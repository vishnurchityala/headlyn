"""Default Headlyn pipeline assembly."""

from __future__ import annotations

from pathlib import Path

from headlyn_clustering.models import Dataset
from headlyn_clustering.pipeline import run_dataset_stage


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = ROOT_DIR / "assets" / "datasets" / "articles" / "clustering-evaluation.json"


def run_pipeline(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    split: str | None = "test",
) -> Dataset:
    """Run the currently implemented dataset-loading stage."""

    return run_dataset_stage(dataset_path, split=split)
