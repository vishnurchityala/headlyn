"""Default Headlyn pipeline assembly."""

from __future__ import annotations

from pathlib import Path

from headlyn_clustering.embedding import generate_embeddings
from headlyn_clustering.models import Dataset, EmbeddingConfig, EmbeddingSet
from headlyn_clustering.pipeline import run_dataset_stage


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = ROOT_DIR / "assets" / "datasets" / "articles" / "clustering-evaluation.json"


def run_pipeline(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    split: str | None = "test",
) -> EmbeddingSet:
    """Run dataset loading followed by embedding generation."""

    dataset = run_dataset_stage(dataset_path, split=split)
    config = EmbeddingConfig(cache_dir=ROOT_DIR / "artifacts" / "cache" / "embeddings")
    return generate_embeddings(dataset, config)
