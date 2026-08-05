"""Manual status check for the embedding stage."""

from __future__ import annotations

from headlyn_clustering.embedding import EmbeddingError
from pipeline import run_pipeline


def main() -> int:
    try:
        first = run_pipeline(split="test")
        second = run_pipeline(split="test")
    except EmbeddingError as exc:
        print(f"embedding_generation: failed ({exc})")
        return 1
    if first != second:
        print("embedding_generation: failed deterministic rerun check")
        return 1
    print("embedding_generation: passed")
    print(f"model: {first.metadata.model_name}")
    print(f"embeddings: {len(first.records)}")
    print(f"dimension: {first.metadata.dimension}")
    print(f"entities: {sum(len(record.entities) for record in first.records)}")
    print("deterministic rerun: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
