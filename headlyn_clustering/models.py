"""Small deterministic contracts for the pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Article:
    """Runtime article data exposed to later pipeline stages.

    Gold-evaluation fields intentionally do not belong on this model.
    """

    article_id: str
    source: str
    url: str
    title: str
    description: str
    published_at: datetime
    paragraphs: tuple[str, ...]
    clean_text: str


@dataclass(frozen=True)
class GoldLabel:
    """Evaluation-only metadata kept outside :class:`Article`."""

    article_id: str
    cluster_id: str
    group: str
    topic: str
    split: str
    hard_negative_for: tuple[str, ...]


@dataclass(frozen=True)
class Dataset:
    """The complete output of the dataset-loading stage.

    ``articles`` and ``labels`` preserve the same order and have matching
    ``article_id`` values. Later stages consume this model directly.
    """

    articles: tuple[Article, ...]
    gold_labels: tuple[GoldLabel, ...]
    split: str | None = None
