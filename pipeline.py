"""Default Headlyn pipeline assembly."""

from __future__ import annotations

from pathlib import Path

from headlyn_clustering.data import load_dataset
from headlyn_clustering.embedding import generate_embeddings
from headlyn_clustering.hybrid_candidate import retrieve_candidates
from headlyn_clustering.models import (
    CandidateRetrievalConfig,
    EmbeddingConfig,
    PairScoringConfig,
    ScoredCandidateSet,
)
from headlyn_clustering.scoring import score_candidates


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = ROOT_DIR / "assets" / "datasets" / "articles" / "clustering-evaluation.json"


def run_pipeline(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    split: str | None = "test",
    candidate_config: CandidateRetrievalConfig | None = None,
    scoring_config: PairScoringConfig | None = None,
) -> ScoredCandidateSet:
    """Run the complete implemented pipeline through pair scoring."""

    dataset = load_dataset(dataset_path, split=split)
    embeddings = generate_embeddings(
        dataset,
        EmbeddingConfig(
            cache_dir=ROOT_DIR / "artifacts" / "stages" / "embedding",
            chunk_artifact_dir=ROOT_DIR / "artifacts" / "stages" / "chunking",
        ),
    )
    retrieval_config = candidate_config or CandidateRetrievalConfig(
        artifact_dir=ROOT_DIR / "artifacts" / "stages" / "candidate_retrieval"
    )
    candidates = retrieve_candidates(embeddings, retrieval_config)
    scoring_config = scoring_config or PairScoringConfig(
        artifact_dir=ROOT_DIR / "artifacts" / "stages" / "pair_scoring"
    )
    return score_candidates(dataset, embeddings, candidates, scoring_config)
