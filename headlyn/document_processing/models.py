from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Mapping


DocumentType = Literal["article", "video"]


@dataclass(frozen=True)
class StoryDocument:
    """Common validated representation for article and pre-sourced video inputs."""

    document_id: str
    document_type: DocumentType
    title: str
    body_text: str
    source_id: str
    source_name: str
    published_at: datetime
    ingested_at: datetime
    url: str
    scope: str | None = None
    category: str | None = None
    labels: tuple[str, ...] = ()
    original_metadata: Mapping[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize the document while retaining source metadata for inspection."""
        value: dict[str, object] = {
            "document_id": self.document_id,
            "document_type": self.document_type,
            "title": self.title,
            "body_text": self.body_text,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "published_at": self.published_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "url": self.url,
            "scope": self.scope,
            "category": self.category,
            "labels": list(self.labels),
        }
        if self.original_metadata is not None:
            value["original_metadata"] = dict(self.original_metadata)
        return value


@dataclass(frozen=True)
class EncodedDocument:
    """Model features generated from one canonical story document."""

    document_id: str
    input_fingerprint: str
    canonical_text: str
    dense_vector: tuple[float, ...]
    sparse_weights: Mapping[str, float]
    model_name: str
    max_length: int

    def as_dict(self) -> dict[str, object]:
        """Serialize dense and sparse features for downstream indexing."""
        return {
            "document_id": self.document_id,
            "input_fingerprint": self.input_fingerprint,
            "canonical_text": self.canonical_text,
            "dense_vector": list(self.dense_vector),
            "sparse_weights": dict(self.sparse_weights),
            "model_name": self.model_name,
            "max_length": self.max_length,
        }


@dataclass(frozen=True)
class ExtractedEntity:
    """One explicitly mentioned entity with a canonical name, type, and role."""

    text: str
    canonical_name: str
    entity_type: str
    role: str

    def as_dict(self) -> dict[str, str]:
        """Serialize the entity using the LLM schema field names."""
        return {
            "text": self.text,
            "canonical_name": self.canonical_name,
            "type": self.entity_type,
            "role": self.role,
        }


@dataclass(frozen=True)
class EntityExtraction:
    """Entity extraction result, including model and prompt provenance."""

    document_id: str
    input_fingerprint: str
    model: str
    prompt_version: str
    status: Literal["ok", "failed"]
    entities: tuple[ExtractedEntity, ...] = ()
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize extraction output with article compatibility metadata."""
        value: dict[str, object] = {
            "document_id": self.document_id,
            "input_fingerprint": self.input_fingerprint,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "status": self.status,
            "entities": [entity.as_dict() for entity in self.entities],
            "error": self.error,
        }
        if self.document_id.startswith("article-"):
            value["article_id"] = self.document_id
        return value


@dataclass(frozen=True)
class DocumentPreparationConfig:
    """Runtime configuration for document preparation and model execution."""

    ingestion_run_id: str
    artifact_root: Path | None = None
    source_ids: tuple[str, ...] | None = None
    video_input: Path | None = None
    embedding_model: str = "BAAI/bge-m3"
    entity_model: str = "gemma4:e4b-it-q4_K_M"
    entity_prompt_version: str = "entity-v1"
    llm_endpoint: str = "http://127.0.0.1:11434/api/generate"
    llm_timeout_seconds: int = 120
    llm_retries: int = 2
    embedding_batch_size: int = 16
    embedding_max_length: int = 512
    embedding_vector_size: int = 1024
    use_fp16: bool = False
    output_dir: Path | None = None


@dataclass(frozen=True)
class DocumentPreparationResult:
    """Summary handle returned after preparation artifacts are written."""

    ingestion_run_id: str
    status: str
    input_count: int
    successful_count: int
    output_dir: Path
    summary_path: Path
