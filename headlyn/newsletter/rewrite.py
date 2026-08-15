from __future__ import annotations

import json
import urllib.request
from hashlib import sha256
from typing import Protocol

from .models import SECTION_ORDER, StoryRewrite


SYSTEM_PROMPT = f"""You are the editorial rewriting component for a daily news newsletter.

Return one JSON object with exactly this shape:
{{
  "headline": "a concise factual headline",
  "summary": "a factual 30-70 word summary",
  "section": "{('|').join(SECTION_ORDER)}"
}}

Rules:
- Use only facts explicitly present in the supplied article titles and descriptions.
- Do not invent context, quotations, causes, locations, dates, or consequences.
- Preserve uncertainty and attribution when the source text is uncertain.
- Combine the supplied reports only when they describe the same story cluster.
- Do not mention the rewriting process or refer to "the articles".
- Choose exactly one section from the allowed list.
- Return valid JSON only, without markdown or explanation.
"""


class StoryRewriter(Protocol):
    model_name: str

    def rewrite(self, story: dict[str, object]) -> StoryRewrite:
        ...


class NewsletterRewriteError(RuntimeError):
    """Raised when the local newsletter model returns unusable output."""


class OllamaStoryRewriter:
    def __init__(
        self,
        *,
        model_name: str = "gemma4:e4b-it-q4_K_M",
        endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_seconds: int = 120,
    ) -> None:
        self.model_name = model_name
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def rewrite(self, story: dict[str, object]) -> StoryRewrite:
        story_id = str(story["story_id"])
        fingerprint = story_fingerprint(story)
        payload = {
            "model": self.model_name,
            "system": SYSTEM_PROMPT,
            "prompt": build_story_prompt(story),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            parsed = parse_rewrite_response(response_payload.get("response", ""))
        except Exception as exc:
            raise NewsletterRewriteError(
                f"local newsletter rewrite failed for {story_id}: {exc}"
            ) from exc
        return StoryRewrite(
            story_id=story_id,
            headline=parsed["headline"],
            summary=parsed["summary"],
            section=parsed["section"],
            status="ok",
            model=self.model_name,
            input_fingerprint=fingerprint,
        )


def build_story_prompt(story: dict[str, object]) -> str:
    records = story.get("articles", [])
    lines = [
        f"Story ID: {story.get('story_id', '')}",
        "Contributing RSS records:",
    ]
    if isinstance(records, list):
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            title = str(record.get("title", ""))[:240]
            description = " ".join(str(record.get("description", "")).split())[:500]
            source = str(record.get("source_name", record.get("source_id", "")))
            lines.append(f"{index}. Publisher: {source}\nTitle: {title}\nDescription: {description}")
    return "\n\n".join(lines)


def parse_rewrite_response(raw_output: str) -> dict[str, str]:
    try:
        value = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise NewsletterRewriteError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise NewsletterRewriteError("LLM response must be a JSON object")
    headline = clean_value(value.get("headline"))
    summary = clean_value(value.get("summary"))
    section = clean_value(value.get("section"))
    if not headline or not summary:
        raise NewsletterRewriteError("LLM response requires headline and summary")
    if section not in SECTION_ORDER:
        raise NewsletterRewriteError(f"LLM returned unsupported section: {section!r}")
    return {"headline": headline, "summary": summary, "section": section}


def fallback_rewrite(
    story: dict[str, object],
    *,
    model_name: str,
    error: str,
) -> StoryRewrite:
    articles = story.get("articles", [])
    representative = {}
    representative_id = str(story.get("representative_article_id", ""))
    if isinstance(articles, list):
        representative = next(
            (
                article
                for article in articles
                if isinstance(article, dict)
                and str(article.get("article_id", "")) == representative_id
            ),
            next((article for article in articles if isinstance(article, dict)), {}),
        )
    return StoryRewrite(
        story_id=str(story.get("story_id", "")),
        headline=clean_value(story.get("representative_title"))
        or clean_value(representative.get("title"))
        or "Untitled story",
        summary=clean_value(story.get("representative_description"))
        or clean_value(representative.get("description"))
        or "No description available.",
        section="Other",
        status="fallback",
        model=model_name,
        input_fingerprint=story_fingerprint(story),
        error=error,
    )


def story_fingerprint(story: dict[str, object]) -> str:
    content = json.dumps(
        {
            "story_id": story.get("story_id"),
            "representative_title": story.get("representative_title"),
            "representative_description": story.get("representative_description"),
            "articles": story.get("articles", []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256(content.encode("utf-8")).hexdigest()


def clean_value(value: object) -> str:
    return " ".join(str(value or "").split())
