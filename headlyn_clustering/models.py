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
class ArticleChunk:
    """A deterministic, semantically focused section of an article."""

    article_id: str
    chunk_id: str
    chunk_type: str
    text: str
    paragraph_start: int
    paragraph_end: int
    token_count: int


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    revision: str = "main"
    device: str = "cpu"
    dimension: int = 1024
    batch_size: int = 16
    normalize_embeddings: bool = True
    input_version: str = "qwen3-title-description-clean-text-title-representation-v1"
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
    cache_dir: Path = Path("artifacts/stages/embedding")
    chunk_size_tokens: int = 384
    chunk_overlap_tokens: int = 64
    max_chunks_per_article: int = 32
    chunk_artifact_dir: Path = Path("artifacts/stages/chunking")


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
    chunk_size_tokens: int = 384
    chunk_overlap_tokens: int = 64
    max_chunks_per_article: int = 32


@dataclass(frozen=True)
class EmbeddingRecord:
    article_id: str
    input_hash: str
    vector: tuple[float, ...]
    lexical_weights: tuple[tuple[str, float], ...]
    entities: tuple[Entity, ...]
    title_representation: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class ChunkEmbeddingRecord:
    """Semantic embedding and entities for one article chunk."""

    article_id: str
    chunk_id: str
    input_hash: str
    vector: tuple[float, ...]
    entities: tuple[Entity, ...]


@dataclass(frozen=True)
class EmbeddingSet:
    """The complete output of the embedding stage."""

    metadata: EmbeddingMetadata
    records: tuple[EmbeddingRecord, ...]
    chunks: tuple[ChunkEmbeddingRecord, ...] = ()


@dataclass(frozen=True)
class CandidateRetrievalConfig:
    """Configuration for the batch hybrid candidate-retrieval stage."""

    top_k: int = 8
    version: str = "hybrid-candidate-v2-chunk"
    artifact_dir: Path = Path("artifacts/stages/candidate_retrieval")
    chunk_top_k: int = 4
    max_chunk_evidence_per_pair: int = 4


@dataclass(frozen=True)
class CandidateEvidence:
    """One directed retrieval result retained as pair evidence."""

    query_article_id: str
    candidate_article_id: str
    retriever: str
    rank: int
    score: float
    query_chunk_id: str | None = None
    candidate_chunk_id: str | None = None


@dataclass(frozen=True)
class CandidatePair:
    """A canonical undirected pair with all retrieval evidence preserved."""

    article_a: str
    article_b: str
    evidence: tuple[CandidateEvidence, ...]


@dataclass(frozen=True)
class CandidateSet:
    """The deduplicated output of hybrid candidate retrieval."""

    article_ids: tuple[str, ...]
    pairs: tuple[CandidatePair, ...]
    config: CandidateRetrievalConfig


@dataclass(frozen=True)
class PairScoringConfig:
    """Weights and guardrails for precision-oriented pair scoring."""

    semantic_weight: float = 0.40
    lexical_weight: float = 0.40
    title_weight: float = 0.10
    entity_weight: float = 0.05
    temporal_weight: float = 0.05
    acceptance_threshold: float = 0.4
    temporal_decay_hours: float = 72.0
    same_source_penalty: float = 0.05
    chunk_match_threshold: float = 0.65
    version: str = "pair-scoring-v1"
    artifact_dir: Path = Path("artifacts/stages/pair_scoring")


@dataclass(frozen=True)
class PairFeatures:
    """Normalized comparison features for one candidate pair."""

    semantic_similarity: float
    lexical_similarity: float
    title_similarity: float
    entity_overlap: float
    temporal_similarity: float
    source_relationship: str
    source_penalty: float
    global_semantic_similarity: float = 0.0
    chunk_semantic_similarity: float = 0.0
    chunk_best_match: float = 0.0
    chunk_top2_mean: float = 0.0
    chunk_bidirectional_coverage: float = 0.0
    chunk_match_count: int = 0


@dataclass(frozen=True)
class ScoredCandidate:
    """Precision decision and evidence for one candidate pair."""

    article_a: str
    article_b: str
    features: PairFeatures
    final_score: float
    accepted: bool
    rejection_reason: str | None
    retrieval_evidence: tuple[CandidateEvidence, ...]


@dataclass(frozen=True)
class ScoredCandidateSet:
    """The complete output of pair scoring."""

    article_ids: tuple[str, ...]
    candidates: tuple[ScoredCandidate, ...]
    config: PairScoringConfig
