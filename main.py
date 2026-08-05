"""Run the Headlyn pipeline through embedding generation."""

from __future__ import annotations

from headlyn_clustering.embedding import EmbeddingError
from pipeline import run_pipeline


def main() -> int:
    try:
        embeddings = run_pipeline(split="test")
    except EmbeddingError as exc:
        print(f"embedding_generation: failed ({exc})")
        return 1
    entity_count = sum(len(record.entities) for record in embeddings.records)
    print(f"embedding_generation: passed ({len(embeddings.records)} embeddings, {entity_count} entities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
