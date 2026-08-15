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


def selection_key(candidate: dict[str, object]) -> tuple[datetime, int, int, float, str]:
    return (
        parse_datetime(str(candidate.get("published_at", ""))),
        int(candidate.get("source_count", 1) or 1),
        int(candidate.get("article_count", 1) or 1),
        float(candidate.get("confidence") or 0.0),
        str(candidate.get("story_id", "")),
    )


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
