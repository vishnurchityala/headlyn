"""Headlyn's batch clustering pipeline package."""

from .embedding import EmbeddingError, generate_embeddings
from .hybrid_candidate import CandidateRetrievalError, retrieve_candidates
from .scoring import PairScoringError, score_candidates
from .chunking import chunk_article, chunk_dataset, write_chunk_artifacts
from .models import (
    Article,
    ArticleChunk,
    CandidateEvidence,
    CandidatePair,
    CandidateRetrievalConfig,
    CandidateSet,
    ChunkEmbeddingRecord,
    Dataset,
    EmbeddingConfig,
    EmbeddingMetadata,
    EmbeddingRecord,
    EmbeddingSet,
    Entity,
    GoldLabel,
    PairFeatures,
    PairScoringConfig,
    ScoredCandidate,
    ScoredCandidateSet,
)
from .pipeline import run_candidate_stage, run_dataset_stage, run_scoring_stage

__all__ = [
    "Article",
    "ArticleChunk",
    "CandidateEvidence",
    "CandidatePair",
    "CandidateRetrievalConfig",
    "CandidateRetrievalError",
    "CandidateSet",
    "ChunkEmbeddingRecord",
    "Dataset",
    "EmbeddingConfig",
    "EmbeddingError",
    "EmbeddingMetadata",
    "EmbeddingRecord",
    "EmbeddingSet",
    "Entity",
    "GoldLabel",
    "PairFeatures",
    "PairScoringConfig",
    "PairScoringError",
    "ScoredCandidate",
    "ScoredCandidateSet",
    "generate_embeddings",
    "chunk_article",
    "chunk_dataset",
    "retrieve_candidates",
    "run_candidate_stage",
    "run_dataset_stage",
    "run_scoring_stage",
    "score_candidates",
    "write_chunk_artifacts",
]
