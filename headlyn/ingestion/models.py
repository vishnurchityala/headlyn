from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FeedConfig:
    source_id: str
    name: str
    feed_url: str
    scope: str
    category: str
    max_items: int = 20
    website_url: str = ""


@dataclass(frozen=True)
class RssEntry:
    url: str
    title: str
    description: str
    published_at: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RssItem:
    article_id: str
    source_id: str
    source_name: str
    scope: str
    category: str
    title: str
    description: str
    published_at: str
    url: str
    tags: tuple[str, ...]
    ingested_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "scope": self.scope,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "published_at": self.published_at,
            "url": self.url,
            "tags": list(self.tags),
            "ingested_at": self.ingested_at,
        }


@dataclass(frozen=True)
class PipelineConfig:
    mode: str = "live"
    snapshot_date: str | None = None
    run_id: str | None = None
    artifact_root: Path | None = None
    source_ids: tuple[str, ...] | None = None
    limit: int | None = None
    timeout_seconds: int = 30
    retries: int = 2
    delay_seconds: float = 0.25
    max_workers: int = 4


@dataclass(frozen=True)
class SourceResult:
    source_id: str
    status: str
    item_count: int
    duplicate_count: int
    output_dir: Path
    summary_path: Path
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "item_count": self.item_count,
            "duplicate_count": self.duplicate_count,
            "output_dir": str(self.output_dir),
            "summary_path": str(self.summary_path),
            "error": self.error,
        }


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    status: str
    source_results: tuple[SourceResult, ...]
    output_dir: Path
    summary_path: Path
