from __future__ import annotations

from typing import Sequence

from .config import StoryIndexConfig
from .models import HybridCandidate, StoryMetadata, StoryRepresentation
from .protocols import DenseVectorStore, StoryStateStore


class HybridStoryIndex:
    """Coordinate dense Qdrant retrieval with SQLite lexical/state retrieval."""

    def __init__(
        self,
        config: StoryIndexConfig,
        *,
        dense_store: DenseVectorStore,
        state_store: StoryStateStore,
    ) -> None:
        self.config = config
        self.dense_store = dense_store
        self.state_store = state_store

    def initialize(self) -> None:
        """Initialize both backends and validate the configured dense schema."""
        # Prepare the relational state store before accepting index operations.
        self.state_store.initialize()

        # Create or validate the Qdrant collection against the encoder dimension.
        self.dense_store.ensure_collection(self.config.vector_size)

    def health_check(self) -> None:
        """Run health checks against both coordinated backends."""
        self.dense_store.health_check()
        self.state_store.health_check()

    def search(
        self,
        query_text: str,
        query_vector: Sequence[float] | None = None,
        *,
        dense_limit: int | None = None,
        lexical_limit: int | None = None,
    ) -> list[HybridCandidate]:
        """Retrieve, union, and deduplicate dense and lexical story candidates."""
        # Search Qdrant only when a dense query vector was supplied.
        dense_hits = (
            self.dense_store.search_active(
                query_vector,
                limit=dense_limit or self.config.dense_limit,
            )
            if query_vector is not None
            else []
        )

        # Search SQLite FTS5 with the canonical query text.
        lexical_hits = self.state_store.search_active_lexical(
            query_text,
            limit=lexical_limit or self.config.lexical_limit,
        )

        # Union both result lists while preserving each backend's raw score and rank.
        candidates: dict[str, HybridCandidate] = {}
        for hit in dense_hits:
            candidates[hit.story_id] = HybridCandidate(
                story_id=hit.story_id,
                dense_score=hit.score,
                dense_rank=hit.rank,
            )
        for hit in lexical_hits:
            current = candidates.get(hit.story_id)
            candidates[hit.story_id] = HybridCandidate(
                story_id=hit.story_id,
                dense_score=current.dense_score if current else None,
                dense_rank=current.dense_rank if current else None,
                lexical_score=hit.score,
                lexical_rank=hit.rank,
            )
        return list(candidates.values())

    def get_story(self, story_id: str) -> StoryMetadata | None:
        """Load complete story state from SQLite."""
        return self.state_store.get_story(story_id)

    def get_active_stories(self) -> list[StoryMetadata]:
        """Return complete active story state for lifecycle and diagnostics."""
        return self.state_store.get_active_stories()

    def is_document_indexed(self, document_id: str) -> bool:
        """Check document idempotency through the SQLite state store."""
        return self.state_store.is_document_indexed(document_id)

    def mark_closed(self, story_id: str) -> None:
        """Mark a story closed in both coordinated backends."""
        self.state_store.mark_status(story_id, "closed")
        self.dense_store.mark_status(story_id, "closed")

    def upsert_story(
        self,
        story: StoryMetadata,
        representation: StoryRepresentation,
    ) -> None:
        """Persist one story in SQLite and Qdrant with explicit write errors."""
        try:
            # SQLite is updated first because it is the complete state source of truth.
            self.state_store.upsert_story(story)

            # Qdrant receives only the searchable centroid and compact payload.
            self.dense_store.upsert(representation)
        except Exception as exc:
            raise RuntimeError(f"hybrid story upsert failed for {story.story_id}: {exc}") from exc
