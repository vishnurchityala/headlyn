"""Evaluation dataset loading and validation."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Article, Dataset, GoldLabel


REQUIRED_FIELDS = frozenset(
    {
        "article_id",
        "source",
        "url",
        "title",
        "description",
        "published_at",
        "paragraphs",
        "cluster_id",
        "group",
        "topic",
        "split",
        "hard_negative_for",
    }
)
ALLOWED_SPLITS = frozenset({"dev", "test"})
WHITESPACE_RE = re.compile(r"\s+")


class DatasetValidationError(ValueError):
    """Raised when the evaluation dataset violates its loading contract."""


def load_dataset(
    path: str | Path,
    *,
    split: str | None = None,
) -> Dataset:
    """Load, validate, and label-separate the evaluation dataset.

    The JSON file remains unchanged. Runtime ``Article`` values never receive
    gold cluster metadata; that information is returned separately as
    ``GoldLabel`` values.
    """

    dataset_path = Path(path).resolve()
    if split is not None and split not in ALLOWED_SPLITS:
        raise DatasetValidationError(
            f"unsupported split {split!r}; expected one of {sorted(ALLOWED_SPLITS)}"
        )

    try:
        raw_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetValidationError(f"dataset not found: {dataset_path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"dataset is not valid JSON: {dataset_path}") from exc

    if not isinstance(raw_data, list):
        raise DatasetValidationError("evaluation dataset must contain a JSON list")
    if not raw_data:
        raise DatasetValidationError("evaluation dataset must not be empty")

    all_records = [_validate_record(record, index) for index, record in enumerate(raw_data)]
    article_ids = [record["article_id"] for record in all_records]
    duplicate_ids = sorted(
        article_id for article_id, count in Counter(article_ids).items() if count > 1
    )
    if duplicate_ids:
        raise DatasetValidationError(f"duplicate article_id values: {duplicate_ids}")

    selected_records = (
        all_records
        if split is None
        else [record for record in all_records if record["split"] == split]
    )
    if split is not None and not selected_records:
        raise DatasetValidationError(f"split {split!r} contains no articles")

    articles = tuple(_to_article(record) for record in selected_records)
    gold_labels = tuple(_to_gold_label(record) for record in selected_records)
    return Dataset(
        articles=articles,
        gold_labels=gold_labels,
        split=split,
    )


def _validate_record(record: Any, index: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise DatasetValidationError(f"record {index} must be a JSON object")

    missing = sorted(REQUIRED_FIELDS - record.keys())
    if missing:
        raise DatasetValidationError(f"record {index} is missing fields: {missing}")

    for field in ("article_id", "source", "url", "title", "description", "published_at", "cluster_id", "group", "topic", "split"):
        if not isinstance(record[field], str) or not record[field].strip():
            raise DatasetValidationError(f"record {index} field {field!r} must be a non-empty string")

    if record["split"] not in ALLOWED_SPLITS:
        raise DatasetValidationError(
            f"record {index} has unsupported split {record['split']!r}"
        )
    if not isinstance(record["paragraphs"], list) or not all(
        isinstance(paragraph, str) for paragraph in record["paragraphs"]
    ):
        raise DatasetValidationError(f"record {index} paragraphs must be a list of strings")
    if not isinstance(record["hard_negative_for"], list) or not all(
        isinstance(cluster_id, str) for cluster_id in record["hard_negative_for"]
    ):
        raise DatasetValidationError(
            f"record {index} hard_negative_for must be a list of strings"
        )

    try:
        datetime.fromisoformat(record["published_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetValidationError(
            f"record {index} published_at is not an ISO-8601 timestamp"
        ) from exc

    return record


def _to_article(record: dict[str, Any]) -> Article:
    paragraphs = tuple(_normalize_text(paragraph) for paragraph in record["paragraphs"])
    paragraphs = tuple(paragraph for paragraph in paragraphs if paragraph)
    return Article(
        article_id=record["article_id"],
        source=record["source"],
        url=record["url"],
        title=_normalize_text(record["title"]),
        description=_normalize_text(record["description"]),
        published_at=datetime.fromisoformat(record["published_at"].replace("Z", "+00:00")),
        paragraphs=paragraphs,
        clean_text="\n\n".join(paragraphs),
    )


def _to_gold_label(record: dict[str, Any]) -> GoldLabel:
    return GoldLabel(
        article_id=record["article_id"],
        cluster_id=record["cluster_id"],
        group=record["group"],
        topic=record["topic"],
        split=record["split"],
        hard_negative_for=tuple(record["hard_negative_for"]),
    )


def _normalize_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()
