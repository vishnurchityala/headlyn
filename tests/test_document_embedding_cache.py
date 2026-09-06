from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Sequence

from headlyn.document_processing.canonical import build_canonical_text, document_fingerprint
from headlyn.document_processing.embeddings import CachedDocumentEncoder
from headlyn.document_processing.models import EncodedDocument, StoryDocument


class FakeVectorStore:
    """In-memory document vector store for cache behavior tests."""

    def __init__(self) -> None:
        self.values: dict[str, EncodedDocument] = {}
        self.initialized_sizes: list[int] = []

    def initialize(self, vector_size: int) -> None:
        """Record collection initialization without contacting Qdrant."""
        self.initialized_sizes.append(vector_size)

    def health_check(self) -> None:
        """Keep the fake store health-compatible with the production protocol."""

    def get_many(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        max_length: int,
    ) -> dict[str, EncodedDocument]:
        """Return only compatible cached vectors."""
        return {
            document.document_id: encoded
            for document in documents
            if (encoded := self.values.get(document.document_id)) is not None
            and encoded.input_fingerprint == document_fingerprint(document)
            and encoded.model_name == model_name
            and encoded.max_length == max_length
        }

    def upsert(self, encoded: EncodedDocument) -> None:
        """Store one generated vector."""
        self.values[encoded.document_id] = encoded


class CountingEncoder:
    """Fake base encoder that records expensive encoding calls."""

    model_name = "test-model"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, documents: Sequence[StoryDocument]) -> list[EncodedDocument]:
        """Generate simple valid vectors for requested cache misses."""
        self.calls.append([document.document_id for document in documents])
        return [
            EncodedDocument(
                document_id=document.document_id,
                input_fingerprint=document_fingerprint(document),
                canonical_text=build_canonical_text(document),
                dense_vector=(1.0, 0.0),
                sparse_weights={"test": 1.0},
                model_name=self.model_name,
                max_length=512,
            )
            for document in documents
        ]


class DocumentEmbeddingCacheTests(unittest.TestCase):
    """Verify reusable document embedding behavior."""

    def test_second_encoding_reuses_cached_vectors(self) -> None:
        """Encode a document once and avoid the base encoder on the second request."""
        document = document_value("article-1", "Initial title")
        store = FakeVectorStore()
        encoder = CountingEncoder()
        cached = CachedDocumentEncoder(encoder, store, vector_size=2)

        first = cached.encode([document])
        second = cached.encode([document])

        self.assertEqual(encoder.calls, [["article-1"]])
        self.assertEqual(first, second)
        self.assertEqual(store.initialized_sizes, [2, 2])

    def test_changed_document_fingerprint_causes_reencoding(self) -> None:
        """Treat changed canonical content as a cache miss for the same document ID."""
        store = FakeVectorStore()
        encoder = CountingEncoder()
        cached = CachedDocumentEncoder(encoder, store, vector_size=2)
        cached.encode([document_value("article-1", "Initial title")])
        cached.encode([document_value("article-1", "Updated title")])

        self.assertEqual(encoder.calls, [["article-1"], ["article-1"]])


def document_value(document_id: str, title: str) -> StoryDocument:
    """Build a minimal valid story document for cache tests."""
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
