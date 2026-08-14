"""Run the Headlyn pipeline through hybrid candidate retrieval."""

from __future__ import annotations

from headlyn_clustering.embedding import EmbeddingError
from headlyn_clustering.hybrid_candidate import CandidateRetrievalError
from headlyn_clustering.scoring import PairScoringError
from pipeline import run_pipeline


def main() -> int:
    try:
        scored = run_pipeline(split="test")
    except (EmbeddingError, CandidateRetrievalError, PairScoringError) as exc:
        print(f"pair_scoring: failed ({exc})")
        return 1
    accepted = sum(candidate.accepted for candidate in scored.candidates)
    print(
        "pair_scoring: passed "
        f"({len(scored.article_ids)} articles, "
        f"{len(scored.candidates)} scored pairs, {accepted} accepted)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
