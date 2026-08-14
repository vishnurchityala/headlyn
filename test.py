"""Manual status check for the hybrid candidate-retrieval stage."""

from __future__ import annotations

from headlyn_clustering.embedding import EmbeddingError
from headlyn_clustering.hybrid_candidate import CandidateRetrievalError
from headlyn_clustering.scoring import PairScoringError
from pipeline import run_pipeline


def main() -> int:
    try:
        first = run_pipeline(split="test")
        second = run_pipeline(split="test")
    except (EmbeddingError, CandidateRetrievalError, PairScoringError) as exc:
        print(f"pair_scoring: failed ({exc})")
        return 1
    if first != second:
        print("pair_scoring: failed deterministic rerun check")
        return 1
    if any(candidate.article_a >= candidate.article_b for candidate in first.candidates):
        print("pair_scoring: failed non-canonical pair ordering")
        return 1
    if any(
        candidate.article_a == candidate.article_b
        for candidate in first.candidates
    ):
        print("pair_scoring: failed self-match exclusion")
        return 1
    if not any(
        evidence.retriever == "chunk_semantic"
        for candidate in first.candidates
        for evidence in candidate.retrieval_evidence
    ):
        print("pair_scoring: failed chunk retrieval evidence check")
        return 1
    print("pair_scoring: passed")
    print(f"articles: {len(first.article_ids)}")
    print(f"scored pairs: {len(first.candidates)}")
    print(f"accepted pairs: {sum(candidate.accepted for candidate in first.candidates)}")
    print(
        "chunk evidence: "
        f"{sum(evidence.retriever == 'chunk_semantic' for candidate in first.candidates for evidence in candidate.retrieval_evidence)}"
    )
    print("deterministic rerun: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
