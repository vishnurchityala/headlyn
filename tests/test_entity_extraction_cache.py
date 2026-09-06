from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Sequence

from headlyn.document_processing.canonical import document_fingerprint
from headlyn.document_processing.entities import CachedEntityExtractor
from headlyn.document_processing.models import EntityExtraction, ExtractedEntity, StoryDocument


class FakeEntityCache:
    """In-memory entity cache used to verify cache hit and miss behavior."""

    def __init__(self) -> None:
        self.values: dict[str, EntityExtraction] = {}

    def get_many_entities(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        prompt_version: str,
    ) -> dict[str, EntityExtraction]:
        """Return only extractions compatible with the requested provenance."""
        return {
            document.document_id: extraction
            for document in documents
            if (extraction := self.values.get(document.document_id)) is not None
            and extraction.input_fingerprint == document_fingerprint(document)
            and extraction.model == model_name
            and extraction.prompt_version == prompt_version
        }

    def upsert_entity(self, document: StoryDocument, extraction: EntityExtraction) -> None:
        """Persist one successful extraction in memory."""
        self.values[document.document_id] = extraction


class CountingExtractor:
    """Fake expensive extractor that records model calls."""

    model_name = "test-gemma"
    prompt_version = "test-prompt-v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, document: StoryDocument) -> EntityExtraction:
        """Return one deterministic entity result for the requested document."""
        self.calls.append(document.document_id)
        return EntityExtraction(
            document_id=document.document_id,
            input_fingerprint=document_fingerprint(document),
            model=self.model_name,
            prompt_version=self.prompt_version,
            status="ok",
            entities=(ExtractedEntity("India", "India", "OTHER", "secondary"),),
        )


class EntityExtractionCacheTests(unittest.TestCase):
    """Verify persistent entity cache behavior independently of Ollama."""

    def test_second_extraction_reuses_cached_result(self) -> None:
        """Call the expensive extractor only once for repeated input."""
        cache = FakeEntityCache()
        extractor = CountingExtractor()
        cached = CachedEntityExtractor(extractor, cache)
        document = document_value("article-1", "Initial title")

        first = cached.extract(document)
        second = cached.extract(document)

        self.assertEqual(extractor.calls, ["article-1"])
        self.assertEqual(first, second)

    def test_changed_document_fingerprint_causes_extraction(self) -> None:
        """Treat changed document content as an entity cache miss."""
        cache = FakeEntityCache()
        extractor = CountingExtractor()
        cached = CachedEntityExtractor(extractor, cache)

        cached.extract(document_value("article-1", "Initial title"))
        cached.extract(document_value("article-1", "Updated title"))

        self.assertEqual(extractor.calls, ["article-1", "article-1"])


def document_value(document_id: str, title: str) -> StoryDocument:
    """Build a minimal valid document for cache tests."""
    timestamp = datetime(2026, 9, 4, 8, tzinfo=timezone.utc)
    return StoryDocument(
        document_id=document_id,
        document_type="article",
        title=title,
        body_text="A document body.",
        source_id="source",
        source_name="Source",
        published_at=timestamp,
        ingested_at=timestamp,
        url=f"https://example.com/{document_id}",
    )


if __name__ == "__main__":
    unittest.main()
