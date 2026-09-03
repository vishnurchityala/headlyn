from __future__ import annotations

import hashlib
import html
import re

from .models import StoryDocument


TAG_RE = re.compile(r"<[^>]+>")
CANONICALIZATION_VERSION = "canonical-v1"


def clean_text(value: str) -> str:
    """Remove simple markup, decode entities, and normalize whitespace."""
    unescaped = html.unescape(value or "")
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", unescaped)).strip()


def build_canonical_text(document: StoryDocument) -> str:
    """Build the single text representation shared by models and fingerprints."""
    # Clean both fields so model inputs are stable across source formatting.
    title = clean_text(document.title)
    body = clean_text(document.body_text) or title

    # Keep field labels to make title/content boundaries explicit to the models.
    return f"Title: {title}\n\nContent: {body}"


def document_fingerprint(document: StoryDocument) -> str:
    """Create a stable hash for the canonical document-processing input."""
    # Hash the canonicalization version and document type with the model text.
    canonical = build_canonical_text(document)
    value = f"{CANONICALIZATION_VERSION}\n{document.document_type}\n{canonical}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
