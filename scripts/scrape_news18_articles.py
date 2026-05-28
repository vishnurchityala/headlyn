from __future__ import annotations

import json
import ssl
import urllib.request
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


SOURCE = "news18"
RSS_PATH = Path("assets/rss-feeds/raw/2026-05-28/news18/feed.xml")
OUTPUT_PATH = Path("assets/datasets/articles/news18-2026-05-28.json")
RAW_HTML_DIR = Path("assets/datasets/raw-html/news18/2026-05-28")
BROWSER_PROFILE_DIR = Path(".browser-profiles/news18")
LIMIT = 20

HEADLESS = False
TIMEOUT_MS = 30_000
DELAY_MS = 250
WRITE_RSS_FALLBACK_ON_ERROR = True
SAVE_RENDERED_HTML = True
WARMUP_ON_START = True
WARMUP_URL = "https://www.news18.com/"
ENABLE_READ_MORE_CLICKS = False


class News18ArticleExtractor(BaseArticleExtractor):
    BODY_SCOPE_SELECTORS = (
        '[itemprop="articleBody"]',
        ".article-content",
        ".article_content",
        ".articleBody",
        ".story_details",
        ".storyDetails",
        ".storyBody",
        "[data-testid='article-body']",
        "article",
        "main article",
    )

    BODY_SELECTORS = (
        '[itemprop="articleBody"] p',
        ".article-content p",
        ".article_content p",
        ".articleBody p",
        ".story_details p",
        ".storyDetails p",
        ".storyBody p",
        "[data-testid='article-body'] p",
        "article p",
        "main article p",
        "main p",
    )

    SKIP_PARAGRAPH_PATTERNS = (
        "advertisement",
        "also read",
        "read more",
        "related stories",
        "follow us",
        "subscribe",
        "watch live",
        "comments",
        "news18",
    )


def scrape() -> None:
    entries = parse_rss_feed(RSS_PATH)
    if LIMIT:
        entries = entries[:LIMIT]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SAVE_RENDERED_HTML:
        RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    extractor: ArticleExtractor = News18ArticleExtractor(source=SOURCE)
    articles = []
    written = 0

    with PlaywrightArticleLoader(
        headless=HEADLESS,
        timeout_ms=TIMEOUT_MS,
        delay_ms=DELAY_MS,
        warmup_on_start=WARMUP_ON_START,
        warmup_url=WARMUP_URL,
        browser_profile_dir=BROWSER_PROFILE_DIR,
        enable_read_more_clicks=ENABLE_READ_MORE_CLICKS,
    ) as loader:
        for index, entry in enumerate(entries, start=1):
            print(f"[{index}/{len(entries)}] Fetching {entry.url}")
            try:
                html = fetch_news18_html(entry.url, loader)
                html_path = save_news18_html(index, entry, html)
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

            articles.append(article)
            written += 1
            print(f"  wrote: {article['title'][:100]}")

    OUTPUT_PATH.write_text(
        json.dumps(articles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Done. Wrote {written} articles to {OUTPUT_PATH}")


def save_news18_html(index: int, entry: RssEntry, html: str) -> Path | None:
    if not SAVE_RENDERED_HTML:
        return None
    return save_rendered_html(index, entry, html, raw_html_dir=RAW_HTML_DIR)


def fetch_news18_html(url: str, loader: PlaywrightArticleLoader) -> str:
    try:
        return fetch_static_html(url)
    except Exception as exc:
        print(f"  static fetch failed, using browser: {exc}")
        return loader.fetch(url)


def fetch_static_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        },
    )
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=20, context=context) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


if __name__ == "__main__":
    scrape()
