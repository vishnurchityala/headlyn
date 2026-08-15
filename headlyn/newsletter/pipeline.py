from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from headlyn.ingestion.artifacts import write_json, write_jsonl

from .delivery import MailSender, SmtpMailSender
from .models import NewsletterConfig, NewsletterResult
from .render import render_html, render_text
from .rewrite import (
    OllamaStoryRewriter,
    StoryRewriter,
    fallback_rewrite,
    story_fingerprint,
)
from .select import prepare_candidates, select_stories


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = ROOT_DIR / "artifacts" / "stages"
STAGE_NAME = "daily_newsletter"


def run_newsletter(
    config: NewsletterConfig,
    *,
    rewriter: StoryRewriter | None = None,
    sender: MailSender | None = None,
) -> NewsletterResult:
    validate_config(config)
    artifact_root = config.artifact_root or DEFAULT_ARTIFACT_ROOT
    story_dir = artifact_root / "story_normalization" / config.story_run_id
    story_path = story_dir / "newsletter_stories.json"
    if not story_path.exists():
        raise FileNotFoundError(f"story artifact not found: {story_path}")

    output_dir = artifact_root / STAGE_NAME / config.edition_date
    output_dir.mkdir(parents=True, exist_ok=True)
    delivery_path = output_dir / "delivery.json"
    prior_delivery = read_json(delivery_path) if delivery_path.exists() else {}
    if config.send and prior_delivery.get("status") == "sent" and not config.force_resend:
        raise RuntimeError(
            f"edition {config.edition_date} was already sent; use --force-resend to resend"
        )

    edition_path = output_dir / "newsletter.json"
    if edition_path.exists() and not config.force_rebuild:
        edition = read_json(edition_path)
        selection_diagnostics = read_json(output_dir / "selection.json").get(
            "diagnostics", {}
        ) if (output_dir / "selection.json").exists() else {}
        html_body = (output_dir / "newsletter.html").read_text(encoding="utf-8")
        text_body = (output_dir / "newsletter.txt").read_text(encoding="utf-8")
    else:
        stories = load_stories(story_path)
        rewrite_engine = rewriter or OllamaStoryRewriter(
            model_name=config.llm_model,
            endpoint=config.llm_endpoint,
            timeout_seconds=config.llm_timeout_seconds,
        )
        rewrites = rewrite_stories(
            stories,
            rewrite_engine,
            output_dir / "rewrites.jsonl",
        )
        candidates = prepare_candidates(stories, rewrites)
        selected, selection_diagnostics = select_stories(
            candidates,
            target_items=config.target_items,
            max_items_per_source=config.max_items_per_source,
        )
        write_json(
            output_dir / "selection.json",
            {
                "selected_story_ids": [story["story_id"] for story in selected],
                "diagnostics": selection_diagnostics,
            },
        )
        edition = {
            "stage": STAGE_NAME,
            "edition_date": config.edition_date,
            "story_run_id": config.story_run_id,
            "generated_at": datetime.now().astimezone().isoformat(),
            "status": "ready" if len(selected) >= config.minimum_items else "held",
            "unsubscribe_instructions": (
                config.unsubscribe_instructions
                or os.environ.get(
                    "HEADLYN_UNSUBSCRIBE_INSTRUCTIONS",
                    "Reply to this email to unsubscribe.",
                )
            ),
            "stories": selected,
        }
        write_json(edition_path, edition)
        html_body = render_html(edition)
        text_body = render_text(edition)
        (output_dir / "newsletter.html").write_text(html_body, encoding="utf-8")
        (output_dir / "newsletter.txt").write_text(text_body, encoding="utf-8")

    selected_count = len(edition.get("stories", []))
    ready = selected_count >= config.minimum_items
    if config.send and ready:
        mail_sender = sender or SmtpMailSender()
        recipient_count = mail_sender.send(edition, html_body, text_body)
        delivery = {
            "status": "sent",
            "edition_date": config.edition_date,
            "recipient_count": recipient_count,
            "sent_at": datetime.now().astimezone().isoformat(),
        }
        result_status = "sent"
    elif not ready:
        delivery = {
            "status": "held",
            "edition_date": config.edition_date,
            "reason": "fewer than minimum valid stories",
        }
        result_status = "held"
    else:
        delivery = {
            "status": "preview",
            "edition_date": config.edition_date,
            "recipient_count": 0,
        }
        result_status = "preview"
    write_json(delivery_path, delivery)

    rewrites_path = output_dir / "rewrites.jsonl"
    fallback_count = count_fallbacks(rewrites_path)
    summary = {
        "stage": STAGE_NAME,
        "status": result_status,
        "edition_date": config.edition_date,
        "story_run_id": config.story_run_id,
        "candidate_count": selection_diagnostics.get("candidate_count", 0),
        "selected_story_count": selected_count,
        "minimum_items": config.minimum_items,
        "target_items": config.target_items,
        "rewrite_fallback_count": fallback_count,
        "delivery_status": delivery["status"],
        "output_files": [
            "rewrites.jsonl",
            "selection.json",
            "newsletter.json",
            "newsletter.html",
            "newsletter.txt",
            "delivery.json",
            "summary.json",
        ],
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    return NewsletterResult(
        edition_date=config.edition_date,
        story_run_id=config.story_run_id,
        status=result_status,
        selected_story_count=selected_count,
        output_dir=output_dir,
        summary_path=summary_path,
    )


def load_stories(path: Path) -> list[dict[str, object]]:
    value = read_json(path)
    stories = value.get("stories")
    if not isinstance(stories, list):
        raise ValueError(f"story artifact has no stories list: {path}")
    return [story for story in stories if isinstance(story, dict)]


def rewrite_stories(
    stories: list[dict[str, object]],
    rewriter: StoryRewriter,
    cache_path: Path,
) -> dict[str, object]:
    cached = load_rewrite_cache(cache_path, rewriter.model_name)
    results: dict[str, object] = {}
    for story in stories:
        story_id = str(story.get("story_id", ""))
        if not story_id:
            continue
        fingerprint = story_fingerprint(story)
        cached_rewrite = cached.get(story_id)
        if cached_rewrite and cached_rewrite.input_fingerprint == fingerprint:
            results[story_id] = cached_rewrite
            continue
        try:
            results[story_id] = rewriter.rewrite(story)
        except Exception as exc:
            results[story_id] = fallback_rewrite(
                story,
                model_name=rewriter.model_name,
                error=f"{type(exc).__name__}: {str(exc) or 'unknown error'}",
            )
    write_jsonl(cache_path, [result.as_dict() for result in results.values()])
    return results


def load_rewrite_cache(path: Path, model_name: str) -> dict[str, object]:
    if not path.exists():
        return {}
    results: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if value.get("model") != model_name:
                continue
            from .models import StoryRewrite

            rewrite = StoryRewrite(
                story_id=str(value["story_id"]),
                headline=str(value["headline"]),
                summary=str(value["summary"]),
                section=str(value["section"]),
                status=str(value.get("status", "fallback")),
                model=str(value["model"]),
                input_fingerprint=str(value["input_fingerprint"]),
                error=value.get("error"),
            )
            results[rewrite.story_id] = rewrite
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
    return results


def count_fallbacks(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            count += json.loads(line).get("status") == "fallback"
        except json.JSONDecodeError:
            continue
    return count


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def validate_config(config: NewsletterConfig) -> None:
    try:
        datetime.strptime(config.edition_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("edition_date must use YYYY-MM-DD") from exc
    if not config.story_run_id.strip():
        raise ValueError("story_run_id is required")
    if config.llm_timeout_seconds < 1:
        raise ValueError("llm_timeout_seconds must be positive")
    if config.minimum_items < 1 or config.target_items < config.minimum_items:
        raise ValueError("target_items must be at least minimum_items")
    if config.max_items_per_source < 1:
        raise ValueError("max_items_per_source must be positive")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and deliver a Headlyn newsletter")
    parser.add_argument("--story-run-id", required=True)
    parser.add_argument("--edition-date", required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--llm-model", default="gemma4:e4b-it-q4_K_M")
    parser.add_argument("--llm-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--llm-timeout-seconds", type=int, default=120)
    parser.add_argument("--target-items", type=int, default=10)
    parser.add_argument("--minimum-items", type=int, default=5)
    parser.add_argument("--max-items-per-source", type=int, default=3)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--force-resend", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_newsletter(
            NewsletterConfig(
                story_run_id=args.story_run_id,
                edition_date=args.edition_date,
                artifact_root=args.artifact_root,
                llm_model=args.llm_model,
                llm_endpoint=args.llm_endpoint,
                llm_timeout_seconds=args.llm_timeout_seconds,
                target_items=args.target_items,
                minimum_items=args.minimum_items,
                max_items_per_source=args.max_items_per_source,
                send=args.send,
                force_rebuild=args.force_rebuild,
                force_resend=args.force_resend,
            )
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"newsletter_pipeline: failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "edition_date": result.edition_date,
                "story_run_id": result.story_run_id,
                "status": result.status,
                "selected_story_count": result.selected_story_count,
                "output_dir": str(result.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status in {"preview", "sent", "held"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
