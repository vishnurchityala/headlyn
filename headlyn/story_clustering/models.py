from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from headlyn.document_processing.models import EncodedDocument, EntityExtraction, StoryDocument


@dataclass(frozen=True)
class PreparedDocument:
    """A validated source document with its embedding and entity results."""

    document: StoryDocument
    encoded: EncodedDocument
    entities: EntityExtraction


@dataclass(frozen=True)
class StoryMatchScore:
    """All score components used to accept or reject a story candidate."""

    story_id: str
    semantic_score: float
    lexical_score: float
    entity_score: float
    temporal_score: float
    final_score: float
    threshold: float
    accepted: bool
    degraded: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize score components for assignment diagnostics."""
        return {
            "story_id": self.story_id,
            "semantic_score": self.semantic_score,
            "lexical_score": self.lexical_score,
            "entity_score": self.entity_score,
            "temporal_score": self.temporal_score,
            "final_score": self.final_score,
            "threshold": self.threshold,
            "accepted": self.accepted,
            "degraded": self.degraded,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AssignmentResult:
    """Outcome of processing one prepared document."""

    document_id: str
    story_id: str | None
    decision: Literal["attached", "singleton", "skipped", "failed"]
    score: StoryMatchScore | None
    candidate_count: int
    degraded: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize the assignment outcome and optional winning score."""
        return {
            "document_id": self.document_id,
            "story_id": self.story_id,
            "decision": self.decision,
            "score": self.score.as_dict() if self.score else None,
            "candidate_count": self.candidate_count,
            "degraded": self.degraded,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StoryClusteringConfig:
    """Runtime settings for incremental story assignment."""

    run_id: str
    artifact_root: Path | None = None
    match_threshold: float = 0.70
    semantic_weight: float = 0.50
    lexical_weight: float = 0.25
    entity_weight: float = 0.20
    temporal_weight: float = 0.05
    active_window_hours: int = 72
    dense_limit: int = 20
    lexical_limit: int = 20
    order_by_published_at: bool = True


@dataclass(frozen=True)
class StoryClusteringResult:
    """Run summary returned after assignments and story artifacts are written."""

    run_id: str
    status: str
    input_count: int
    attached_count: int
    singleton_count: int
    skipped_count: int
    failed_count: int
    output_dir: Path
    summary_path: Path
