from __future__ import annotations

from ..models import FeedConfig


CONFIG = FeedConfig(
    source_id="firstpost",
    name="Firstpost",
    website_url="https://www.firstpost.com/",
    feed_url="https://www.firstpost.com/commonfeeds/v1/mfp/rss/india.xml",
    scope="india-general",
    category="general",
    max_items=50,
)
