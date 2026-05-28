from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from scrape_article_utils import (
    ArticleExtractor,
    BaseArticleExtractor,
    PlaywrightArticleLoader,
    RssEntry,
    article_from_rss_entry,
    clean_text,
    looks_like_access_denied,
    parse_rss_feed,
    save_rendered_html,
    utc_now_iso,
)


SOURCE = "pib"
RSS_PATH = Path("assets/rss-feeds/raw/2026-05-28/pib/feed.xml")
OUTPUT_PATH = Path("assets/datasets/articles/pib-2026-05-28.json")
RAW_HTML_DIR = Path("assets/datasets/raw-html/pib/2026-05-28")
BROWSER_PROFILE_DIR = Path(".browser-profiles/pib")
LIMIT = 20

HEADLESS = False
TIMEOUT_MS = 30_000
DELAY_MS = 250
WRITE_RSS_FALLBACK_ON_ERROR = True
SAVE_RENDERED_HTML = True
WARMUP_ON_START = True
WARMUP_URL = "https://pib.gov.in/"
ENABLE_READ_MORE_CLICKS = False


class PibArticleExtractor(BaseArticleExtractor):
    BODY_SCOPE_SELECTORS = (
        '[itemprop="articleBody"]',
        ".innner-page-main-about-us-content-right-part",
        "#divContent",
        "#ReleaseDiv",
        ".innner-page-main-about-us-content",
        ".inner-content",
        ".content-area",
        ".release",
        ".PressRelease",
        "article",
        "main",
    )

    BODY_SELECTORS = (
        '[itemprop="articleBody"] p',
        ".innner-page-main-about-us-content-right-part > p",
        "#divContent p",
        "#ReleaseDiv p",
        ".innner-page-main-about-us-content p",
        ".inner-content p",
        ".content-area p",
        ".release p",
        ".PressRelease p",
        "article p",
        "main p",
    )

    SKIP_PARAGRAPH_PATTERNS = (
        "advertisement",
        "also read",
        "read more",
        "release id",
        "visitor counter",
        "site is designed",
        "content owned",
        "last updated",
        "print",
        "share",
    )

    def _extract_paragraphs(self, soup: BeautifulSoup, article_body: Any) -> list[str]:
        container = soup.select_one(".innner-page-main-about-us-content-right-part")
        if not container:
            return super()._extract_paragraphs(soup, article_body)

        paragraphs = self._extract_release_paragraphs(container)
        if paragraphs:
            return paragraphs
        return super()._extract_paragraphs(soup, article_body)

    def _extract_release_paragraphs(self, container: Tag) -> list[str]:
        paragraphs: list[str] = []
        seen: set[str] = set()

        for tag in container.find_all("p", recursive=False):
            text = self._release_paragraph_text(tag)
            if not text:
                continue

            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            paragraphs.append(text)

        return paragraphs

    def _release_paragraph_text(self, tag: Tag) -> str:
        text = clean_text(tag.get_text(" ", strip=True))
        if len(text) < 35:
            return ""

        lowered = text.lower()
        if self._is_ui_or_boilerplate_text(lowered):
            return ""
        if self._is_non_article_embed(tag, lowered):
            return ""
        if self._is_release_footer(text):
            return ""
        return text

    def _is_ui_or_boilerplate_text(self, lowered_text: str) -> bool:
        if lowered_text in {"print", "share"}:
            return True
        return any(
            pattern in lowered_text
            for pattern in self.SKIP_PARAGRAPH_PATTERNS
            if pattern not in {"print", "share"}
        )

    def _is_non_article_embed(self, tag: Tag, lowered_text: str) -> bool:
        if tag.select_one("blockquote.twitter-tweet, .twitter-tweet"):
            return True
        if "pic.twitter.com" in lowered_text or "platform.x.com/widgets" in lowered_text:
            return True
        return False

    def _is_release_footer(self, text: str) -> bool:
        normalized = clean_text(text).strip("* ")
        if not normalized:
            return True
        return bool(re.fullmatch(r"[A-Z]{1,8}(?:/[A-Z]{1,8})?", normalized))


def scrape() -> None:
    entries = parse_rss_feed(RSS_PATH)
    if LIMIT:
        entries = entries[:LIMIT]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SAVE_RENDERED_HTML:
        RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    extractor: ArticleExtractor = PibArticleExtractor(source=SOURCE)
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
            fetch_url = pib_full_page_url(entry.url)
            print(f"[{index}/{len(entries)}] Fetching {fetch_url}")
            try:
                html = fetch_pib_html(fetch_url, loader)
                html_path = save_pib_html(index, entry, html)
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


def save_pib_html(index: int, entry: RssEntry, html: str) -> Path | None:
    if not SAVE_RENDERED_HTML:
        return None
    return save_rendered_html(index, entry, html, raw_html_dir=RAW_HTML_DIR)


def pib_full_page_url(url: str) -> str:
    return url.replace(
        "https://pib.gov.in/PressReleaseIframePage.aspx",
        "https://www.pib.gov.in/PressReleasePage.aspx",
    ).replace(
        "https://www.pib.gov.in/PressReleaseIframePage.aspx",
        "https://www.pib.gov.in/PressReleasePage.aspx",
    )


def fetch_pib_html(url: str, loader: PlaywrightArticleLoader) -> str:
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
        content_type = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(content_type, errors="replace")


if __name__ == "__main__":
    scrape()
