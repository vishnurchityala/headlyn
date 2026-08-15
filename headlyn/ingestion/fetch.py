from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .models import FeedConfig, PipelineConfig


ROOT_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_ROOT = ROOT_DIR / "assets" / "rss-feeds" / "raw"
USER_AGENT = "Headlyn/0.1 (+RSS newsletter ingestion)"


@dataclass(frozen=True)
class FeedResponse:
    payload: bytes
    http_status: int | None
    headers: dict[str, str]
    input_path: Path | None = None


def fetch_feed(config: PipelineConfig, feed: FeedConfig) -> FeedResponse:
    if config.mode == "snapshot":
        if not config.snapshot_date:
            raise ValueError("snapshot mode requires snapshot_date")
        path = SNAPSHOT_ROOT / config.snapshot_date / feed.source_id / "feed.xml"
        return FeedResponse(payload=path.read_bytes(), http_status=None, headers={}, input_path=path)

    request = urllib.request.Request(
        feed.feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    last_error: Exception | None = None
    for attempt in range(config.retries):
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                return FeedResponse(
                    payload=response.read(),
                    http_status=response.status,
                    headers=dict(response.headers.items()),
                )
        except Exception as exc:
            last_error = exc
            if attempt + 1 < config.retries:
                time.sleep(config.delay_seconds)
    raise RuntimeError(f"feed fetch failed: {last_error}") from last_error
