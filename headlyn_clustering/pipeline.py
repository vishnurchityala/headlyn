"""Pipeline entry point for the dataset-loading stage."""

from __future__ import annotations

from pathlib import Path

from .data import load_dataset
from .models import Dataset


def run_dataset_stage(path: str | Path, split: str | None = "test") -> Dataset:
    """Return the deterministic output of the dataset-loading stage."""

    return load_dataset(path, split=split)
