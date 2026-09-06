from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from .document_processing.embeddings import DocumentEncoder
from .document_processing.entities import EntityExtractor
from .ingestion.models import PipelineConfig
from .ingestion.pipeline import run_pipeline as run_ingestion_pipeline
from .newsletter.delivery import MailSender
from .newsletter.models import NewsletterConfig, NewsletterResult
from .newsletter.pipeline import run_newsletter
from .newsletter.rewrite import StoryRewriter
from .document_processing.models import DocumentPreparationConfig
from .document_processing.pipeline import load_documents, run_document_preparation
from .document_processing.vector_store import QdrantDocumentVectorStore
from .story_clustering.models import PreparedDocument, StoryClusteringConfig
from .story_clustering.pipeline import run_story_clustering
from .story_clustering.preparation import prepared_document_from_dict
from .story_index.config import StoryIndexConfig
from .story_index.hybrid_index import HybridStoryIndex
from .story_index.qdrant_store import QdrantStoryStore
from .story_index.sqlite_store import SQLiteStoryStore
from .tls import configure_ca_bundle


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT_DIR / "artifacts" / "stages"


@dataclass(frozen=True)
class DailyPipelineConfig:
    edition_date: str
    artifact_root: Path | None = None
    story_run_id: str | None = None
    ingestion_mode: str = "live"
    snapshot_date: str | None = None
    source_ids: tuple[str, ...] | None = None
    ingestion_limit: int | None = None
    max_workers: int = 4
    entity_model: str = "gemma4:e4b-it-q4_K_M"
    llm_endpoint: str = "http://127.0.0.1:11434/api/generate"
    llm_timeout_seconds: int = 120
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = 16
    embedding_max_length: int = 512
    use_fp16: bool = False
    semantic_weight: float = 0.7
    lexical_weight: float = 0.15
    entity_weight: float = 0.15
    temporal_weight: float = 0.0
    match_threshold: float = 0.70
    active_window_hours: int = 72
    dense_limit: int = 20
    lexical_limit: int = 20
    newsletter_model: str = "gemma4:e4b-it-q4_K_M"
    target_items: int = 10
    minimum_items: int = 5
    max_items_per_source: int = 3
    send: bool = False
    force_rebuild: bool = False
    force_resend: bool = False


@dataclass(frozen=True)
class DailyPipelineResult:
    edition_date: str
    story_run_id: str
    newsletter: NewsletterResult


def run_pipeline(
    config: DailyPipelineConfig,
    *,
    encoder: DocumentEncoder | None = None,
    entity_extractor: EntityExtractor | None = None,
    rewriter: StoryRewriter | None = None,
    sender: MailSender | None = None,
) -> DailyPipelineResult:
    # Load local credentials/configuration when the pipeline is run directly.
    # Existing shell variables take precedence over values in .env.
    load_dotenv(override=False)
    configure_ca_bundle()
    artifact_root = config.artifact_root or DEFAULT_ARTIFACT_ROOT
    if config.story_run_id:
        story_run_id = config.story_run_id
    else:
        ingestion = run_ingestion_pipeline(
            PipelineConfig(
                mode=config.ingestion_mode,
                snapshot_date=config.snapshot_date,
                artifact_root=artifact_root,
                source_ids=config.source_ids,
                limit=config.ingestion_limit,
                max_workers=config.max_workers,
            )
        )
        if ingestion.status == "failed":
            raise RuntimeError("daily pipeline cannot continue after ingestion failure")
        story_run_id = ingestion.run_id
        preparation_config = DocumentPreparationConfig(
            ingestion_run_id=story_run_id,
            artifact_root=artifact_root,
            source_ids=config.source_ids,
            embedding_model=config.embedding_model,
            entity_model=config.entity_model,
            llm_endpoint=config.llm_endpoint,
            llm_timeout_seconds=config.llm_timeout_seconds,
            embedding_batch_size=config.embedding_batch_size,
            embedding_max_length=config.embedding_max_length,
            use_fp16=config.use_fp16,
        )
        documents, invalid_inputs = load_documents(
            artifact_root / "rss_ingestion" / story_run_id,
            preparation_config,
        )
        index_config = StoryIndexConfig.from_env()
        preparation = run_document_preparation(
            preparation_config,
            documents=documents,
            invalid_input_count=invalid_inputs,
            encoder=encoder,
            document_vector_store=QdrantDocumentVectorStore(index_config),
            entity_extractor=entity_extractor,
        )
        prepared_documents = load_prepared_documents(preparation.output_dir / "document_features.jsonl")
        state_store = SQLiteStoryStore(index_config.sqlite_path)
        story_index = HybridStoryIndex(
            index_config,
            dense_store=QdrantStoryStore(index_config),
            state_store=state_store,
        )
        try:
            run_story_clustering(
                StoryClusteringConfig(
                    run_id=story_run_id,
                    artifact_root=artifact_root,
                    match_threshold=config.match_threshold,
                    semantic_weight=config.semantic_weight,
                    lexical_weight=config.lexical_weight,
                    entity_weight=config.entity_weight,
                    temporal_weight=config.temporal_weight,
                    active_window_hours=config.active_window_hours,
                    dense_limit=config.dense_limit,
                    lexical_limit=config.lexical_limit,
                ),
                documents=prepared_documents,
                index=story_index,
            )
        finally:
            state_store.close()
    newsletter = run_newsletter(
        NewsletterConfig(
            story_run_id=story_run_id,
            edition_date=config.edition_date,
            artifact_root=artifact_root,
            llm_model=config.newsletter_model,
            llm_endpoint=config.llm_endpoint,
            llm_timeout_seconds=config.llm_timeout_seconds,
            target_items=config.target_items,
            minimum_items=config.minimum_items,
            max_items_per_source=config.max_items_per_source,
            send=config.send,
            force_rebuild=config.force_rebuild,
            force_resend=config.force_resend,
        ),
        rewriter=rewriter,
        sender=sender,
    )
    return DailyPipelineResult(
        edition_date=config.edition_date,
        story_run_id=story_run_id,
        newsletter=newsletter,
    )


