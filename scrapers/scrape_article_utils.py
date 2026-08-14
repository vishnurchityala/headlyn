from __future__ import annotations

import html as html_lib
import json
import random
import re
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_SOURCE = "article"
DEFAULT_RAW_HTML_DIR = Path("assets/datasets/raw-html/articles")
DEFAULT_BROWSER_PROFILE_DIR = Path(".browser-profiles/articles")
HEADLESS = False
TIMEOUT_MS = 30_000
DELAY_MS = 250
WAIT_SELECTOR: str | None = None
SAVE_RENDERED_HTML = True
USE_PERSISTENT_CONTEXT = True
WARMUP_ON_START = True
WARMUP_URL = "about:blank"
ENABLE_READ_MORE_CLICKS = True
SLOW_MO_MS = 20
MIN_ACTION_DELAY_MS = 80
MAX_ACTION_DELAY_MS = 250
FULL_PAGE_SCROLL_STEP_PX = 650
FULL_PAGE_MAX_SCROLLS = 24
READ_MORE_TEXT_PATTERN = r"\b(read\s*more|continue\s*reading|show\s*more|load\s*more)\b"
READ_MORE_SKIP_TEXT_PATTERN = (
    r"\b(read\s+more\s+stories|more\s+stories|related\s+stories|"
    r"click\s+here\s+to\s+read\s+more|next\s+article|next\s+story|read\s+next)\b"
)
READ_MORE_MAX_CLICKS = 5
NEXT_ARTICLE_TEXT_PATTERN = r"\b(next\s+article|next\s+story|read\s+next)\b"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ARTICLE_KEYS = (
    "source",
    "url",
    "title",
    "description",
    "published_at",
    "tags",
    "paragraphs",
    "rss_published_at",
    "fetched_at",
)


@dataclass(frozen=True)
class RssEntry:
    url: str
    title: str
    description: str
    published_at: str
    tags: list[str]


class ContentLoader(ABC):
    @abstractmethod
    def fetch(self, url: str) -> str:
        """Return rendered article HTML for a URL."""


