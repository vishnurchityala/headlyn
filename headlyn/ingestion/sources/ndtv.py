from __future__ import annotations

from ..models import FeedConfig


CONFIG = FeedConfig(
    source_id="ndtv",
    name="NDTV",
    website_url="https://www.ndtv.com/",
    feed_url="https://feeds.feedburner.com/ndtvnews-india-news",
    scope="india-general",
    category="general",
    max_items=50,
)
