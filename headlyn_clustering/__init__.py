"""Headlyn's batch clustering pipeline package."""

from .embedding import EmbeddingError, generate_embeddings
from .models import (
    Article,
    Dataset,
    EmbeddingConfig,
    EmbeddingMetadata,
    EmbeddingRecord,
    EmbeddingSet,
    Entity,
    GoldLabel,
)
from .pipeline import run_dataset_stage

__all__ = [
    "Article",
    "Dataset",
    "EmbeddingConfig",
    "EmbeddingError",
    "EmbeddingMetadata",
    "EmbeddingRecord",
    "EmbeddingSet",
    "Entity",
    "GoldLabel",
    "generate_embeddings",
    "run_dataset_stage",
]
