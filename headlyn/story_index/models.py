from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Mapping


StoryStatus = Literal["active", "closed"]


@dataclass(frozen=True)
class StoryRepresentation:
    """Searchable story fields stored in the dense vector index."""

    story_id: str
    canonical_text: str
    dense_vector: tuple[float, ...]
    status: StoryStatus
    first_seen: datetime
    latest_published_at: datetime
    last_updated_at: datetime
    document_count: int
    source_count: int
    entity_names: tuple[str, ...] = ()
    category: str | None = None

    def payload(self) -> dict[str, object]:
        """Return the small metadata payload attached to the Qdrant point."""
        return {
            "story_id": self.story_id,
            "status": self.status,
            "category": self.category,
            "document_count": self.document_count,
            "source_count": self.source_count,
            "first_seen": self.first_seen.isoformat(),
            "latest_published_at": self.latest_published_at.isoformat(),
            "last_updated_at": self.last_updated_at.isoformat(),
        }


@dataclass
class StoryMetadata:
    """Complete story state retained by SQLite."""

    story_id: str
    status: StoryStatus
    representative_document_id: str
    member_document_ids: list[str]
    canonical_text: str
    first_seen: datetime
    latest_published_at: datetime
    last_updated_at: datetime
    document_count: int
    source_count: int
    entity_names: list[str] = field(default_factory=list)
    merged_story_ids: list[str] = field(default_factory=list)
    category: str | None = None
    centroid: tuple[float, ...] = ()
    member_documents: list[dict[str, object]] = field(default_factory=list)

    def representation(self, dense_vector: tuple[float, ...]) -> StoryRepresentation:
        """Build the Qdrant-facing representation from complete story state."""
        return StoryRepresentation(
            story_id=self.story_id,
            canonical_text=self.canonical_text,
            dense_vector=dense_vector,
            status=self.status,
            first_seen=self.first_seen,
            latest_published_at=self.latest_published_at,
            last_updated_at=self.last_updated_at,
            document_count=self.document_count,
            source_count=self.source_count,
            entity_names=tuple(self.entity_names),
            category=self.category,
        )


@dataclass(frozen=True)
class StoryCandidate:
    """One dense or lexical search hit before composite reranking."""

    story_id: str
    score: float
    rank: int
    source: Literal["dense", "lexical"]


@dataclass(frozen=True)
class HybridCandidate:
    """Unioned dense/lexical candidate retaining both raw retrieval scores."""

    story_id: str
    dense_score: float | None = None
    dense_rank: int | None = None
    lexical_score: float | None = None
    lexical_rank: int | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize a candidate for diagnostics and development search output."""
        return {
            "story_id": self.story_id,
            "dense_score": self.dense_score,
            "dense_rank": self.dense_rank,
            "lexical_score": self.lexical_score,
            "lexical_rank": self.lexical_rank,
        }
