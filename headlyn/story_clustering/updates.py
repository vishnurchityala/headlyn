from __future__ import annotations

import hashlib
import math
from datetime import datetime

from headlyn.document_processing.models import StoryDocument
from headlyn.story_index.models import StoryMetadata

from .models import PreparedDocument


def normalized_centroid(vector: list[float]) -> tuple[float, ...]:
    """Normalize a vector for cosine-based dense retrieval."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("story centroid must not be zero")
    return tuple(value / norm for value in vector)


def document_payload(prepared: PreparedDocument) -> dict[str, object]:
    """Create the persisted source record needed to reconstruct a story."""
    payload = prepared.document.as_dict()
    payload["input_fingerprint"] = prepared.encoded.input_fingerprint
    return payload


def updated_sparse_weights(
    old_weights: dict[str, float],
    new_weights: dict[str, float],
) -> dict[str, float]:
    """Maintain an element-wise maximum BGE-M3 sparse profile for a story."""
    keys = set(old_weights) | set(new_weights)
    return {
        key: max(float(old_weights.get(key, 0.0)), float(new_weights.get(key, 0.0)))
        for key in keys
    }


def create_singleton(prepared: PreparedDocument, now: datetime) -> StoryMetadata:
    """Create a deterministic active story containing one prepared document."""
    # Derive a stable ID so retries cannot create a second singleton.
    story_id = "story-" + hashlib.sha256(prepared.document.document_id.encode()).hexdigest()[:24]
    return StoryMetadata(
        story_id=story_id,
        status="active",
        representative_document_id=prepared.document.document_id,
        member_document_ids=[prepared.document.document_id],
        canonical_text=prepared.encoded.canonical_text,
        first_seen=prepared.document.published_at,
        latest_published_at=prepared.document.published_at,
        last_updated_at=now,
        document_count=1,
        source_count=1,
        entity_names=sorted({entity.canonical_name for entity in prepared.entities.entities}),
        category=prepared.document.category,
        centroid=normalized_centroid(list(prepared.encoded.dense_vector)),
        dense_sum=tuple(prepared.encoded.dense_vector),
        sparse_weights=dict(prepared.encoded.sparse_weights),
        member_documents=[document_payload(prepared)],
    )


def attach_document(
    story: StoryMetadata,
    prepared: PreparedDocument,
    now: datetime,
) -> StoryMetadata:
    """Return updated story state after attaching one new document."""
    if prepared.document.document_id in story.member_document_ids:
        return story
    old_count = story.document_count
    old_dense_sum = list(story.dense_sum or story.centroid or prepared.encoded.dense_vector)
    new_vector = list(prepared.encoded.dense_vector)
    if len(old_dense_sum) != len(new_vector):
        raise ValueError("document vector dimension does not match story dense sum")

    # Add the new vector to the unnormalized sum, then derive the exact mean centroid.
    dense_sum = [old_value + new_value for old_value, new_value in zip(old_dense_sum, new_vector)]
    centroid = normalized_centroid([value / (old_count + 1) for value in dense_sum])

    # Preserve all member records and update the newest display representative.
    member_documents = list(story.member_documents) + [document_payload(prepared)]
    latest = prepared.document.published_at >= story.latest_published_at
    entity_names = set(story.entity_names)
    entity_names.update(entity.canonical_name for entity in prepared.entities.entities)
    source_ids = {
        str(document.get("source_id"))
        for document in member_documents
        if document.get("source_id")
    }
    return StoryMetadata(
        story_id=story.story_id,
        status="active",
        representative_document_id=(
            prepared.document.document_id if latest else story.representative_document_id
        ),
        member_document_ids=list(story.member_document_ids) + [prepared.document.document_id],
        canonical_text=(prepared.encoded.canonical_text if latest else story.canonical_text),
        first_seen=min(story.first_seen, prepared.document.published_at),
        latest_published_at=max(story.latest_published_at, prepared.document.published_at),
        last_updated_at=now,
        document_count=old_count + 1,
        source_count=len(source_ids) or story.source_count,
        entity_names=sorted(entity_names),
        merged_story_ids=list(story.merged_story_ids),
        category=story.category or prepared.document.category,
        centroid=centroid,
        dense_sum=tuple(dense_sum),
        sparse_weights=updated_sparse_weights(
            story.sparse_weights,
            dict(prepared.encoded.sparse_weights),
        ),
        member_documents=member_documents,
    )
