from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from headlyn.document_processing.adapters import RssArticleAdapter
from headlyn.document_processing.embeddings import BgeM3DocumentEncoder
from headlyn.document_processing.entities import OllamaEntityExtractor
from headlyn.document_processing.models import DocumentPreparationConfig
from headlyn.document_processing.pipeline import run_document_preparation
from headlyn.document_processing.vector_store import QdrantDocumentVectorStore
from headlyn.story_clustering.models import StoryClusteringConfig
from headlyn.story_clustering.pipeline import run_story_clustering
from headlyn.story_clustering.preparation import prepared_document_from_dict
from headlyn.story_index.config import StoryIndexConfig
from headlyn.story_index.hybrid_index import HybridStoryIndex
from headlyn.story_index.qdrant_store import QdrantStoryStore
from headlyn.story_index.sqlite_store import SQLiteStoryStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "phase0-20260815T200549Z.jsonl"


class StoryClusteringDatasetIntegrationTests(unittest.TestCase):
    """Run the production document and story pipelines on the annotated fixture."""

    def test_converted_dataset_runs_through_real_story_assignment(self) -> None:
        """Prepare all articles with real models and evaluate available pair labels."""
        articles, _ = load_dataset(DATASET_PATH)
        self.assertEqual(len(articles), 170)

        root = PROJECT_ROOT / "artifacts" / "stages"
        preparation = run_document_preparation(
            config=DocumentPreparationConfig(
                ingestion_run_id="phase0-real-dataset-test",
                artifact_root=root,
                ),
                documents=[RssArticleAdapter().adapt(as_rss_payload(article)) for article in articles],
                encoder=BgeM3DocumentEncoder(),
                document_vector_store=QdrantDocumentVectorStore(StoryIndexConfig.from_env()),
                entity_extractor=OllamaEntityExtractor(),
            )
        self.assertEqual(preparation.successful_count, len(articles))

        prepared = [
            prepared_document_from_dict(json.loads(line))
            for line in (preparation.output_dir / "document_features.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        index_config = real_test_index_config(PROJECT_ROOT)
        state = SQLiteStoryStore(index_config.sqlite_path)
        index = HybridStoryIndex(
            index_config,
            dense_store=QdrantStoryStore(index_config),
            state_store=state,
        )
        try:
            result = run_story_clustering(
                StoryClusteringConfig(
                    run_id="phase0-real-dataset-test",
                    artifact_root=root,
                ),
                documents=prepared,
                index=index,
                clock=lambda: datetime(2026, 8, 15, 20, tzinfo=timezone.utc),
            )

            self.assertEqual(result.input_count, 170)
            self.assertEqual(result.failed_count, 0)
            assignments = load_assignments(result.output_dir / "story_assignments.jsonl")
            self.assertEqual(len(assignments), 170)
        finally:
            state.close()


def load_dataset(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Load article and pair-annotation records from the converted JSONL fixture."""
    if not path.exists():
        raise FileNotFoundError(f"annotated dataset not found: {path}")
    articles: list[dict[str, object]] = []
    annotations: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("record_type") == "article":
            articles.append(record)
        elif record.get("record_type") == "pair_annotation":
            annotations.append(record)
    return articles, annotations


def as_rss_payload(article: dict[str, object]) -> dict[str, object]:
    """Map the normalized JSONL document ID to the RSS adapter's source field."""
    payload = dict(article)
    payload["article_id"] = payload["document_id"]
    return payload


def real_test_index_config(project_root: Path) -> StoryIndexConfig:
    """Create a run-specific index using Qdrant credentials loaded from `.env`."""
    configured = StoryIndexConfig.from_env()
    return replace(
        configured,
        sqlite_path=project_root / "data" / "phase0-real-story-index.sqlite3",
        qdrant_collection=f"{configured.qdrant_collection}-dataset-{uuid.uuid4().hex[:12]}",
        vector_size=1024,
    )


def load_assignments(path: Path) -> dict[str, str | None]:
    """Read document-to-story assignments emitted by the clustering pipeline."""
    return {
        str(record["document_id"]): record.get("story_id")
        for record in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    }


if __name__ == "__main__":
    unittest.main()
