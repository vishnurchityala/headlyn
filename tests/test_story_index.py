from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from headlyn.story_index.config import StoryIndexConfig
from headlyn.story_index.hybrid_index import HybridStoryIndex
from headlyn.story_index.models import StoryCandidate, StoryMetadata
from headlyn.story_index.sqlite_store import SQLiteStoryStore


class FakeDenseStore:
    def __init__(self) -> None:
        self.initialized_with = None
        self.hits = [StoryCandidate("story-dense", 0.91, 1, "dense")]

    def ensure_collection(self, vector_size):
        self.initialized_with = vector_size

    def health_check(self):
        return None

    def upsert(self, story):
        return None

    def search_active(self, vector, *, limit):
        return self.hits[:limit]

    def mark_status(self, story_id, status):
        return None

    def delete(self, story_id):
        return None


def story(story_id: str = "story-1") -> StoryMetadata:
    timestamp = datetime(2026, 9, 3, 8, tzinfo=timezone.utc)
    return StoryMetadata(
        story_id=story_id,
        status="active",
        representative_document_id="article-1",
        member_document_ids=["article-1"],
        canonical_text="Title: India trade talks\n\nContent: India trade negotiations continue",
        first_seen=timestamp,
        latest_published_at=timestamp,
        last_updated_at=timestamp,
        document_count=1,
        source_count=1,
        entity_names=["India"],
        category="National",
    )


class StoryIndexTests(unittest.TestCase):
    def test_sqlite_initializes_and_returns_active_fts_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStoryStore(Path(directory) / "index.sqlite")
            store.initialize()
            store.upsert_story(story())
            candidates = store.search_active_lexical("India trade", limit=20)
            self.assertEqual([candidate.story_id for candidate in candidates], ["story-1"])
            self.assertTrue(store.get_story("story-1"))
            store.mark_status("story-1", "closed")
            self.assertEqual(store.search_active_lexical("India trade", limit=20), [])
            store.close()

    def test_hybrid_index_unions_dense_and_lexical_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            state_store = SQLiteStoryStore(Path(directory) / "index.sqlite")
            state_store.initialize()
            state_store.upsert_story(story("story-lexical"))
            dense_store = FakeDenseStore()
            index = HybridStoryIndex(
                StoryIndexConfig(sqlite_path=Path(directory) / "index.sqlite"),
                dense_store=dense_store,
                state_store=state_store,
            )
            candidates = index.search("India trade", [1.0, 0.0], dense_limit=20, lexical_limit=20)
            self.assertEqual({candidate.story_id for candidate in candidates}, {"story-dense", "story-lexical"})
            dense_candidate = next(candidate for candidate in candidates if candidate.story_id == "story-dense")
            lexical_candidate = next(candidate for candidate in candidates if candidate.story_id == "story-lexical")
            self.assertEqual(dense_candidate.dense_score, 0.91)
            self.assertIsNotNone(lexical_candidate.lexical_score)
            state_store.close()

    def test_config_loads_qdrant_settings_from_env_file(self):
        with patch.dict(
            "os.environ",
            {
                "HEADLYN_QDRANT_URL": "https://qdrant.example",
                "HEADLYN_QDRANT_API_KEY": "secret",
                "HEADLYN_QDRANT_COLLECTION": "test-stories",
                "HEADLYN_STORY_VECTOR_SIZE": "4",
            },
            clear=False,
        ):
            config = StoryIndexConfig.from_env()
            self.assertEqual(config.qdrant_url, "https://qdrant.example")
            self.assertEqual(config.qdrant_api_key, "secret")
            self.assertEqual(config.qdrant_collection, "test-stories")
            self.assertEqual(config.vector_size, 4)


if __name__ == "__main__":
    unittest.main()
