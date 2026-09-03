from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from headlyn.document_processing.adapters import RssArticleAdapter
from headlyn.document_processing.canonical import build_canonical_text, document_fingerprint
from headlyn.document_processing.models import EncodedDocument, EntityExtraction, ExtractedEntity
from headlyn.story_clustering.clusterer import StoryClusterer
from headlyn.story_clustering.models import PreparedDocument, StoryClusteringConfig
from headlyn.story_index.config import StoryIndexConfig
from headlyn.story_index.hybrid_index import HybridStoryIndex
from headlyn.story_index.models import StoryCandidate
from headlyn.story_index.sqlite_store import SQLiteStoryStore


class FakeDenseStore:
    def __init__(self) -> None:
        self.stories = {}

    def ensure_collection(self, vector_size):
        return None

    def health_check(self):
        return None

    def upsert(self, story):
        self.stories[story.story_id] = story

    def search_active(self, vector, *, limit):
        return [
            StoryCandidate(story_id, 0.90, rank, "dense")
            for rank, (story_id, story) in enumerate(self.stories.items(), start=1)
            if story.status == "active"
        ][:limit]

    def mark_status(self, story_id, status):
        if story_id in self.stories:
            self.stories[story_id] = self.stories[story_id].__class__(
                **{**self.stories[story_id].__dict__, "status": status}
            )

    def delete(self, story_id):
        self.stories.pop(story_id, None)


class StoryClusteringTests(unittest.TestCase):
    def test_first_document_is_singleton_and_second_matching_document_attaches(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SQLiteStoryStore(Path(directory) / "index.sqlite")
            dense = FakeDenseStore()
            index = HybridStoryIndex(
                StoryIndexConfig(sqlite_path=Path(directory) / "index.sqlite"),
                dense_store=dense,
                state_store=state,
            )
            now = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
            clusterer = StoryClusterer(
                index=index,
                config=StoryClusteringConfig(run_id="run-1"),
                clock=lambda: now,
            )
            index.initialize()
            first = prepared("article-1", "India trade talks")
            second = prepared("article-2", "India trade negotiations")

            first_result = clusterer.process_document(first)
            second_result = clusterer.process_document(second)

            self.assertEqual(first_result.decision, "singleton")
            self.assertEqual(second_result.decision, "attached")
            self.assertEqual(first_result.story_id, second_result.story_id)
            story = index.get_story(first_result.story_id)
            self.assertIsNotNone(story)
            self.assertEqual(story.document_count, 2)
            self.assertEqual(len(story.member_documents), 2)
            state.close()

    def test_duplicate_document_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SQLiteStoryStore(Path(directory) / "index.sqlite")
            index = HybridStoryIndex(
                StoryIndexConfig(sqlite_path=Path(directory) / "index.sqlite"),
                dense_store=FakeDenseStore(),
                state_store=state,
            )
            index.initialize()
            clusterer = StoryClusterer(
                index=index,
                config=StoryClusteringConfig(run_id="run-1"),
                clock=lambda: datetime(2026, 9, 3, 12, tzinfo=timezone.utc),
            )
            prepared_document = prepared("article-1", "India trade talks")
            clusterer.process_document(prepared_document)
            result = clusterer.process_document(prepared_document)
            self.assertEqual(result.decision, "skipped")
            state.close()


def prepared(document_id: str, title: str) -> PreparedDocument:
    document = RssArticleAdapter().adapt(
        {
            "article_id": document_id,
            "source_id": "source",
            "source_name": "Source",
            "title": title,
            "description": "India trade negotiations continue.",
            "published_at": "2026-09-03T08:00:00+00:00",
            "url": f"https://example.com/{document_id}",
            "ingested_at": "2026-09-03T08:05:00+00:00",
        }
    )
    fingerprint = document_fingerprint(document)
    return PreparedDocument(
        document=document,
        encoded=EncodedDocument(
            document_id=document_id,
            input_fingerprint=fingerprint,
            canonical_text=build_canonical_text(document),
            dense_vector=(1.0, 0.0),
            sparse_weights={"1": 0.5},
            model_name="fake-bge-m3",
            max_length=512,
        ),
        entities=EntityExtraction(
            document_id=document_id,
            input_fingerprint=fingerprint,
            model="fake-gemma",
            prompt_version="entity-v1",
            status="ok",
            entities=(ExtractedEntity("India", "India", "GPE", "primary"),),
        ),
    )


if __name__ == "__main__":
    unittest.main()
