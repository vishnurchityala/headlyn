from __future__ import annotations

import csv
import json
import time
import urllib.request
from typing import Protocol, Sequence

from .canonical import build_canonical_text, document_fingerprint
from .models import EntityExtraction, ExtractedEntity, StoryDocument


PROMPT_VERSION = "entity-v2-csv"
SYSTEM_PROMPT = """You are extracting named entities from a news article's title and short description for the purpose of STORY CLUSTERING. Your output will be used to compute entity-overlap scores between articles — high recall and high precision both matter, since missed entities cause duplicate stories to stay unmerged, and spurious entities cause unrelated stories to merge incorrectly.

ENTITY TYPES TO EXTRACT (only if explicitly named in the text):
- PERSON: named individuals (full name or clearly identifying single name, e.g. "Zelensky", "Musk")
- ORGANIZATION: companies, agencies, institutions, political parties, sports teams, militant/rebel groups, courts
- LOCATION: countries, states, cities, regions, landmarks, venues, bodies of water — anything geographically specific
- PRODUCT/WORK: named products, apps, aircraft/ship/mission names, books, films, brands
- EVENT: named or clearly identifiable events — elections, wars, storms/hurricanes (by name), summits, tournaments, court cases, legislation/bills (by name or number), disasters
- MISC_PROPER_NOUN: any other proper noun central to the story that doesn't fit above (e.g. named laws, operations, awards)

EXTRACTION RULES:
1. Extract only entities explicitly present in the title or description text. Never infer an entity that isn't stated, even if it's strongly implied by context or general knowledge.
2. Normalize each entity to the most complete form it takes anywhere in the given text. If "Apple" and "Apple Inc." both appear, output "Apple Inc." once. If only "Apple" appears, output "Apple".
3. Resolve an alias/abbreviation to its canonical name ONLY if the full form also appears in the same text, or the abbreviation is globally unambiguous (e.g. "NASA", "FBI", "UN"). Do not resolve ambiguous short forms (e.g. a bare "the Fed" is fine to keep as-is; do not guess a person's full name from a surname alone).
4. Deduplicate: each distinct real-world entity appears exactly once in the output, regardless of how many times or in how many forms it's mentioned.
5. Do not extract:
   - Dates, times, durations, ages
   - Bare numbers, percentages, prices, statistics
   - Generic role/descriptor nouns without a proper name ("officials", "the company", "a spokesperson", "authorities", "the president" if unnamed)
   - Common nouns and generic event descriptors ("a protest", "the storm") unless they carry a proper name
   - Titles or honorifics alone without an attached proper name ("Dr.", "President" by itself)
6. Keep multi-word entities intact as a single CSV field — never split ("New York City" stays whole, not "New York" + "City").
7. Prefer the specific over the general when both appear: if "Federal Reserve" and "the Fed" both appear, output once using the fuller canonical form.
8. When text is very short (headline-only or one-line description), extract even single-mention entities — do not withhold entities due to low context; short text is expected and recall matters most here.
9. Order output entities by first appearance in the text (title first, then description).

OUTPUT FORMAT:
- Return only a single comma-separated CSV row of entity names. No header row.
- If no entities are found, return an empty response.
- Do not return JSON, arrays, entity type labels, explanations, reasoning, or markdown formatting of any kind.
- Do not wrap the output in quotes or code blocks.
"""


class EntityExtractor(Protocol):
    """Extract and canonicalize explicit entities from a story document."""

    model_name: str
    prompt_version: str

    def extract(self, document: StoryDocument) -> EntityExtraction:
        ...


class EntityCache(Protocol):
    """Persist and retrieve successful entity extraction results."""

    def get_many_entities(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        prompt_version: str,
    ) -> dict[str, EntityExtraction]:
        ...

    def upsert_entity(self, document: StoryDocument, extraction: EntityExtraction) -> None:
        ...


class CachedEntityExtractor(EntityExtractor):
    """Reuse compatible entity results and call the model only for cache misses."""

    def __init__(self, extractor: EntityExtractor, cache: EntityCache) -> None:
        """Configure a persistent cache around an entity extractor."""
        self.extractor = extractor
        self.cache = cache
        self.model_name = extractor.model_name
        self.prompt_version = extractor.prompt_version

    def extract(self, document: StoryDocument) -> EntityExtraction:
        """Return one cached extraction or generate and persist a cache miss."""
        try:
            cached = self.cache.get_many_entities(
                [document],
                model_name=self.model_name,
                prompt_version=self.prompt_version,
            )
        except Exception:
            cached = {}
        if document.document_id in cached:
            return cached[document.document_id]
        extraction = self.extractor.extract(document)
        if extraction.status == "ok":
            try:
                self.cache.upsert_entity(document, extraction)
            except Exception:
                pass
        return extraction

    def extract_many(self, documents: Sequence[StoryDocument]) -> dict[str, EntityExtraction]:
        """Bulk-load cache hits, extract misses, and persist successful results."""
        if not documents:
            return {}
        try:
            cached = self.cache.get_many_entities(
                documents,
                model_name=self.model_name,
                prompt_version=self.prompt_version,
            )
        except Exception:
            cached = {}
        # Call Ollama only for documents absent from the compatible cache.
        for document in documents:
            if document.document_id in cached:
                continue
            extraction = self.extractor.extract(document)
            cached[document.document_id] = extraction
            if extraction.status == "ok":
                try:
                    self.cache.upsert_entity(document, extraction)
                except Exception:
                    pass
        return cached


class OllamaEntityExtractor(EntityExtractor):
    """Call a local Ollama model for deterministic CSV entity extraction."""

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

                # Parse and validate the model's comma-separated entity response.
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
    """Parse a CSV entity list and remove duplicate names case-insensitively."""
    entities: list[ExtractedEntity] = []
    seen: set[str] = set()

    # Read CSV rows so entity names containing commas remain valid when quoted.
    for row in csv.reader(raw_output.splitlines()):
        for raw_entity in row:
            name = clean_value(raw_entity).strip("`\"'")
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            # Preserve the existing internal contract without asking the model for metadata.
            entities.append(ExtractedEntity(name, name, "OTHER", "secondary"))
    return entities


def clean_value(value: object) -> str:
    """Normalize arbitrary model field values to single-space text."""
    return " ".join(str(value or "").split())
