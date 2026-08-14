"""Pipeline entry point for the dataset-loading stage."""

from __future__ import annotations

from pathlib import Path

from .data import load_dataset
from .hybrid_candidate import retrieve_candidates
from .models import (
    CandidateRetrievalConfig,
    CandidateSet,
    Dataset,
    EmbeddingSet,
    PairScoringConfig,
    ScoredCandidateSet,
)
from .scoring import score_candidates


def run_dataset_stage(path: str | Path, split: str | None = "test") -> Dataset:
    """Return the deterministic output of the dataset-loading stage."""

    return load_dataset(path, split=split)


def run_candidate_stage(
    embeddings: EmbeddingSet,
    config: CandidateRetrievalConfig | None = None,
) -> CandidateSet:
    """Return the deterministic hybrid-retrieval output for an embedding set."""

    return retrieve_candidates(embeddings, config or CandidateRetrievalConfig())


def run_scoring_stage(
    dataset: Dataset,
    embeddings: EmbeddingSet,
    candidates: CandidateSet,
    config: PairScoringConfig | None = None,
) -> ScoredCandidateSet:
    """Return the deterministic precision-scoring output."""

    return score_candidates(dataset, embeddings, candidates, config or PairScoringConfig())
