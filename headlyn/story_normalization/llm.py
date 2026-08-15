from __future__ import annotations

import json
import urllib.request
from hashlib import sha256
from typing import Protocol

from .models import EntityExtraction, ExtractedEntity


SYSTEM_PROMPT = """You extract named entities from short news RSS items.

Return one JSON object with exactly this shape:
{
  "entities": [
    {
      "text": "text exactly as written",
      "canonical_name": "normalized name only when unambiguous",
      "type": "PERSON|ORG|GPE|LOC|EVENT|PRODUCT|LAW|OTHER",
      "role": "primary|secondary"
    }
  ]
}

Rules:
- Extract only entities explicitly present in the title or description.
- Do not infer facts, relationships, or entities.
- Mark people or organizations central to the reported event as primary.
- Mark contextual entities as secondary.
- Normalize clear aliases and honorifics, but do not guess ambiguous aliases.
- Return valid JSON only. Do not include markdown or explanation.
"""


class EntityExtractor(Protocol):
    model_name: str

    def extract(self, item: dict[str, object]) -> EntityExtraction:
        ...


class EntityExtractionError(RuntimeError):
    """Raised when the local LLM cannot return a valid extraction."""


class OllamaEntityExtractor:
    def __init__(
        self,
        *,
        model_name: str = "gemma4:e4b-it-q4_K_M",
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_seconds: int = 120,
    ) -> None:
        self.model_name = model_name
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def extract(self, item: dict[str, object]) -> EntityExtraction:
        article_id = str(item["article_id"])
        fingerprint = input_fingerprint(item)
        prompt = (
            "Title:\n"
            + str(item["title"])
            + "\n\nDescription:\n"
            + str(item["description"])
        )
        payload = {
            "model": self.model_name,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
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
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            raw_output = response_payload.get("response", "")
            parsed = parse_entity_response(raw_output)
        except Exception as exc:
            raise EntityExtractionError(
                f"local LLM extraction failed for {article_id}: {exc}"
            ) from exc
        return EntityExtraction(
            article_id=article_id,
            input_fingerprint=fingerprint,
            model=self.model_name,
            status="ok",
            entities=tuple(parsed),
        )


def parse_entity_response(raw_output: str) -> list[ExtractedEntity]:
    try:
        value = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise EntityExtractionError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("entities"), list):
        raise EntityExtractionError("LLM response must contain an entities list")

    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()
    for raw_entity in value["entities"]:
        if not isinstance(raw_entity, dict):
            continue
        text = clean_value(raw_entity.get("text"))
        canonical_name = clean_value(raw_entity.get("canonical_name")) or text
        entity_type = clean_value(raw_entity.get("type")).upper() or "OTHER"
        role = clean_value(raw_entity.get("role")).lower() or "secondary"
        if not text or not canonical_name:
            continue
        if role not in {"primary", "secondary"}:
            role = "secondary"
        key = (canonical_name.casefold(), entity_type)
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            ExtractedEntity(
                text=text,
                canonical_name=canonical_name,
                entity_type=entity_type,
                role=role,
            )
        )
    return entities


def input_fingerprint(item: dict[str, object]) -> str:
    content = f"{item.get('title', '')}\n{item.get('description', '')}"
    return sha256(content.encode("utf-8")).hexdigest()


def clean_value(value: object) -> str:
    return " ".join(str(value or "").split())
