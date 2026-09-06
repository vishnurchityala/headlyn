from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from headlyn.ingestion.artifacts import write_json, write_jsonl

from .adapters import RssArticleAdapter, VideoDocumentAdapter
from .canonical import document_fingerprint
from .embeddings import BgeM3DocumentEncoder, CachedDocumentEncoder, DocumentEncoder
from .entities import CachedEntityExtractor, EntityExtractor, OllamaEntityExtractor
from .models import (
    DocumentPreparationConfig,
    DocumentPreparationResult,
    EncodedDocument,
    EntityExtraction,
    StoryDocument,
)
from .vector_store import DocumentVectorStore


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = ROOT_DIR / "artifacts" / "stages"
STAGE_NAME = "document_preparation"


def run_document_preparation(
    config: DocumentPreparationConfig,
    *,
    documents: list[StoryDocument],
    invalid_input_count: int = 0,
    encoder: DocumentEncoder | None = None,
    document_vector_store: DocumentVectorStore | None = None,
    entity_extractor: EntityExtractor | None = None,
) -> DocumentPreparationResult:
    """Prepare caller-provided documents and write downstream-ready artifacts."""
    # Validate configuration and establish the run-specific output directory.
    validate_config(config)
    artifact_root = config.artifact_root or DEFAULT_ARTIFACT_ROOT
    output_dir = config.output_dir or artifact_root / STAGE_NAME / config.ingestion_run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Remove repeated document IDs before invoking expensive model operations.
    documents = deduplicate_documents(documents)
    invalid_inputs = invalid_input_count
    write_jsonl(output_dir / "documents.jsonl", [document.as_dict() for document in documents])

    # Initialize each model implementation once and reuse it for this run.
    encoder_instance = encoder or BgeM3DocumentEncoder(
        model_name=config.embedding_model,
        batch_size=config.embedding_batch_size,
        max_length=config.embedding_max_length,
        use_fp16=config.use_fp16,
    )
    if document_vector_store is not None:
        encoder_instance = CachedDocumentEncoder(
            encoder_instance,
            document_vector_store,
            vector_size=config.embedding_vector_size,
            max_length=config.embedding_max_length,
        )
    extractor = entity_extractor or OllamaEntityExtractor(
        model_name=config.entity_model,
        endpoint=config.llm_endpoint,
        timeout_seconds=config.llm_timeout_seconds,
        retries=config.llm_retries,
        prompt_version=config.entity_prompt_version,
    )
    if document_vector_store is not None:
        extractor = CachedEntityExtractor(extractor, document_vector_store)

    # Produce dense/sparse embeddings and independent entity results.
    embeddings, embedding_errors = encode_documents(documents, encoder_instance)
    entities = extract_entities(documents, extractor)
    write_jsonl(output_dir / "embeddings.jsonl", [item.as_dict() for item in embeddings.values()])
    write_jsonl(output_dir / "entity_extractions.jsonl", [item.as_dict() for item in entities.values()])

    # Combine successful embeddings with entity results into downstream records.
    features: list[dict[str, object]] = []
    for document in documents:
        encoded = embeddings.get(document.document_id)
        extraction = entities[document.document_id]
        if encoded is None:
            continue
        features.append(
            {
                "document": document.as_dict(),
                "canonical_text": encoded.canonical_text,
                "input_fingerprint": encoded.input_fingerprint,
                "embedding": encoded.as_dict(),
                "entities": extraction.as_dict(),
                "status": "ok",
            }
        )
    # Persist the model outputs and operational summary for inspection/replay.
    write_jsonl(output_dir / "document_features.jsonl", features)

    summary = {
        "stage": STAGE_NAME,
        "status": "failed" if not documents else "partial" if invalid_inputs or embedding_errors or any(item.status == "failed" for item in entities.values()) else "ok",
        "ingestion_run_id": config.ingestion_run_id,
        "input_count": len(documents) + invalid_inputs,
        "valid_document_count": len(documents),
        "article_count": sum(document.document_type == "article" for document in documents),
        "video_count": sum(document.document_type == "video" for document in documents),
        "successful_count": len(features),
        "invalid_input_count": invalid_inputs,
        "embedding_failure_count": len(embedding_errors),
        "entity_failure_count": sum(item.status == "failed" for item in entities.values()),
        "embedding_model": encoder_instance.model_name,
        "entity_model": extractor.model_name,
        "entity_prompt_version": extractor.prompt_version,
        "embedding_errors": embedding_errors,
        "output_files": [
            "documents.jsonl",
            "embeddings.jsonl",
            "entity_extractions.jsonl",
            "document_features.jsonl",
            "summary.json",
        ],
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    status = str(summary["status"])
    return DocumentPreparationResult(
        ingestion_run_id=config.ingestion_run_id,
        status=status,
        input_count=len(documents),
        successful_count=len(features),
        output_dir=output_dir,
        summary_path=summary_path,
    )


def load_documents(
    ingestion_dir: Path,
    config: DocumentPreparationConfig,
) -> tuple[list[StoryDocument], int]:
    """Load source assets for the CLI and adapt them into story documents."""
    # Discover configured RSS source directories and adapt each JSONL item.
    source_ids = config.source_ids or load_source_ids(ingestion_dir)
    documents: list[StoryDocument] = []
    invalid = 0
    for source_id in source_ids:
        path = ingestion_dir / source_id / "items.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("item must be an object")
                documents.append(RssArticleAdapter().adapt(value))
            except (json.JSONDecodeError, ValueError, TypeError):
                invalid += 1
    # Optionally adapt caller-supplied, pre-normalized video JSONL records.
    if config.video_input:
        for line in config.video_input.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("video item must be an object")
                documents.append(VideoDocumentAdapter().adapt(value))
            except (json.JSONDecodeError, ValueError, TypeError):
                invalid += 1
    return documents, invalid


def load_source_ids(ingestion_dir: Path) -> tuple[str, ...]:
    """Read source IDs from an ingestion summary or infer them from directories."""
    summary_path = ingestion_dir / "summary.json"
    if summary_path.exists():
        value = json.loads(summary_path.read_text(encoding="utf-8"))
        source_ids = tuple(
            str(item["source_id"])
            for item in value.get("sources", [])
            if isinstance(item, dict) and item.get("source_id")
        )
        if source_ids:
            return source_ids
    return tuple(sorted(path.name for path in ingestion_dir.iterdir() if path.is_dir()))


def deduplicate_documents(documents: list[StoryDocument]) -> list[StoryDocument]:
    """Keep the first occurrence of each document ID in input order."""
    result: list[StoryDocument] = []
    seen: set[str] = set()
    for document in documents:
        if document.document_id in seen:
            continue
        seen.add(document.document_id)
        result.append(document)
    return result


def encode_documents(
    documents: list[StoryDocument],
    encoder: DocumentEncoder,
) -> tuple[dict[str, EncodedDocument], list[dict[str, str]]]:
    """Encode a batch, falling back to per-document attempts after batch failure."""
    # Attempt the efficient batch path first.
    result: dict[str, EncodedDocument] = {}
    pending = documents
    errors: list[dict[str, str]] = []
    if pending:
        try:
            encoded = encoder.encode(pending)
            if len(encoded) != len(pending):
                raise RuntimeError("encoder returned an unexpected number of documents")
            result.update({item.document_id: item for item in encoded})
        except Exception as exc:
            # Isolate bad documents so one input does not hide all good results.
            for document in pending:
                try:
                    item = encoder.encode([document])
                    if len(item) != 1:
                        raise RuntimeError("encoder returned an unexpected number of documents")
                    result[document.document_id] = item[0]
                except Exception as item_exc:
                    errors.append({"document_id": document.document_id, "error": f"{type(item_exc).__name__}: {item_exc}", "batch_error": str(exc)})
    return result, errors


def extract_entities(
    documents: list[StoryDocument],
    extractor: EntityExtractor,
) -> dict[str, EntityExtraction]:
    """Extract entities per document and convert exceptions to failed results."""
    if isinstance(extractor, CachedEntityExtractor):
        try:
            return extractor.extract_many(documents)
        except Exception:
            # Preserve per-document failure reporting if the cache backend is unavailable.
            pass
    result: dict[str, EntityExtraction] = {}
    for document in documents:
        # Keep entity failure local to the document while preserving its fingerprint.
        fingerprint = document_fingerprint(document)
        try:
            result[document.document_id] = extractor.extract(document)
        except Exception as exc:
            result[document.document_id] = EntityExtraction(
                document_id=document.document_id,
                input_fingerprint=fingerprint,
                model=extractor.model_name,
                prompt_version=extractor.prompt_version,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
    return result


def validate_config(config: DocumentPreparationConfig) -> None:
    """Validate model, retry, input, and embedding configuration."""
    if not config.ingestion_run_id.strip():
        raise ValueError("ingestion_run_id is required")
    if config.llm_timeout_seconds < 1 or config.llm_retries < 0:
        raise ValueError("invalid LLM timeout or retry count")
    if config.embedding_batch_size < 1 or config.embedding_max_length < 1 or config.embedding_vector_size < 1:
        raise ValueError("embedding batch size, max length, and vector size must be positive")
    if config.video_input and not config.video_input.exists():
        raise FileNotFoundError(f"video input not found: {config.video_input}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare documents for story clustering")
    parser.add_argument("--ingestion-run-id", required=True)
    parser.add_argument("--source", dest="source_ids", action="append")
    parser.add_argument("--video-input", type=Path)
    parser.add_argument("--embedding-model", default="BAAI/bge-m3")
    parser.add_argument("--entity-model", default="gemma4:e4b-it-q4_K_M")
    parser.add_argument("--llm-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--llm-timeout-seconds", type=int, default=120)
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--embedding-batch-size", type=int, default=16)
    parser.add_argument("--embedding-max-length", type=int, default=512)
    parser.add_argument("--use-fp16", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        documents, invalid_inputs = load_documents(
            args.artifact_root / "rss_ingestion" / args.ingestion_run_id,
            DocumentPreparationConfig(
                ingestion_run_id=args.ingestion_run_id,
                source_ids=tuple(args.source_ids) if args.source_ids else None,
                video_input=args.video_input,
            ),
        )
        result = run_document_preparation(
            DocumentPreparationConfig(
                ingestion_run_id=args.ingestion_run_id,
                artifact_root=args.artifact_root,
                source_ids=tuple(args.source_ids) if args.source_ids else None,
                video_input=args.video_input,
                embedding_model=args.embedding_model,
                entity_model=args.entity_model,
                llm_endpoint=args.llm_endpoint,
                llm_timeout_seconds=args.llm_timeout_seconds,
                llm_retries=args.llm_retries,
                embedding_batch_size=args.embedding_batch_size,
                embedding_max_length=args.embedding_max_length,
                use_fp16=args.use_fp16,
                output_dir=args.output_dir,
            ),
            documents=documents,
            invalid_input_count=invalid_inputs,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"document_preparation: failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"run_id": result.ingestion_run_id, "status": result.status, "output_dir": str(result.output_dir)}))
    return 0 if result.status in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
