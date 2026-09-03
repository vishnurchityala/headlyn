from __future__ import annotations

from datetime import datetime
from typing import Mapping

from headlyn.document_processing.models import (
    EncodedDocument,
    EntityExtraction,
    ExtractedEntity,
    StoryDocument,
)
from headlyn.document_processing.canonical import document_fingerprint

from .models import PreparedDocument


def parse_datetime(value: object, field: str) -> datetime:
    """Parse a timezone-aware serialized timestamp."""
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def prepared_document_from_dict(value: Mapping[str, object]) -> PreparedDocument:
    """Deserialize and validate one document-preparation feature record."""
    document_value = value.get("document")
    embedding_value = value.get("embedding")
    entity_value = value.get("entities")
    if not isinstance(document_value, dict) or not isinstance(embedding_value, dict) or not isinstance(entity_value, dict):
        raise ValueError("feature record must contain document, embedding, and entities objects")

    # Reconstruct the normalized document contract.
    document = StoryDocument(
        document_id=str(document_value["document_id"]),
        document_type=str(document_value["document_type"]),
        title=str(document_value["title"]),
        body_text=str(document_value["body_text"]),
        source_id=str(document_value["source_id"]),
        source_name=str(document_value["source_name"]),
        published_at=parse_datetime(document_value["published_at"], "published_at"),
        ingested_at=parse_datetime(document_value["ingested_at"], "ingested_at"),
        url=str(document_value["url"]),
        scope=str(document_value.get("scope") or "") or None,
        category=str(document_value.get("category") or "") or None,
        labels=tuple(str(item) for item in document_value.get("labels", [])),
        original_metadata=document_value.get("original_metadata"),
    )

    # Reconstruct the dense/sparse embedding output and check document identity.
    if str(embedding_value.get("document_id")) != document.document_id:
        raise ValueError("embedding document_id does not match document")
    encoded = EncodedDocument(
        document_id=document.document_id,
        input_fingerprint=str(embedding_value["input_fingerprint"]),
        canonical_text=str(embedding_value["canonical_text"]),
        dense_vector=tuple(float(item) for item in embedding_value["dense_vector"]),
        sparse_weights={str(key): float(item) for key, item in dict(embedding_value["sparse_weights"]).items()},
        model_name=str(embedding_value["model_name"]),
        max_length=int(embedding_value["max_length"]),
    )
    if not encoded.dense_vector:
        raise ValueError("dense vector must not be empty")

    # Reconstruct entities while preserving extraction failure status.
    entities = tuple(
        ExtractedEntity(
            text=str(item["text"]),
            canonical_name=str(item["canonical_name"]),
            entity_type=str(item.get("type", "OTHER")),
            role=str(item.get("role", "secondary")),
        )
        for item in entity_value.get("entities", [])
    )
    extraction = EntityExtraction(
        document_id=document.document_id,
        input_fingerprint=str(entity_value["input_fingerprint"]),
        model=str(entity_value["model"]),
        prompt_version=str(entity_value["prompt_version"]),
        status=str(entity_value.get("status", "failed")),
        entities=entities,
        error=entity_value.get("error"),
    )
    if extraction.input_fingerprint != encoded.input_fingerprint:
        raise ValueError("embedding and entity fingerprints do not match")
    if encoded.input_fingerprint != document_fingerprint(document):
        raise ValueError("prepared feature fingerprint does not match document content")
    return PreparedDocument(document=document, encoded=encoded, entities=extraction)
