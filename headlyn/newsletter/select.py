from __future__ import annotations

from datetime import datetime, timezone

from .models import SECTION_ORDER, StoryRewrite


def prepare_candidates(
    stories: list[dict[str, object]],
    rewrites: dict[str, StoryRewrite],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for story in stories:
        story_id = str(story.get("story_id", ""))
        rewrite = rewrites.get(story_id)
        if not story_id or rewrite is None:
            continue
        representative = representative_article(story)
        url = str(representative.get("url", "")).strip()
        if not url:
            continue
        article_links = []
        raw_articles = story.get("articles", [])
        if isinstance(raw_articles, list):
            for article in raw_articles:
                if not isinstance(article, dict):
                    continue
                article_url = str(article.get("url", "")).strip()
                if not article_url:
                    continue
                article_links.append(
                    {
                        "source_name": str(
                            article.get("source_name") or article.get("source_id") or ""
                        ),
                        "title": str(article.get("title", "")),
                        "published_at": str(article.get("published_at", "")),
                        "url": article_url,
                    }
                )
        if not article_links:
            article_links.append(
                {
                    "source_name": str(
                        representative.get("source_name")
                        or representative.get("source_id")
                        or ""
                    ),
                    "title": str(representative.get("title", "")),
                    "published_at": str(representative.get("published_at", "")),
                    "url": url,
                }
            )
        candidates.append(
            {
                "story_id": story_id,
                "section": rewrite.section,
                "headline": rewrite.headline,
                "summary": rewrite.summary,
                "rewrite_status": rewrite.status,
                "rewrite_error": rewrite.error,
                "source_id": str(representative.get("source_id", "")),
                "source_name": str(representative.get("source_name", "")),
                "published_at": str(representative.get("published_at", "")),
                "url": url,
                "articles": article_links,
                "article_count": int(story.get("article_count", 1) or 1),
                "source_count": int(story.get("source_count", 1) or 1),
                "confidence": story.get("confidence"),
            }
        )
    return candidates


def select_stories(
    candidates: list[dict[str, object]],
    *,
    target_items: int = 10,
    max_items_per_source: int = 3,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    ranked = sorted(candidates, key=selection_key, reverse=True)
    selected: list[dict[str, object]] = []
    selected_ids: set[str] = set()
    source_counts: dict[str, int] = {}
    available_sources = {
        str(candidate.get("source_id", ""))
        for candidate in ranked
        if str(candidate.get("source_id", ""))
    }
    source_goal = min(4, len(available_sources))

    def can_add(candidate: dict[str, object]) -> bool:
        if len(selected) >= target_items:
            return False
        story_id = str(candidate["story_id"])
        source_id = str(candidate.get("source_id", ""))
        return (
            story_id not in selected_ids
            and source_counts.get(source_id, 0) < max_items_per_source
        )

    def add(candidate: dict[str, object]) -> None:
        selected.append(candidate)
        selected_ids.add(str(candidate["story_id"]))
        source_id = str(candidate.get("source_id", ""))
        source_counts[source_id] = source_counts.get(source_id, 0) + 1

    # Establish publisher diversity before filling the edition.
    for candidate in ranked:
        if len({str(item.get("source_id", "")) for item in selected}) >= source_goal:
            break
        source_id = str(candidate.get("source_id", ""))
        if source_id not in {str(item.get("source_id", "")) for item in selected} and can_add(candidate):
            add(candidate)

    # Give each available section one opportunity before adding repeats.
    for section in SECTION_ORDER:
        candidate = next(
            (
                item
                for item in ranked
                if item.get("section") == section and can_add(item)
            ),
            None,
        )
        if candidate is not None:
            add(candidate)

    for candidate in ranked:
        if can_add(candidate):
            add(candidate)

    diagnostics = {
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "available_source_count": len(available_sources),
        "selected_source_count": len(
            {str(item.get("source_id", "")) for item in selected}
        ),
        "source_counts": source_counts,
        "target_items": target_items,
        "max_items_per_source": max_items_per_source,
    }
    return selected, diagnostics


def preselect_stories(
    stories: list[dict[str, object]],
    *,
    target_items: int = 10,
    max_items_per_source: int = 3,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Rank raw story clusters and limit expensive rewrites to likely selections."""
    ranked = sorted(stories, key=story_selection_key, reverse=True)
    selected: list[dict[str, object]] = []
    source_counts: dict[str, int] = {}
    for story in ranked:
        if len(selected) >= target_items:
            break
        representative = representative_article(story)
        source_id = str(representative.get("source_id", ""))
        if not str(representative.get("url", "")).strip():
            continue
        if source_counts.get(source_id, 0) >= max_items_per_source:
            continue
        selected.append(story)
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
    return selected, {
        "input_story_count": len(stories),
        "preselected_story_count": len(selected),
        "target_items": target_items,
        "max_items_per_source": max_items_per_source,
        "source_counts": source_counts,
        "preselected_story_ids": [str(story.get("story_id", "")) for story in selected],
    }


def representative_article(story: dict[str, object]) -> dict[str, object]:
    representative_id = str(story.get("representative_article_id", ""))
    articles = story.get("articles", [])
    if not isinstance(articles, list):
        return {}
    for article in articles:
        if isinstance(article, dict) and str(article.get("article_id", "")) == representative_id:
            return article
    for article in articles:
        if isinstance(article, dict):
            return article
    return {}


def selection_key(candidate: dict[str, object]) -> tuple[int, int, datetime, float, str]:
    return (
        int(candidate.get("article_count", 1) or 1),
        int(candidate.get("source_count", 1) or 1),
        parse_datetime(str(candidate.get("published_at", ""))),
        float(candidate.get("confidence") or 0.0),
        str(candidate.get("story_id", "")),
    )


def story_selection_key(story: dict[str, object]) -> tuple[int, int, datetime, float, str]:
    return (
        int(story.get("article_count", 1) or 1),
        int(story.get("source_count", 1) or 1),
        parse_datetime(str(story.get("latest_published_at", ""))),
        float(story.get("confidence") or 0.0),
        str(story.get("story_id", "")),
    )


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
