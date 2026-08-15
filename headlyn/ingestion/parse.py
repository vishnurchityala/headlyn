from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from .models import RssEntry


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def parse_rss(payload: bytes) -> list[RssEntry]:
    root = ET.fromstring(payload)
    entries: list[RssEntry] = []
    for item in root.iter():
        if local_name(item.tag) != "item":
            continue
        values: dict[str, str] = {}
        categories: list[str] = []
        for child in item:
            key = local_name(child.tag)
            value = child.text or ""
            if key == "category":
                categories.append(clean_text(value))
            elif key not in values or not values[key]:
                values[key] = value

        url = clean_text(values.get("link") or values.get("guid"))
        title = clean_html(values.get("title"))
        if not url or not title:
            continue
        raw_description = values.get("description") or values.get("encoded") or ""
        raw_date = values.get("pubDate") or values.get("published") or ""
        description = clean_html(raw_description) or title
        entries.append(
            RssEntry(
                url=url,
                title=title,
                description=description,
                published_at=normalize_datetime(raw_date),
                tags=tuple(dedupe(categories)),
            )
        )
    return entries


def clean_html(value: str) -> str:
    parser = _TextParser()
    parser.feed(html.unescape(value or ""))
    return clean_text(" ".join(parser.parts))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def normalize_datetime(value: str) -> str:
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


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = clean_text(value)
        key = normalized.lower()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result
