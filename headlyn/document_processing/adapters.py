from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Protocol
from urllib.parse import urlsplit

from .models import StoryDocument


class DocumentAdapter(Protocol):
    """Convert one source-specific payload into a validated story document."""

    def adapt(self, value: Mapping[str, object]) -> StoryDocument:
        ...


def parse_timestamp(value: object, field: str) -> datetime:
    """Parse a timezone-aware ISO-8601 timestamp and normalize it to UTC."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {text}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def required_text(value: object, field: str) -> str:
    """Return normalized non-empty text or raise a field-specific validation error."""
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError(f"{field} is required")
    return text


def validate_url(value: object) -> str:
    """Validate that a value is an absolute HTTP or HTTPS URL."""
    url = required_text(value, "url")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("url must be an absolute http(s) URL")
    return url


def labels_from(value: object) -> tuple[str, ...]:
    """Normalize an optional list of labels or tags into an immutable tuple."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("labels/tags must be a list")
    return tuple(" ".join(str(item).split()) for item in value if str(item).strip())


class RssArticleAdapter(DocumentAdapter):
    """Adapt the existing normalized RSS article payload."""

    def adapt(self, value: Mapping[str, object]) -> StoryDocument:
        """Validate RSS fields and map ``article_id`` to ``document_id``."""
        # Normalize the required identity and content fields first.
        document_id = required_text(value.get("article_id"), "article_id")
        title = required_text(value.get("title"), "title")
        description = " ".join(str(value.get("description") or "").split()) or title

        # Build one generic document while preserving the original source payload.
        return StoryDocument(
            document_id=document_id,
            document_type="article",
            title=title,
            body_text=description,
            source_id=required_text(value.get("source_id"), "source_id"),
            source_name=required_text(value.get("source_name"), "source_name"),
            published_at=parse_timestamp(value.get("published_at"), "published_at"),
            ingested_at=parse_timestamp(value.get("ingested_at"), "ingested_at"),
            url=validate_url(value.get("url")),
            scope=str(value.get("scope") or "").strip() or None,
            category=str(value.get("category") or "").strip() or None,
            labels=labels_from(value.get("tags")),
            original_metadata=dict(value),
        )


class VideoDocumentAdapter(DocumentAdapter):
    """Adapt an already-sourced video with a transcript-derived summary."""

    def adapt(self, value: Mapping[str, object]) -> StoryDocument:
        """Validate a pre-sourced video and require its transcript summary."""
        # Validate the explicit document type and required video identity.
        document_id = required_text(value.get("document_id"), "document_id")
        if str(value.get("document_type", "video")).lower() != "video":
            raise ValueError("video input must have document_type=video")

        # Map the transcript-derived summary into the shared body_text field.
        return StoryDocument(
            document_id=document_id,
            document_type="video",
            title=required_text(value.get("title"), "title"),
            body_text=required_text(value.get("summary"), "summary"),
            source_id=required_text(value.get("source_id"), "source_id"),
            source_name=required_text(value.get("source_name"), "source_name"),
            published_at=parse_timestamp(value.get("published_at"), "published_at"),
            ingested_at=parse_timestamp(value.get("ingested_at"), "ingested_at"),
            url=validate_url(value.get("url")),
            scope=str(value.get("scope") or "").strip() or None,
            category=str(value.get("category") or "").strip() or None,
            labels=labels_from(value.get("labels")),
            original_metadata=dict(value),
        )
