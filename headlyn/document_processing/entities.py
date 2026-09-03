from __future__ import annotations

import json
import time
import urllib.request
from typing import Protocol

from .canonical import build_canonical_text, document_fingerprint
from .models import EntityExtraction, ExtractedEntity, StoryDocument


PROMPT_VERSION = "entity-v1"
SYSTEM_PROMPT = """You extract named entities from short news documents.

Return JSON with exactly this shape:
{"entities":[{"text":"...","canonical_name":"...","type":"PERSON|ORG|GPE|LOC|EVENT|PRODUCT|LAW|OTHER","role":"primary|secondary"}]}

Rules:
- Extract only entities explicitly present in the title or content.
- Do not infer facts, relationships, or entities.
- Mark people or organizations central to the reported event as primary.
- Mark contextual entities as secondary.
- Normalize clear aliases only when unambiguous.
- Return valid JSON only. Do not include markdown or explanation.
"""


class EntityExtractor(Protocol):
    """Extract and canonicalize explicit entities from a story document."""

    model_name: str
    prompt_version: str

    def extract(self, document: StoryDocument) -> EntityExtraction:
        ...


class OllamaEntityExtractor(EntityExtractor):
    """Call a local Ollama model for deterministic JSON entity extraction."""

    def __init__(
        self,
        *,
        model_name: str = "gemma4:e4b-it-q4_K_M",
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_seconds: int = 120,
        retries: int = 2,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        """Validate request settings and configure the reusable Ollama client."""
        if timeout_seconds < 1 or retries < 0:
            raise ValueError("timeout_seconds must be positive and retries non-negative")
        self.model_name = model_name
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.prompt_version = prompt_version

    def extract(self, document: StoryDocument) -> EntityExtraction:
        """Extract entities, retry transient failures, and return a typed result."""
        # Construct a deterministic request from the shared canonical text.
        payload = {
            "model": self.model_name,
            "system": SYSTEM_PROMPT,
            "prompt": build_canonical_text(document),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                # Send one non-streaming JSON request to the local model endpoint.
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    response_payload = json.loads(response.read().decode("utf-8"))

                # Parse and validate the model's strict entity response.
                parsed = parse_entity_response(response_payload.get("response", ""))
                return EntityExtraction(
                    document_id=document.document_id,
                    input_fingerprint=document_fingerprint(document),
                    model=self.model_name,
                    prompt_version=self.prompt_version,
                    status="ok",
                    entities=tuple(parsed),
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                # Retry bounded failures, then preserve the final error for diagnostics.
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 4))
        return EntityExtraction(
            document_id=document.document_id,
            input_fingerprint=document_fingerprint(document),
            model=self.model_name,
            prompt_version=self.prompt_version,
            status="failed",
            error=f"{type(last_error).__name__}: {last_error}",
        )


def parse_entity_response(raw_output: str) -> list[ExtractedEntity]:
    """Parse strict entity JSON, validate fields, and remove duplicate entities."""
    value = json.loads(raw_output)
    if not isinstance(value, dict) or not isinstance(value.get("entities"), list):
        raise ValueError("LLM response must contain an entities list")
    allowed_types = {"PERSON", "ORG", "GPE", "LOC", "EVENT", "PRODUCT", "LAW", "OTHER"}
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    # Validate and normalize each model-returned entity independently.
    for raw_entity in value["entities"]:
        if not isinstance(raw_entity, dict):
            raise ValueError("each entity must be an object")
        text = clean_value(raw_entity.get("text"))
        canonical = clean_value(raw_entity.get("canonical_name")) or text
        entity_type = clean_value(raw_entity.get("type")).upper() or "OTHER"
        role = clean_value(raw_entity.get("role")).lower() or "secondary"
        if not text or not canonical:
            raise ValueError("entity text and canonical_name are required")
        if entity_type not in allowed_types:
            entity_type = "OTHER"
        if role not in {"primary", "secondary"}:
            raise ValueError("entity role must be primary or secondary")
        key = (canonical.casefold(), entity_type)
        if key in seen:
            continue
        seen.add(key)
        entities.append(ExtractedEntity(text, canonical, entity_type, role))
    return entities


def clean_value(value: object) -> str:
    """Normalize arbitrary model field values to single-space text."""
    return " ".join(str(value or "").split())
