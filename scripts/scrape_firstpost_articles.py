from __future__ import annotations

import json
from pathlib import Path

from scrape_article_utils import (
    ArticleExtractor,
    BaseArticleExtractor,
    PlaywrightArticleLoader,
    RssEntry,
    article_from_rss_entry,
    looks_like_access_denied,
    parse_rss_feed,
    save_rendered_html,
    utc_now_iso,
)


SOURCE = "firstpost"
RSS_PATH = Path("assets/rss-feeds/raw/2026-05-28/firstpost/feed.xml")
OUTPUT_PATH = Path("assets/datasets/articles/firstpost-2026-05-28.jsonl")
RAW_HTML_DIR = Path("assets/datasets/raw-html/firstpost/2026-05-28")
BROWSER_PROFILE_DIR = Path(".browser-profiles/firstpost")
LIMIT = 20

HEADLESS = False
TIMEOUT_MS = 30_000
DELAY_MS = 250
WRITE_RSS_FALLBACK_ON_ERROR = True
SAVE_RENDERED_HTML = True
WARMUP_ON_START = True
WARMUP_URL = "https://www.firstpost.com/"
ENABLE_READ_MORE_CLICKS = True


class FirstpostArticleExtractor(BaseArticleExtractor):
    BODY_SCOPE_SELECTORS = (
        '[itemprop="articleBody"]',
        "article",
        "main article",
        ".article-content",
        ".story-content",
        ".article__body",
        ".article-body",
        ".content-area",
        '[class*="article"][class*="content"]',
        '[class*="story"][class*="content"]',
    )

    BODY_SELECTORS = (
        '[itemprop="articleBody"] p',
        "article p",
        "main article p",
        ".article-content p",
        ".story-content p",
        ".article__body p",
        ".article-body p",
        ".content-area p",
        '[class*="article"][class*="content"] p',
        '[class*="story"][class*="content"] p',
        '[class*="article"] p',
        "main p",
    )

    SKIP_PARAGRAPH_PATTERNS = (
        "advertisement",
        "also read",
        "read more",
        "watch:",
        "follow us",
        "subscribe",
        "download app",
        "end of article",
        "tags:",
        "click here",
    )


def scrape() -> None:
    entries = parse_rss_feed(RSS_PATH)
    if LIMIT:
        entries = entries[:LIMIT]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SAVE_RENDERED_HTML:
        RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    extractor: ArticleExtractor = FirstpostArticleExtractor(source=SOURCE)
    written = 0

    with PlaywrightArticleLoader(
        headless=HEADLESS,
        timeout_ms=TIMEOUT_MS,
        delay_ms=DELAY_MS,
        warmup_on_start=WARMUP_ON_START,
        warmup_url=WARMUP_URL,
        browser_profile_dir=BROWSER_PROFILE_DIR,
        enable_read_more_clicks=ENABLE_READ_MORE_CLICKS,
    ) as loader, OUTPUT_PATH.open("w", encoding="utf-8") as output:
        for index, entry in enumerate(entries, start=1):
            print(f"[{index}/{len(entries)}] Fetching {entry.url}")
            try:
                html = loader.fetch(entry.url)
                html_path = save_firstpost_html(index, entry, html)
                if html_path:
                    print(f"  saved: {html_path}")
                    html = html_path.read_text(encoding="utf-8")
                if looks_like_access_denied(html):
                    raise RuntimeError("article page returned Access Denied")
                article = extractor.extract(html, entry, utc_now_iso())
                if not article["paragraphs"]:
                    raise RuntimeError("no article paragraphs found")
            except Exception as exc:
                if not WRITE_RSS_FALLBACK_ON_ERROR:
                    print(f"  skipped: {exc}")
                    continue
                article = article_from_rss_entry(entry, utc_now_iso(), source=SOURCE)
                print(f"  fallback: {exc}")

            output.write(json.dumps(article, ensure_ascii=False) + "\n")
            written += 1
            print(f"  wrote: {article['title'][:100]}")

    print(f"Done. Wrote {written} articles to {OUTPUT_PATH}")


def save_firstpost_html(index: int, entry: RssEntry, html: str) -> Path | None:
    if not SAVE_RENDERED_HTML:
        return None
    return save_rendered_html(index, entry, html, raw_html_dir=RAW_HTML_DIR)


if __name__ == "__main__":
    scrape()
