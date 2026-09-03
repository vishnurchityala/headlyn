from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from .models import StoryCandidate, StoryMetadata, StoryRepresentation


class DenseVectorStore(Protocol):
    """Interface implemented by a dense vector backend such as Qdrant."""

    def ensure_collection(self, vector_size: int) -> None:
        ...

    def health_check(self) -> None:
        ...

    def upsert(self, story: StoryRepresentation) -> None:
        ...

    def search_active(self, vector: Sequence[float], *, limit: int) -> list[StoryCandidate]:
        ...

    def mark_status(self, story_id: str, status: str) -> None:
        ...

    def delete(self, story_id: str) -> None:
        ...


class StoryStateStore(Protocol):
    """Interface for SQLite story metadata, FTS5, and idempotency state."""

    def initialize(self) -> None:
        ...

    def health_check(self) -> None:
        ...

    def get_story(self, story_id: str) -> StoryMetadata | None:
        ...

    def upsert_story(self, story: StoryMetadata) -> None:
        ...

    def search_active_lexical(self, query_text: str, *, limit: int) -> list[StoryCandidate]:
        ...

    def mark_status(self, story_id: str, status: str) -> None:
        ...

    def is_document_indexed(self, document_id: str) -> bool:
        ...

    def get_active_stories(self) -> list[StoryMetadata]:
        ...

    def record_document(
        self,
        document_id: str,
        story_id: str,
        *,
        input_fingerprint: str | None = None,
        document_payload: dict[str, object] | None = None,
    ) -> None:
        ...

    def close(self) -> None:
        ...
