from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from headlyn.ingestion.artifacts import write_json, write_jsonl
from headlyn.story_index.hybrid_index import HybridStoryIndex

from .clusterer import StoryClusterer
from .models import AssignmentResult, PreparedDocument, StoryClusteringConfig, StoryClusteringResult


def run_story_clustering(
    config: StoryClusteringConfig,
    *,
    documents: Sequence[PreparedDocument],
    index: HybridStoryIndex,
    clock: Callable[[], datetime] | None = None,
) -> StoryClusteringResult:
    """Run incremental story assignment and write clustering artifacts."""
    validate_config(config)
    output_dir = config.artifact_root or Path("artifacts/stages")
    output_dir = output_dir / "story_clustering" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure both storage adapters are ready before mutating story state.
    index.initialize()
    clusterer = StoryClusterer(index=index, config=config, clock=clock)
    closed_story_ids = clusterer.close_inactive()
    results: list[AssignmentResult] = []
    ordered_documents = list(documents)
    if config.order_by_published_at:
        ordered_documents.sort(key=lambda item: item.document.published_at)
    for prepared in ordered_documents:
        try:
            results.append(clusterer.process_document(prepared))
        except (ValueError, RuntimeError) as exc:
            results.append(
                AssignmentResult(
                    document_id=prepared.document.document_id,
                    story_id=None,
                    decision="failed",
                    score=None,
                    candidate_count=0,
                    degraded=prepared.entities.status != "ok",
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )

    write_jsonl(output_dir / "story_assignments.jsonl", [result.as_dict() for result in results])
    stories = [story_to_newsletter(story) for story in index.get_active_stories()]
    write_jsonl(output_dir / "stories.jsonl", stories)
    write_json(output_dir / "newsletter_stories.json", {"stage": "story_clustering", "run_id": config.run_id, "stories": stories})
    summary = {
        "stage": "story_clustering",
        "run_id": config.run_id,
        "status": "failed" if not documents else "partial" if any(result.decision == "failed" for result in results) else "ok",
        "input_count": len(documents),
        "attached_count": sum(result.decision == "attached" for result in results),
        "singleton_count": sum(result.decision == "singleton" for result in results),
        "skipped_count": sum(result.decision == "skipped" for result in results),
        "failed_count": sum(result.decision == "failed" for result in results),
        "closed_story_count": len(closed_story_ids),
        "story_count": len(stories),
        "match_threshold": config.match_threshold,
        "active_window_hours": config.active_window_hours,
        "output_files": ["story_assignments.jsonl", "stories.jsonl", "newsletter_stories.json", "summary.json"],
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    return StoryClusteringResult(
        run_id=config.run_id,
        status=str(summary["status"]),
        input_count=len(documents),
        attached_count=summary["attached_count"],
        singleton_count=summary["singleton_count"],
        skipped_count=summary["skipped_count"],
        failed_count=summary["failed_count"],
        output_dir=output_dir,
        summary_path=summary_path,
    )


def story_to_newsletter(story) -> dict[str, object]:
    """Serialize persisted story state in the newsletter-compatible shape."""
    representative = next(
        (document for document in story.member_documents if document.get("document_id") == story.representative_document_id),
        {},
    )
    return {
        "story_id": story.story_id,
        "representative_article_id": story.representative_document_id,
        "representative_title": representative.get("title", ""),
        "representative_description": representative.get("body_text", story.canonical_text),
        "latest_published_at": story.latest_published_at.isoformat(),
        "source_count": story.source_count,
        "article_count": story.document_count,
        "confidence": None,
        "articles": story.member_documents,
    }


def validate_config(config: StoryClusteringConfig) -> None:
    """Validate clustering weights, limits, and lifecycle configuration."""
    if not config.run_id.strip():
        raise ValueError("run_id is required")
    if not 0 <= config.match_threshold <= 1:
        raise ValueError("match_threshold must be between 0 and 1")
    weights = (config.semantic_weight, config.lexical_weight, config.entity_weight, config.temporal_weight)
    if any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError("score weights must be non-negative and have a positive sum")
    if config.active_window_hours < 1 or config.dense_limit < 1 or config.lexical_limit < 1:
        raise ValueError("lifecycle and retrieval limits must be positive")
