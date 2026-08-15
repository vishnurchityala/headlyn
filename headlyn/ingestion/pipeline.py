from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import relative_to_root, write_bytes, write_json, write_jsonl
from .fetch import fetch_feed
from .models import FeedConfig, PipelineConfig, PipelineResult, SourceResult
from .normalize import normalize_entries
from .parse import parse_rss
from .registry import available_sources, get_feed


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = ROOT_DIR / "artifacts" / "stages"


def run_pipeline(config: PipelineConfig | None = None) -> PipelineResult:
    """Fetch and normalize all selected RSS sources concurrently."""
    config = config or PipelineConfig()
    validate_config(config)
    feeds = [get_feed(source_id) for source_id in selected_source_ids(config)]
    run_id = config.run_id or utc_run_id()
    artifact_root = config.artifact_root or DEFAULT_ARTIFACT_ROOT
    output_dir = artifact_root / "rss_ingestion" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline_started_at = utc_now_iso()

    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=min(config.max_workers, len(feeds))) as executor:
        futures: dict[Future[SourceResult], str] = {
            executor.submit(run_source, config, feed, run_id, artifact_root): feed.source_id
            for feed in feeds
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: selected_source_ids(config).index(result.source_id))
    successful_count = sum(result.status == "ok" for result in results)
    failed_count = len(results) - successful_count
    status = "ok" if failed_count == 0 else "partial" if successful_count else "failed"
    summary = {
        "run_id": run_id,
        "status": status,
        "mode": config.mode,
        "snapshot_date": config.snapshot_date,
        "source_count": len(results),
        "successful_source_count": successful_count,
        "failed_source_count": failed_count,
        "item_count": sum(result.item_count for result in results),
        "duplicate_count": sum(result.duplicate_count for result in results),
        "sources": [result.as_dict() for result in results],
        "started_at": pipeline_started_at,
        "completed_at": utc_now_iso(),
        "output_files": [
            *[f"{result.source_id}/summary.json" for result in results],
            "summary.json",
        ],
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    return PipelineResult(
        run_id=run_id,
        status=status,
        source_results=tuple(results),
        output_dir=output_dir,
        summary_path=summary_path,
    )


def run_source(
    config: PipelineConfig,
    feed: FeedConfig,
    run_id: str,
    artifact_root: Path,
) -> SourceResult:
    output_dir = artifact_root / "rss_ingestion" / run_id / feed.source_id
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now_iso()
    summary_path = output_dir / "summary.json"
    try:
        response = fetch_feed(config, feed)
        entries = parse_rss(response.payload)
        limit = config.limit or feed.max_items
        items, duplicate_count = normalize_entries(
            feed,
            entries,
            limit=limit,
            ingested_at=started_at,
        )
        write_bytes(output_dir / "feed.xml", response.payload)
        write_jsonl(output_dir / "items.jsonl", [item.as_dict() for item in items])
        write_json(
            summary_path,
            {
                "run_id": run_id,
                "source_id": feed.source_id,
                "source_name": feed.name,
                "website_url": feed.website_url,
                "mode": config.mode,
                "snapshot_date": config.snapshot_date,
                "status": "ok",
                "feed_url": feed.feed_url,
                "input_path": relative_to_root(response.input_path, ROOT_DIR)
                if response.input_path
                else None,
                "http_status": response.http_status,
                "feed_bytes": len(response.payload),
                "parsed_item_count": len(entries),
                "written_item_count": len(items),
                "duplicate_count": duplicate_count,
                "started_at": started_at,
                "completed_at": utc_now_iso(),
                "output_files": ["feed.xml", "items.jsonl", "summary.json"],
            },
        )
        return SourceResult(
            source_id=feed.source_id,
            status="ok",
            item_count=len(items),
            duplicate_count=duplicate_count,
            output_dir=output_dir,
            summary_path=summary_path,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc) or 'unknown error'}"
        write_json(
            summary_path,
            {
                "run_id": run_id,
                "source_id": feed.source_id,
                "source_name": feed.name,
                "website_url": feed.website_url,
                "mode": config.mode,
                "snapshot_date": config.snapshot_date,
                "status": "failed",
                "feed_url": feed.feed_url,
                "error": error,
                "started_at": started_at,
                "completed_at": utc_now_iso(),
                "output_files": ["summary.json"],
            },
        )
        return SourceResult(
            source_id=feed.source_id,
            status="failed",
            item_count=0,
            duplicate_count=0,
            output_dir=output_dir,
            summary_path=summary_path,
            error=error,
        )


def selected_source_ids(config: PipelineConfig) -> tuple[str, ...]:
    return config.source_ids or available_sources()


def validate_config(config: PipelineConfig) -> None:
    if config.mode not in {"live", "snapshot"}:
        raise ValueError("mode must be 'live' or 'snapshot'")
    if config.mode == "snapshot" and not config.snapshot_date:
        raise ValueError("snapshot mode requires snapshot_date")
    if config.limit is not None and config.limit < 1:
        raise ValueError("limit must be positive")
    if config.retries < 1:
        raise ValueError("retries must be at least one")
    if config.max_workers < 1:
        raise ValueError("max_workers must be at least one")
    source_ids = selected_source_ids(config)
    if not source_ids:
        raise ValueError("at least one source is required")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("source IDs must be unique")


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Headlyn RSS ingestion pipeline")
    parser.add_argument(
        "--source",
        dest="source_ids",
        action="append",
        choices=available_sources(),
        help="source to include; repeat for multiple sources (default: all)",
    )
    parser.add_argument("--mode", choices=("live", "snapshot"), default="live")
    parser.add_argument("--snapshot-date")
    parser.add_argument("--run-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_pipeline(
            PipelineConfig(
                mode=args.mode,
                snapshot_date=args.snapshot_date,
                run_id=args.run_id,
                artifact_root=args.artifact_root,
                source_ids=tuple(args.source_ids) if args.source_ids else None,
                limit=args.limit,
                max_workers=args.max_workers,
            )
        )
    except (ValueError, OSError) as exc:
        print(f"rss_pipeline: failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "status": result.status,
                "source_count": len(result.source_results),
                "successful_source_count": sum(
                    source.status == "ok" for source in result.source_results
                ),
                "item_count": sum(source.item_count for source in result.source_results),
                "output_dir": str(result.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
