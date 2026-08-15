from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import FeedConfig, RssEntry, RssItem


TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip()
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_KEYS and not key.lower().startswith("utm_")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(sorted(query)),
            "",
        )
    )


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(title).lower()).strip()


def article_id(url: str) -> str:
    return "article-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def normalize_entries(
    feed: FeedConfig,
    entries: list[RssEntry],
    *,
    limit: int,
    ingested_at: str,
) -> tuple[list[RssItem], int]:
    items: list[RssItem] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    duplicate_count = 0
    for entry in entries[:limit]:
        canonical_url = normalize_url(entry.url)
        title_key = normalize_title(entry.title)
        if not canonical_url or not title_key:
            continue
        if canonical_url in seen_urls or title_key in seen_titles:
            duplicate_count += 1
            continue
        seen_urls.add(canonical_url)
        seen_titles.add(title_key)
        items.append(
            RssItem(
                article_id=article_id(canonical_url),
                source_id=feed.source_id,
                source_name=feed.name,
                scope=feed.scope,
                category=feed.category,
                title=entry.title,
                description=entry.description,
                published_at=entry.published_at,
                url=canonical_url,
                tags=entry.tags,
                ingested_at=ingested_at,
            )
        )
    return items, duplicate_count
