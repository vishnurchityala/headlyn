from __future__ import annotations

import math
from datetime import datetime

from headlyn.document_processing.models import EntityExtraction
from headlyn.story_index.models import HybridCandidate, StoryMetadata

from .models import StoryMatchScore


def rank_score(rank: int | None, limit: int) -> float:
    """Convert a retrieval rank into a bounded score, with missing hits scoring zero."""
    if rank is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ((rank - 1) / max(1, limit - 1))))


def semantic_score(raw_score: float | None) -> float:
    """Normalize cosine similarity from [-1, 1] into [0, 1]."""
    if raw_score is None:
        return 0.0
    return max(0.0, min(1.0, (float(raw_score) + 1.0) / 2.0))


def entity_score(extraction: EntityExtraction, story: StoryMetadata) -> float:
    """Calculate canonical entity overlap using the smaller set as denominator."""
    document_entities = {
        entity.canonical_name.casefold() for entity in extraction.entities
    }
    story_entities = {name.casefold() for name in story.entity_names}
    if not document_entities or not story_entities:
        return 0.0
    return len(document_entities & story_entities) / min(
        len(document_entities), len(story_entities)
    )


def temporal_score(now: datetime, story: StoryMetadata) -> float:
    """Apply exponential decay to the age of the story's latest activity."""
    age_hours = max(0.0, (now - story.last_updated_at).total_seconds() / 3600)
    return math.exp(-age_hours / 24.0)


def score_candidate(
    candidate: HybridCandidate,
    story: StoryMetadata,
    extraction: EntityExtraction,
    *,
    now: datetime,
    dense_limit: int,
    lexical_limit: int,
    threshold: float,
    semantic_weight: float,
    lexical_weight: float,
    entity_weight: float,
    temporal_weight: float,
) -> StoryMatchScore:
    """Calculate one candidate's component and weighted final scores."""
    semantic = semantic_score(candidate.dense_score)
    lexical = rank_score(candidate.lexical_rank, lexical_limit)
    entities = entity_score(extraction, story)
    temporal = temporal_score(now, story)
    final = (
        semantic_weight * semantic
        + lexical_weight * lexical
        + entity_weight * entities
        + temporal_weight * temporal
    )
    return StoryMatchScore(
        story_id=story.story_id,
        semantic_score=round(semantic, 6),
        lexical_score=round(lexical, 6),
        entity_score=round(entities, 6),
        temporal_score=round(temporal, 6),
        final_score=round(final, 6),
        threshold=threshold,
        accepted=final >= threshold,
        degraded=extraction.status != "ok",
        reason=None if final >= threshold else "below_match_threshold",
    )


def select_best(scores: list[StoryMatchScore]) -> StoryMatchScore | None:
    """Select a deterministic winner by score, components, and story ID."""
    if not scores:
        return None
    return sorted(
        scores,
        key=lambda score: (
            -score.final_score,
            -score.semantic_score,
            -score.lexical_score,
            -score.entity_score,
            -score.temporal_score,
            score.story_id,
        ),
    )[0]
