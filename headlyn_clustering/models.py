"""Small deterministic contracts for the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Article:
    """Runtime article data exposed to later pipeline stages.

    Gold-evaluation fields intentionally do not belong on this model.
    """

    article_id: str
    source: str
    url: str
    title: str
    description: str
    published_at: datetime
    paragraphs: tuple[str, ...]
    clean_text: str


@dataclass(frozen=True)
class GoldLabel:
    """Evaluation-only metadata kept outside :class:`Article`."""

    article_id: str
    cluster_id: str
    group: str
    topic: str
    split: str
    hard_negative_for: tuple[str, ...]


@dataclass(frozen=True)
class Dataset:
    """The complete output of the dataset-loading stage.

    ``articles`` and ``labels`` preserve the same order and have matching
    ``article_id`` values. Later stages consume this model directly.
    """

    articles: tuple[Article, ...]
    gold_labels: tuple[GoldLabel, ...]
    split: str | None = None


@dataclass(frozen=True)
class Entity:
    surface: str
    canonical: str
    type: str


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "BAAI/bge-small-en-v1.5"
    revision: str = "main"
    device: str = "cpu"
    dimension: int = 384
    batch_size: int = 16
    normalize_embeddings: bool = True
    input_version: str = "title-description-clean-text-v1"
    lexical_version: str = "bm25-v1"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    title_weight: float = 3.0
    description_weight: float = 2.0
    body_weight: float = 1.0
    entity_model: str = "en_core_web_sm"
    entity_version: str = "spacy-entity-v1"
    entity_alias_version: str = "aliases-v1"
    entity_types: str = "EVENT,GPE,LAW,LOC,ORG,PERSON,PRODUCT"
    cache_dir: Path = Path("artifacts/cache/embeddings")


@dataclass(frozen=True)
class EmbeddingMetadata:
    model_name: str
    revision: str
    dimension: int
    normalized: bool
    input_version: str
    lexical_version: str
    lexical_vocabulary_hash: str
    bm25_k1: float
    bm25_b: float
    title_weight: float
    description_weight: float
    body_weight: float
    entity_model: str
    entity_version: str
    entity_alias_version: str
    entity_types: str


@dataclass(frozen=True)
class EmbeddingRecord:
    article_id: str
    input_hash: str
    vector: tuple[float, ...]
    lexical_weights: tuple[tuple[str, float], ...]
    entities: tuple[Entity, ...]


@dataclass(frozen=True)
class EmbeddingSet:
    """The complete output of the embedding stage."""

    metadata: EmbeddingMetadata
    records: tuple[EmbeddingRecord, ...]
