from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoryNormalizationConfig:
    ingestion_run_id: str
    artifact_root: Path | None = None
    source_ids: tuple[str, ...] | None = None
    max_items_per_source: int | None = None
    entity_model: str = "gemma4:e4b-it-q4_K_M"
    llm_endpoint: str = "http://127.0.0.1:11434/api/generate"
    llm_timeout_seconds: int = 120
    lexical_model: str = "BAAI/bge-m3"
    lexical_batch_size: int = 16
    lexical_max_length: int = 512
    use_fp16: bool = False
    entity_weight: float = 0.5
    lexical_weight: float = 0.5
    merge_threshold: float = 0.5
    require_primary_entity: bool = True


@dataclass(frozen=True)
class ExtractedEntity:
    text: str
    canonical_name: str
    entity_type: str
    role: str

    def as_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "canonical_name": self.canonical_name,
            "type": self.entity_type,
            "role": self.role,
        }


@dataclass(frozen=True)
class EntityExtraction:
    article_id: str
    input_fingerprint: str
    model: str
    status: str
    entities: tuple[ExtractedEntity, ...] = ()
    error: str | None = None

    @property
    def primary_entities(self) -> frozenset[str]:
        return frozenset(
            entity.canonical_name.casefold()
            for entity in self.entities
            if entity.role == "primary"
        )

    @property
    def distinctive_primary_entities(self) -> frozenset[str]:
        distinctive_types = {"PERSON", "ORG", "EVENT", "PRODUCT", "LAW"}
        return frozenset(
            entity.canonical_name.casefold()
            for entity in self.entities
            if entity.role == "primary" and entity.entity_type in distinctive_types
        )

    @property
    def all_entities(self) -> frozenset[str]:
        return frozenset(entity.canonical_name.casefold() for entity in self.entities)

    def as_dict(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "input_fingerprint": self.input_fingerprint,
            "model": self.model,
            "status": self.status,
            "entities": [entity.as_dict() for entity in self.entities],
            "error": self.error,
        }


@dataclass(frozen=True)
class PairScore:
    article_id_a: str
    article_id_b: str
    source_id_a: str
    source_id_b: str
    shared_entities: tuple[str, ...]
    entity_score: float
    lexical_score: float | None
    final_score: float | None
    accepted: bool
    rejection_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "article_id_a": self.article_id_a,
            "article_id_b": self.article_id_b,
            "source_id_a": self.source_id_a,
            "source_id_b": self.source_id_b,
            "shared_entities": list(self.shared_entities),
            "entity_score": self.entity_score,
            "lexical_score": self.lexical_score,
            "final_score": self.final_score,
            "accepted": self.accepted,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class StoryNormalizationResult:
    ingestion_run_id: str
    status: str
    item_count: int
    story_count: int
    output_dir: Path
    summary_path: Path
