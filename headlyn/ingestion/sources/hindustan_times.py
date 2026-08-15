from __future__ import annotations

from ..models import FeedConfig


CONFIG = FeedConfig(
    source_id="hindustan-times",
    name="Hindustan Times",
    website_url="https://www.hindustantimes.com/",
    feed_url="https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
    scope="india-general",
    category="general",
    max_items=50,
)