def default_edition_date() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the complete Headlyn daily pipeline")
    parser.add_argument("--edition-date", default=default_edition_date())
    parser.add_argument("--story-run-id")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--mode", dest="ingestion_mode", choices=("live", "snapshot"), default="live")
    parser.add_argument("--snapshot-date")
    parser.add_argument("--source", dest="source_ids", action="append")
    parser.add_argument("--limit", dest="ingestion_limit", type=int)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--entity-model", default="gemma4:e4b-it-q4_K_M")
    parser.add_argument("--newsletter-model", default="gemma4:e4b-it-q4_K_M")
    parser.add_argument("--llm-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--llm-timeout-seconds", type=int, default=120)
    parser.add_argument("--embedding-model", "--lexical-model", dest="embedding_model", default="BAAI/bge-m3")
    parser.add_argument("--temporal-weight", type=float, default=0.0)
    parser.add_argument("--semantic-weight", type=float, default=0.7)
    parser.add_argument("--lexical-weight", type=float, default=0.15)
    parser.add_argument("--entity-weight", type=float, default=0.15)
    parser.add_argument("--match-threshold", "--merge-threshold", dest="match_threshold", type=float, default=0.70)
    parser.add_argument("--embedding-batch-size", type=int, default=16)
    parser.add_argument("--embedding-max-length", type=int, default=512)
    parser.add_argument("--use-fp16", action="store_true")
    parser.add_argument("--target-items", type=int, default=10)
    parser.add_argument("--minimum-items", type=int, default=5)
    parser.add_argument("--max-items-per-source", type=int, default=3)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--force-resend", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_pipeline(
            DailyPipelineConfig(
                edition_date=args.edition_date,
                artifact_root=args.artifact_root,
                story_run_id=args.story_run_id,
                ingestion_mode=args.ingestion_mode,
                snapshot_date=args.snapshot_date,
                source_ids=tuple(args.source_ids) if args.source_ids else None,
                ingestion_limit=args.ingestion_limit,
                max_workers=args.max_workers,
                entity_model=args.entity_model,
                newsletter_model=args.newsletter_model,
                llm_endpoint=args.llm_endpoint,
                llm_timeout_seconds=args.llm_timeout_seconds,
                embedding_model=args.embedding_model,
                embedding_batch_size=args.embedding_batch_size,
                embedding_max_length=args.embedding_max_length,
                use_fp16=args.use_fp16,
                semantic_weight=args.semantic_weight,
                entity_weight=args.entity_weight,
                lexical_weight=args.lexical_weight,
                temporal_weight=args.temporal_weight,
                match_threshold=args.match_threshold,
                target_items=args.target_items,
                minimum_items=args.minimum_items,
                max_items_per_source=args.max_items_per_source,
                send=args.send,
                force_rebuild=args.force_rebuild,
                force_resend=args.force_resend,
            )
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"headlyn_pipeline: failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "edition_date": result.edition_date,
                "story_run_id": result.story_run_id,
                "status": result.newsletter.status,
                "selected_story_count": result.newsletter.selected_story_count,
                "output_dir": str(result.newsletter.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.newsletter.status in {"preview", "sent", "held"} else 1


def load_prepared_documents(path: Path) -> list[PreparedDocument]:
    """Load validated document features produced by the preparation stage."""
    if not path.exists():
        raise FileNotFoundError(f"prepared document features not found: {path}")
    return [
        prepared_document_from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


if __name__ == "__main__":
    raise SystemExit(main())