class PlaywrightArticleLoader(ContentLoader):
    def __init__(
        self,
        *,
        headless: bool | None = None,
        timeout_ms: int | None = None,
        delay_ms: int | None = None,
        wait_selector: str | None = None,
        user_agent: str | None = None,
        use_persistent_context: bool | None = None,
        warmup_on_start: bool | None = None,
        warmup_url: str = WARMUP_URL,
        browser_profile_dir: Path = DEFAULT_BROWSER_PROFILE_DIR,
        enable_read_more_clicks: bool = ENABLE_READ_MORE_CLICKS,
    ) -> None:
        self.headless = HEADLESS if headless is None else headless
        self.timeout_ms = TIMEOUT_MS if timeout_ms is None else timeout_ms
        self.delay_ms = DELAY_MS if delay_ms is None else delay_ms
        self.wait_selector = WAIT_SELECTOR if wait_selector is None else wait_selector
        self.user_agent = USER_AGENT if user_agent is None else user_agent
        self.use_persistent_context = (
            USE_PERSISTENT_CONTEXT
            if use_persistent_context is None
            else use_persistent_context
        )
        self.warmup_on_start = WARMUP_ON_START if warmup_on_start is None else warmup_on_start
        self.warmup_url = warmup_url
        self.browser_profile_dir = browser_profile_dir
        self.enable_read_more_clicks = enable_read_more_clicks
        self._playwright = None
        self._browser = None
        self._context = None
        self._warmed_up = False
        self._clicked_read_more_signatures: set[str] = set()

    def __enter__(self) -> "PlaywrightArticleLoader":
        self._playwright = sync_playwright().start()
        context_options = {
            "user_agent": self.user_agent,
            "viewport": {"width": 1366, "height": 900},
            "locale": "en-IN",
            "timezone_id": "Asia/Kolkata",
            "extra_http_headers": {
                "Accept-Language": "en-IN,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        }
        if self.use_persistent_context:
            self.browser_profile_dir.mkdir(parents=True, exist_ok=True)
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.browser_profile_dir),
                headless=self.headless,
                slow_mo=SLOW_MO_MS,
                **context_options,
            )
        else:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=SLOW_MO_MS,
            )
            self._context = self._browser.new_context(**context_options)
        if self.warmup_on_start:
            self._warm_up()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def fetch(self, url: str) -> str:
        if self._context is None:
            raise RuntimeError("PlaywrightArticleLoader must be used as a context manager")

        page = self._context.new_page()
        try:
            self._clicked_read_more_signatures.clear()
            self._human_pause()
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.wait_selector:
                page.wait_for_selector(self.wait_selector, timeout=self.timeout_ms)
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightTimeoutError:
                    pass

            self._close_common_overlays(page)
            if self.enable_read_more_clicks:
                self._click_read_more_buttons(page)
            self._emulate_reading(page)
            if self.enable_read_more_clicks:
                self._click_read_more_buttons(page)
            return page.content()
        finally:
            page.close()
            if self.delay_ms > 0:
                time.sleep(self.delay_ms / 1000)

    def _warm_up(self) -> None:
        if self._context is None or self._warmed_up:
            return

        page = self._context.new_page()
        try:
            page.goto(self.warmup_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except PlaywrightTimeoutError:
                pass
            self._close_common_overlays(page)
            self._emulate_reading(page, max_scrolls=4)
            self._warmed_up = True
        except Exception as exc:
            print(f"Warmup skipped: {exc}")
        finally:
            page.close()

    def _close_common_overlays(self, page) -> None:
        labels = (
            "Accept",
            "Accept All",
            "I Agree",
            "Agree",
            "Continue",
            "Got it",
            "Allow all",
        )
        for label in labels:
            button = page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
            try:
                if button.count() > 0:
                    button.first.click(timeout=800)
                    self._human_pause(200, 500)
                    return
            except Exception:
                continue

    def _emulate_reading(self, page, *, max_scrolls: int = FULL_PAGE_MAX_SCROLLS) -> None:
        self._human_pause()
        self._move_mouse(page)

        for _ in range(max_scrolls):
            page.mouse.wheel(0, random.randint(450, FULL_PAGE_SCROLL_STEP_PX))
            self._human_pause()
            if self.enable_read_more_clicks:
                self._click_read_more_buttons(page)
            if self._next_article_marker_visible(page):
                print("  stopped before next article")
                break
            at_bottom = page.evaluate(
                """
                () => (
                    window.scrollY + window.innerHeight >=
                    document.documentElement.scrollHeight - 80
                )
                """
            )
            if at_bottom:
                break

        self._human_pause()

    def _click_read_more_buttons(self, page) -> int:
        pattern = re.compile(READ_MORE_TEXT_PATTERN, re.I)
        candidate_locators = (
            page.get_by_role("button", name=pattern),
            page.get_by_role("link", name=pattern),
            page.locator("button, a, [role='button']").filter(has_text=pattern),
            page.locator(
                ".read-more, .readmore, "
                "[class*='read-more'], [class*='readmore'], "
                "[id*='read-more'], [id*='readmore']"
            ).filter(has_text=pattern),
        )
        clicks = 0

        while clicks < READ_MORE_MAX_CLICKS:
            clicked = False
            for locator in candidate_locators:
                try:
                    count = min(locator.count(), 5)
                except Exception:
                    continue

                for index in range(count):
                    target = locator.nth(index)
                    try:
                        if not target.is_visible(timeout=300):
                            continue
                        label = clean_text(target.inner_text(timeout=500))
                        if label and not pattern.search(label):
                            continue
                        if label and re.search(READ_MORE_SKIP_TEXT_PATTERN, label, re.I):
                            continue
                        if self._is_navigational_read_more(target):
                            continue
                        signature = self._read_more_signature(target)
                        if signature in self._clicked_read_more_signatures:
                            continue
                        target.scroll_into_view_if_needed(timeout=1_000)
                        self._human_pause(100, 300)
                        target.click(timeout=2_000)
                        self._clicked_read_more_signatures.add(signature)
                        clicks += 1
                        clicked = True
                        print(f"  clicked read more: {label[:80] or 'matched element'}")
                        try:
                            page.wait_for_load_state("networkidle", timeout=5_000)
                        except PlaywrightTimeoutError:
                            pass
                        self._human_pause(500, 1_200)
                        break
                    except Exception:
                        continue

                if clicked:
                    break

            if not clicked:
                break

        return clicks

    def _is_navigational_read_more(self, target) -> bool:
        try:
            return bool(
                target.evaluate(
                    """
                    (element) => {
                        const anchor = element.closest('a[href]') || element.querySelector('a[href]');
                        if (!anchor) {
                            return false;
                        }
                        const href = (anchor.getAttribute('href') || '').trim();
                        if (!href || href === '#') {
                            return false;
                        }
                        const lowered = href.toLowerCase();
                        return !lowered.startsWith('javascript:');
                    }
                    """
                )
            )
        except Exception:
            return True

    def _read_more_signature(self, target) -> str:
        try:
            return clean_text(
                target.evaluate(
                    """
                    (element) => [
                        element.tagName,
                        element.id || '',
                        element.className || '',
                        element.getAttribute('href') || '',
                        element.textContent || ''
                    ].join('|')
                    """
                )
            )
        except Exception:
            return ""

    def _next_article_marker_visible(self, page) -> bool:
        pattern = re.compile(NEXT_ARTICLE_TEXT_PATTERN, re.I)
        locators = (
            page.get_by_text(pattern),
            page.locator("h1, h2, h3, h4, a, button, [role='heading']").filter(has_text=pattern),
        )
        for locator in locators:
            try:
                count = min(locator.count(), 5)
            except Exception:
                continue
            for index in range(count):
                target = locator.nth(index)
                try:
                    if target.is_visible(timeout=200):
                        return True
                except Exception:
                    continue
        return False

    def _move_mouse(self, page) -> None:
        viewport = page.viewport_size or {"width": 1366, "height": 900}
        for _ in range(random.randint(2, 4)):
            page.mouse.move(
                random.randint(120, max(121, viewport["width"] - 120)),
                random.randint(120, max(121, viewport["height"] - 120)),
                steps=random.randint(8, 18),
            )
            self._human_pause(100, 300)

    def _human_pause(
        self,
        min_delay_ms: int = MIN_ACTION_DELAY_MS,
        max_delay_ms: int = MAX_ACTION_DELAY_MS,
    ) -> None:
        time.sleep(random.uniform(min_delay_ms, max_delay_ms) / 1000)


class ArticleExtractor(ABC):
    @abstractmethod
    def extract(self, html: str, rss_entry: RssEntry, fetched_at: str) -> dict[str, Any]:
        """Return a normalized article entity."""


class BaseArticleExtractor(ArticleExtractor):
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

    def __init__(self, *, source: str = DEFAULT_SOURCE) -> None:
        self.source = source

    def extract(self, html: str, rss_entry: RssEntry, fetched_at: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "lxml")
        article_data = find_article_json_ld(soup)

        page_title = first_text(
            value_from_json(article_data, "headline"),
            value_from_json(article_data, "name"),
            meta_content(soup, property_name="og:title"),
            meta_content(soup, name="twitter:title"),
            element_text(soup.find("h1")),
        )
        description = first_text(
            value_from_json(article_data, "description"),
            meta_content(soup, name="description"),
            meta_content(soup, property_name="og:description"),
            meta_content(soup, name="twitter:description"),
        )
        published_at = first_text(
            value_from_json(article_data, "datePublished"),
            meta_content(soup, property_name="article:published_time"),
            meta_content(soup, name="publish-date"),
            meta_content(soup, name="pubdate"),
            meta_content(soup, itemprop="datePublished"),
            datetime_from_time_element(soup),
        )

        page_tags = dedupe(
            tags_from_value(article_data.get("keywords"))
            + split_tags(meta_content(soup, name="news_keywords"))
            + split_tags(meta_content(soup, name="keywords"))
            + split_many_tags(meta_contents(soup, property_name="article:tag"))
            + dom_tags(soup)
        )
        paragraphs = self._extract_paragraphs(soup, article_data.get("articleBody"))

        entity = {
            "source": self.source,
            "url": rss_entry.url,
            "title": clean_text(page_title) or rss_entry.title,
            "description": clean_text(description) or rss_entry.description,
            "published_at": normalize_datetime(published_at) or rss_entry.published_at,
            "tags": page_tags or rss_entry.tags,
            "paragraphs": paragraphs,
            "rss_published_at": rss_entry.published_at,
            "fetched_at": fetched_at,
        }
        return {key: entity[key] for key in ARTICLE_KEYS}

    def _extract_paragraphs(self, soup: BeautifulSoup, article_body: Any) -> list[str]:
        scoped_paragraphs = self._extract_from_first_article_scope(soup)
        if scoped_paragraphs:
            return scoped_paragraphs

        selector_results: list[list[str]] = []
        for selector in self.BODY_SELECTORS:
            paragraphs = clean_paragraphs(
                self._paragraph_texts_before_next_article(soup.select(selector)),
                skip_patterns=self.SKIP_PARAGRAPH_PATTERNS,
            )
            if paragraphs:
                selector_results.append(paragraphs)
            if len(paragraphs) >= 2 and total_text_length(paragraphs) >= 200:
                return paragraphs

        body_paragraphs = clean_paragraphs(
            split_article_body(article_body),
            skip_patterns=self.SKIP_PARAGRAPH_PATTERNS,
        )
        if len(body_paragraphs) >= 2:
            return body_paragraphs

        if selector_results:
            return max(selector_results, key=total_text_length)
        return body_paragraphs

    def _extract_from_first_article_scope(self, soup: BeautifulSoup) -> list[str]:
        for selector in self.BODY_SCOPE_SELECTORS:
            for scope in soup.select(selector):
                paragraphs = clean_paragraphs(
                    self._paragraph_texts_before_next_article(scope.select("p")),
                    skip_patterns=self.SKIP_PARAGRAPH_PATTERNS,
                )
                if len(paragraphs) >= 2 and total_text_length(paragraphs) >= 200:
                    return paragraphs
        return []

    def _paragraph_texts_before_next_article(self, paragraph_tags: list[Tag]) -> list[str]:
        values: list[str] = []
        for tag in paragraph_tags:
            if has_next_article_marker_before(tag):
                break
            values.append(element_text(tag))
        return values


def parse_rss_feed(path: Path) -> list[RssEntry]:
    root = ET.parse(path).getroot()
    entries: list[RssEntry] = []

    for item in root.findall("./channel/item"):
        url = clean_text(item.findtext("link"))
        if not url:
            continue

        title = clean_rss_html(item.findtext("title"))
        description = clean_rss_html(item.findtext("description"))
        published_at = normalize_datetime(item.findtext("pubDate")) or clean_text(
            item.findtext("pubDate")
        )
        tags = dedupe(
            clean_text(category.text)
            for category in item.findall("category")
            if clean_text(category.text)
        )
        entries.append(
            RssEntry(
                url=url,
                title=title,
                description=description,
                published_at=published_at,
                tags=tags,
            )
        )

    return entries


def save_rendered_html(
    index: int,
    entry: RssEntry,
    html: str,
    *,
    raw_html_dir: Path = DEFAULT_RAW_HTML_DIR,
) -> Path | None:
    if not SAVE_RENDERED_HTML:
        return None

    path = raw_html_path(index, entry, raw_html_dir=raw_html_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def raw_html_path(
    index: int,
    entry: RssEntry,
    *,
    raw_html_dir: Path = DEFAULT_RAW_HTML_DIR,
) -> Path:
    slug = entry.url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.html?$", "", slug, flags=re.I)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-")
    if not slug:
        slug = f"article-{index:03d}"
    return raw_html_dir / f"{index:03d}-{slug[:120]}.html"


def article_from_rss_entry(
    entry: RssEntry,
    fetched_at: str,
    *,
    source: str = DEFAULT_SOURCE,
) -> dict[str, Any]:
    entity = {
        "source": source,
        "url": entry.url,
        "title": entry.title,
        "description": entry.description,
        "published_at": entry.published_at,
        "tags": entry.tags,
        "paragraphs": [entry.description] if entry.description else [],
        "rss_published_at": entry.published_at,
        "fetched_at": fetched_at,
    }
    return {key: entity[key] for key in ARTICLE_KEYS}


def looks_like_access_denied(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    title = element_text(soup.find("title")).lower()
    body = element_text(soup.find("body")).lower()
    return "access denied" in title or "you don't have permission to access" in body


def find_article_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates.extend(flatten_json_ld(data))

    for candidate in candidates:
        candidate_type = candidate.get("@type") or candidate.get("type")
        types = candidate_type if isinstance(candidate_type, list) else [candidate_type]
        normalized_types = {str(item).lower() for item in types if item}
        if normalized_types & {"newsarticle", "article", "reportagenewsarticle"}:
            return candidate
    return {}


def flatten_json_ld(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        current = [data]
        graph = data.get("@graph")
        if graph is not None:
            current.extend(flatten_json_ld(graph))
        return current
    if isinstance(data, list):
        flattened: list[dict[str, Any]] = []
        for item in data:
            flattened.extend(flatten_json_ld(item))
        return flattened
    return []


def value_from_json(data: dict[str, Any], key: str) -> Any:
    value = data.get(key)
    if isinstance(value, list):
        return first_text(*value)
    if isinstance(value, dict):
        return first_text(value.get("name"), value.get("@id"), value.get("url"))
    return value


def meta_content(
    soup: BeautifulSoup,
    *,
    name: str | None = None,
    property_name: str | None = None,
    itemprop: str | None = None,
) -> str:
    return first_text(
        *meta_contents(soup, name=name, property_name=property_name, itemprop=itemprop)
    )


def meta_contents(
    soup: BeautifulSoup,
    *,
    name: str | None = None,
    property_name: str | None = None,
    itemprop: str | None = None,
) -> list[str]:
    attrs: dict[str, str] = {}
    if name:
        attrs["name"] = name
    if property_name:
        attrs["property"] = property_name
    if itemprop:
        attrs["itemprop"] = itemprop

    values = [
        clean_text(tag.get("content"))
        for tag in soup.find_all("meta", attrs=attrs)
        if clean_text(tag.get("content"))
    ]
    return values


def datetime_from_time_element(soup: BeautifulSoup) -> str:
    time_tag = soup.find("time")
    if not isinstance(time_tag, Tag):
        return ""
    return first_text(time_tag.get("datetime"), time_tag.get("content"), element_text(time_tag))


def dom_tags(soup: BeautifulSoup) -> list[str]:
    selectors = (
        'a[rel="tag"]',
        '[class*="tag"] a',
        '[class*="keyword"] a',
        '[class*="topic"] a',
    )
    tags: list[str] = []
    for selector in selectors:
        tags.extend(element_text(tag) for tag in soup.select(selector))
    return [tag for tag in dedupe(tags) if is_reasonable_tag(tag)]


def tags_from_value(value: Any) -> list[str]:
    if isinstance(value, list):
        tags: list[str] = []
        for item in value:
            tags.extend(tags_from_value(item))
        return dedupe(tags)
    if isinstance(value, dict):
        return tags_from_value(first_text(value.get("name"), value.get("text")))
    if isinstance(value, str):
        return split_tags(value)
    return []


def split_many_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        tags.extend(split_tags(value))
    return dedupe(tags)


def split_tags(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [
        clean_text(tag)
        for tag in re.split(r"[,|;]", value)
        if clean_text(tag) and is_reasonable_tag(clean_text(tag))
    ]


def is_reasonable_tag(value: str) -> bool:
    return 1 < len(value) <= 80 and not value.lower().startswith(("http://", "https://"))


def split_article_body(value: Any) -> list[str]:
    if isinstance(value, list):
        paragraphs: list[str] = []
        for item in value:
            paragraphs.extend(split_article_body(item))
        return paragraphs
    if isinstance(value, dict):
        return split_article_body(
            first_text(value.get("articleBody"), value.get("text"), value.get("name"))
        )
    if not isinstance(value, str):
        return []
    text = clean_text(value)
    if not text:
        return []
    blocks = re.split(r"\n{2,}|(?<=[.!?])\s+(?=[A-Z])", text)
    return [clean_text(block) for block in blocks]


def has_next_article_marker_before(tag: Tag) -> bool:
    for previous in tag.find_all_previous(limit=80):
        text = element_text(previous)
        if 0 < len(text) <= 160 and re.search(NEXT_ARTICLE_TEXT_PATTERN, text, re.I):
            return True
    return False


def clean_paragraphs(values: list[str], *, skip_patterns: tuple[str, ...]) -> list[str]:
    paragraphs: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if len(text) < 35:
            continue
        lowered = text.lower()
        if any(pattern in lowered for pattern in skip_patterns):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        paragraphs.append(text)
    return paragraphs


def clean_rss_html(value: str | None) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "lxml")
    return clean_text(soup.get_text(" ", strip=True))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    for _ in range(2):
        unescaped = html_lib.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return re.sub(r"\s+", " ", text).strip()


def first_text(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def element_text(tag: Tag | None) -> str:
    if not isinstance(tag, Tag):
        return ""
    return clean_text(tag.get_text(" ", strip=True))


def dedupe(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = text.lower()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def normalize_datetime(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""

    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        parsed = None

    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def total_text_length(values: list[str]) -> int:
    return sum(len(value) for value in values)
