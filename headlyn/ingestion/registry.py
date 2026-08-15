from __future__ import annotations

from .models import FeedConfig
from .sources.firstpost import CONFIG as FIRSTPOST_CONFIG
from .sources.hindustan_times import CONFIG as HINDUSTAN_TIMES_CONFIG
from .sources.indian_express import CONFIG as INDIAN_EXPRESS_CONFIG
from .sources.ndtv import CONFIG as NDTV_CONFIG


FEEDS: tuple[FeedConfig, ...] = (
    FIRSTPOST_CONFIG,
    INDIAN_EXPRESS_CONFIG,
    NDTV_CONFIG,
    HINDUSTAN_TIMES_CONFIG,
)
FEED_BY_ID = {feed.source_id: feed for feed in FEEDS}


def get_feed(source_id: str) -> FeedConfig:
    try:
        return FEED_BY_ID[source_id]
    except KeyError as exc:
        available = ", ".join(sorted(FEED_BY_ID))
        raise ValueError(f"Unknown source '{source_id}'. Available sources: {available}") from exc


def available_sources() -> tuple[str, ...]:
    return tuple(feed.source_id for feed in FEEDS)
