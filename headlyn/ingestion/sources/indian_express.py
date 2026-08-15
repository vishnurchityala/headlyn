from __future__ import annotations

from ..models import FeedConfig


CONFIG = FeedConfig(
    source_id="indian-express",
    name="The Indian Express",
    website_url="https://indianexpress.com/",
    feed_url="https://indianexpress.com/section/india/feed/",
    scope="india-general",
    category="general",
    max_items=50,
)
