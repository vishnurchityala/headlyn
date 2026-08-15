from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from headlyn.ingestion.artifacts import relative_to_root, write_json, write_jsonl
from headlyn.ingestion.normalize import normalize_title, normalize_url

from .lexical import BgeM3LexicalScorer, LexicalScorer
from .llm import EntityExtractor, OllamaEntityExtractor, input_fingerprint
from .models import EntityExtraction, ExtractedEntity, PairScore, StoryNormalizationConfig, StoryNormalizationResult


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = ROOT_DIR / "artifacts" / "stages"
STAGE_NAME = "story_normalization"


def run_story_normalization(
    config: StoryNormalizationConfig,
    *,
    entity_extractor: EntityExtractor | None = None,
    lexical_scorer: LexicalScorer | None = None,
) -> StoryNormalizationResult:
    """Normalize one RSS ingestion run into source-linked story groups."""
    validate_config(config)
    artifact_root = config.artifact_root or DEFAULT_ARTIFACT_ROOT
    ingestion_dir = artifact_root / "rss_ingestion" / config.ingestion_run_id
    if not ingestion_dir.is_dir():
        raise FileNotFoundError(f"ingestion run not found: {ingestion_dir}")
    output_dir = artifact_root / STAGE_NAME / config.ingestion_run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    source_ids = load_source_ids(ingestion_dir, config.source_ids)
    items, invalid_count, missing_source_count = load_items(
        ingestion_dir,
        source_ids,
        max_items_per_source=config.max_items_per_source,
    )
    items, input_duplicate_count = deduplicate_items(items)

    extractor = entity_extractor or OllamaEntityExtractor(
        model_name=config.entity_model,
        endpoint=config.llm_endpoint,
        timeout_seconds=config.llm_timeout_seconds,
    )
    scorer = lexical_scorer or BgeM3LexicalScorer(
        model_name=config.lexical_model,
        batch_size=config.lexical_batch_size,
        max_length=config.lexical_max_length,
        use_fp16=config.use_fp16,
    )
    extractions = extract_entities(items, extractor, output_dir / "entity_extractions.jsonl")
    write_jsonl(
        output_dir / "entity_extractions.jsonl",
        [extractions[item["article_id"]].as_dict() for item in items],
    )

    candidates = build_candidates(items, extractions, config.require_primary_entity)
    pair_scores = score_candidates(items, candidates, scorer, config)
    write_jsonl(output_dir / "pair_scores.jsonl", [pair.as_dict() for pair in pair_scores])

    accepted_pairs = [pair for pair in pair_scores if pair.accepted]
    stories = build_stories(items, accepted_pairs)
    write_jsonl(output_dir / "stories.jsonl", stories)
    write_json(
        output_dir / "accepted_stories_debug.json",
        build_accepted_stories_debug(stories, items, extractions, accepted_pairs),
    )
    write_json(
        output_dir / "newsletter_stories.json",
        {
            "stage": STAGE_NAME,
            "ingestion_run_id": config.ingestion_run_id,
            "entity_model": extractor.model_name,
            "lexical_model": scorer.model_name,
            "stories": stories,
        },
    )

    extraction_failures = sum(
        extraction.status != "ok" for extraction in extractions.values()
    )
    multi_source_count = sum(story["source_count"] > 1 for story in stories)
    status = "failed" if not items else "partial" if extraction_failures else "ok"
    summary = {
        "stage": STAGE_NAME,
        "status": status,
        "ingestion_run_id": config.ingestion_run_id,
        "ingestion_input": relative_to_root(ingestion_dir, ROOT_DIR),
        "source_ids": source_ids,
        "candidate_item_count": len(items) + input_duplicate_count,
        "unique_item_count": len(items),
        "max_items_per_source": config.max_items_per_source,
        "invalid_item_count": invalid_count,
        "missing_source_count": missing_source_count,
        "input_duplicate_count": input_duplicate_count,
        "entity_extraction_count": len(extractions),
        "entity_extraction_failure_count": extraction_failures,
        "candidate_pair_count": len(candidates),
        "accepted_pair_count": len(accepted_pairs),
        "story_count": len(stories),
        "multi_source_story_count": multi_source_count,
        "singleton_story_count": sum(story["article_count"] == 1 for story in stories),
        "entity_model": extractor.model_name,
        "lexical_model": scorer.model_name,
        "entity_weight": config.entity_weight,
        "lexical_weight": config.lexical_weight,
        "merge_threshold": config.merge_threshold,
        "output_files": [
            "entity_extractions.jsonl",
            "pair_scores.jsonl",
            "stories.jsonl",
            "accepted_stories_debug.json",
            "newsletter_stories.json",
            "summary.json",
        ],
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    return StoryNormalizationResult(
        ingestion_run_id=config.ingestion_run_id,
        status=status,
        item_count=len(items),
        story_count=len(stories),
        output_dir=output_dir,
        summary_path=summary_path,
    )


def load_source_ids(ingestion_dir: Path, requested: tuple[str, ...] | None) -> tuple[str, ...]:
    if requested:
        return requested
    summary_path = ingestion_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        source_ids = tuple(
            source["source_id"]
            for source in summary.get("sources", [])
            if source.get("source_id")
        )
        if source_ids:
            return source_ids
    return tuple(sorted(path.name for path in ingestion_dir.iterdir() if path.is_dir()))


def load_items(
    ingestion_dir: Path,
    source_ids: tuple[str, ...],
    *,
    max_items_per_source: int | None = None,
) -> tuple[list[dict[str, object]], int, int]:
    items: list[dict[str, object]] = []
    invalid_count = 0
    missing_source_count = 0
    for source_id in source_ids:
        path = ingestion_dir / source_id / "items.jsonl"
        if not path.exists():
            missing_source_count += 1
            continue
        source_item_count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                invalid_count += 1
                continue
            if isinstance(item, dict) and not str(item.get("description", "")).strip():
                title = str(item.get("title", "")).strip()
                if title:
                    item["description"] = title
            if not isinstance(item, dict) or not valid_item(item):
                invalid_count += 1
                continue
            items.append(item)
            source_item_count += 1
            if max_items_per_source is not None and source_item_count >= max_items_per_source:
                break
    return items, invalid_count, missing_source_count


def valid_item(item: dict[str, object]) -> bool:
    required = ("article_id", "source_id", "source_name", "title", "description", "published_at", "url")
    return all(isinstance(item.get(field), str) and item[field].strip() for field in required)


def deduplicate_items(items: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    unique: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    duplicates = 0
    for item in items:
        url = normalize_url(str(item["url"]))
        title = normalize_title(str(item["title"]))
        if url in seen_urls or title in seen_titles:
            duplicates += 1
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        unique.append(item)
    return unique, duplicates


def extract_entities(
    items: list[dict[str, object]],
    extractor: EntityExtractor,
    cache_path: Path,
) -> dict[str, EntityExtraction]:
    cached = load_extraction_cache(cache_path, extractor.model_name)
    result: dict[str, EntityExtraction] = {}
    for item in items:
        article_id = str(item["article_id"])
        fingerprint = input_fingerprint(item)
        cached_extraction = cached.get(article_id)
        if cached_extraction and cached_extraction.input_fingerprint == fingerprint:
            result[article_id] = cached_extraction
            continue
        try:
            extraction = extractor.extract(item)
        except Exception as exc:
            extraction = EntityExtraction(
                article_id=article_id,
                input_fingerprint=fingerprint,
                model=extractor.model_name,
                status="failed",
                error=f"{type(exc).__name__}: {str(exc) or 'unknown error'}",
            )
        result[article_id] = extraction
    return result


def load_extraction_cache(path: Path, model_name: str) -> dict[str, EntityExtraction]:
    if not path.exists():
        return {}
    result: dict[str, EntityExtraction] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if value.get("model") != model_name:
                continue
            entities = tuple(
                ExtractedEntity(
                    text=str(entity.get("text", "")),
                    canonical_name=str(entity.get("canonical_name", "")),
                    entity_type=str(entity.get("type", "OTHER")),
                    role=str(entity.get("role", "secondary")),
                )
                for entity in value.get("entities", [])
                if entity.get("canonical_name")
            )
            extraction = EntityExtraction(
                article_id=str(value["article_id"]),
                input_fingerprint=str(value["input_fingerprint"]),
                model=str(value["model"]),
                status=str(value.get("status", "failed")),
                entities=entities,
                error=value.get("error"),
            )
            result[extraction.article_id] = extraction
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
    return result


def build_candidates(
    items: list[dict[str, object]],
    extractions: dict[str, EntityExtraction],
    require_primary_entity: bool,
) -> list[tuple[int, int, tuple[str, ...], float]]:
    candidates: list[tuple[int, int, tuple[str, ...], float]] = []
    for index, left in enumerate(items):
        left_extraction = extractions[str(left["article_id"])]
        for right_index in range(index + 1, len(items)):
            right = items[right_index]
            right_extraction = extractions[str(right["article_id"])]
            shared_primary = (
                left_extraction.distinctive_primary_entities
                & right_extraction.distinctive_primary_entities
            )
            shared_entities = left_extraction.all_entities & right_extraction.all_entities
            if require_primary_entity and not shared_primary:
                continue
            if not shared_entities:
                continue
            denominator = min(
                len(left_extraction.all_entities),
                len(right_extraction.all_entities),
            )
            entity_score = len(shared_entities) / denominator if denominator else 0.0
            candidates.append((index, right_index, tuple(sorted(shared_entities)), entity_score))
    return candidates


def score_candidates(
    items: list[dict[str, object]],
    candidates: list[tuple[int, int, tuple[str, ...], float]],
    scorer: LexicalScorer,
    config: StoryNormalizationConfig,
) -> list[PairScore]:
    text_pairs = [
        (article_text(items[left]), article_text(items[right]))
        for left, right, _, _ in candidates
    ]
    lexical_scores = scorer.score_pairs(text_pairs)
    if len(lexical_scores) != len(candidates):
        raise RuntimeError("lexical scorer returned an unexpected number of scores")
    results: list[PairScore] = []
    for candidate, lexical_score in zip(candidates, lexical_scores):
        left_index, right_index, shared_entities, entity_score = candidate
        final_score = (
            config.entity_weight * entity_score
            + config.lexical_weight * lexical_score
        )
        accepted = final_score >= config.merge_threshold
        results.append(
            PairScore(
                article_id_a=str(items[left_index]["article_id"]),
                article_id_b=str(items[right_index]["article_id"]),
                source_id_a=str(items[left_index]["source_id"]),
                source_id_b=str(items[right_index]["source_id"]),
                shared_entities=shared_entities,
                entity_score=entity_score,
                lexical_score=lexical_score,
                final_score=final_score,
                accepted=accepted,
                rejection_reason=None if accepted else "below_merge_threshold",
            )
        )
    return results


def build_stories(
    items: list[dict[str, object]],
    accepted_pairs: list[PairScore],
) -> list[dict[str, object]]:
    items_by_id = {str(item["article_id"]): item for item in items}
    accepted_by_pair = {
        frozenset((pair.article_id_a, pair.article_id_b)): pair
        for pair in accepted_pairs
    }
    ordered_ids = sorted(
        items_by_id,
        key=lambda article_id: representative_key(items_by_id[article_id]),
        reverse=True,
    )
    unassigned = set(ordered_ids)
    stories: list[dict[str, object]] = []
    while unassigned:
        seed_id = next(article_id for article_id in ordered_ids if article_id in unassigned)
        cluster_ids = [seed_id]
        unassigned.remove(seed_id)
        for candidate_id in ordered_ids:
            if candidate_id not in unassigned:
                continue
            pair = accepted_by_pair.get(frozenset((seed_id, candidate_id)))
            if pair is None:
                continue
            cluster_ids.append(candidate_id)
            unassigned.remove(candidate_id)
        stories.append(build_story([items_by_id[article_id] for article_id in cluster_ids], accepted_by_pair))
    return stories


def build_story(
    cluster: list[dict[str, object]],
    accepted_by_pair: dict[frozenset[str], PairScore],
) -> dict[str, object]:
    representative = max(cluster, key=representative_key)
    article_ids = sorted(str(item["article_id"]) for item in cluster)
    story_id = "story-" + sha256("|".join(article_ids).encode("utf-8")).hexdigest()[:24]
    pair_scores = [
        pair.final_score
        for index, left in enumerate(article_ids)
        for right in article_ids[index + 1 :]
        if (pair := accepted_by_pair.get(frozenset((left, right)))) is not None
        and pair.final_score is not None
    ]
    article_records = [
        {
            "article_id": str(item["article_id"]),
            "source_id": str(item["source_id"]),
            "source_name": str(item["source_name"]),
            "title": str(item["title"]),
            "description": str(item["description"]),
            "published_at": str(item["published_at"]),
            "url": str(item["url"]),
        }
        for item in cluster
    ]
    return {
        "story_id": story_id,
        "representative_article_id": str(representative["article_id"]),
        "representative_title": str(representative["title"]),
        "representative_description": str(representative["description"]),
        "latest_published_at": max(str(item["published_at"]) for item in cluster),
        "source_count": len({str(item["source_id"]) for item in cluster}),
        "article_count": len(cluster),
        "confidence": round(sum(pair_scores) / len(pair_scores), 6) if pair_scores else None,
        "articles": article_records,
    }


def build_accepted_stories_debug(
    stories: list[dict[str, object]],
    items: list[dict[str, object]],
    extractions: dict[str, EntityExtraction],
    accepted_pairs: list[PairScore],
) -> dict[str, object]:
    """Build a human-inspectable artifact for stories formed by accepted pairs."""
    items_by_id = {str(item["article_id"]): item for item in items}
    debug_stories: list[dict[str, object]] = []
    debug_article_count = 0
    debug_pair_count = 0
    for story in stories:
        story_articles = story.get("articles", [])
        article_ids = [
            str(article["article_id"])
            for article in story_articles
            if isinstance(article, dict) and article.get("article_id")
        ]
        article_id_set = set(article_ids)
        if len(article_id_set) < 2:
            continue
        article_records = [
            build_debug_article(items_by_id[article_id], extractions[article_id])
            for article_id in article_ids
        ]
        story_pair_scores = [
            pair.as_dict()
            for pair in accepted_pairs
            if {pair.article_id_a, pair.article_id_b} <= article_id_set
        ]
        debug_story = dict(story)
        debug_story["articles"] = article_records
        debug_story["accepted_pair_scores"] = story_pair_scores
        debug_stories.append(debug_story)
        debug_article_count += len(article_records)
        debug_pair_count += len(story_pair_scores)

    return {
        "stage": STAGE_NAME,
        "debug_scope": "stories containing at least one accepted pair",
        "accepted_story_count": len(debug_stories),
        "article_count": debug_article_count,
        "accepted_pair_count": debug_pair_count,
        "pipeline_accepted_pair_count": len(accepted_pairs),
        "stories": debug_stories,
    }


def build_debug_article(
    item: dict[str, object],
    extraction: EntityExtraction,
) -> dict[str, object]:
    return {
        "article_id": str(item["article_id"]),
        "content": {
            "title": str(item["title"]),
            "description": str(item["description"]),
        },
        "details": {
            "source_id": str(item["source_id"]),
            "source_name": str(item["source_name"]),
            "scope": str(item.get("scope", "")),
            "category": str(item.get("category", "")),
            "published_at": str(item["published_at"]),
            "url": str(item["url"]),
            "tags": item.get("tags", []),
            "ingested_at": str(item.get("ingested_at", "")),
        },
        "entity_extraction": extraction.as_dict(),
    }


def article_text(item: dict[str, object]) -> str:
    return f"Title: {item['title']}\nDescription: {item['description']}"


def representative_key(item: dict[str, object]) -> tuple[int, datetime]:
    return len(str(item["description"])), parse_datetime(str(item["published_at"]))


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_config(config: StoryNormalizationConfig) -> None:
    if not config.ingestion_run_id.strip():
        raise ValueError("ingestion_run_id is required")
    if config.entity_weight < 0 or config.lexical_weight < 0:
        raise ValueError("model weights must be non-negative")
    if config.entity_weight + config.lexical_weight <= 0:
        raise ValueError("at least one model weight must be positive")
    if not 0 <= config.merge_threshold <= 1:
        raise ValueError("merge_threshold must be between 0 and 1")
    if config.lexical_batch_size < 1 or config.lexical_max_length < 1:
        raise ValueError("lexical batch size and max length must be positive")
    if config.max_items_per_source is not None and config.max_items_per_source < 1:
        raise ValueError("max_items_per_source must be positive")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize RSS articles into story groups")
    parser.add_argument("--ingestion-run-id", required=True)
    parser.add_argument("--source", dest="source_ids", action="append")
    parser.add_argument("--limit", dest="max_items_per_source", type=int)
    parser.add_argument("--entity-model", default="gemma4:e4b-it-q4_K_M")
    parser.add_argument("--llm-endpoint", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--llm-timeout-seconds", type=int, default=120)
    parser.add_argument("--lexical-model", default="BAAI/bge-m3")
    parser.add_argument("--lexical-batch-size", type=int, default=16)
    parser.add_argument("--lexical-max-length", type=int, default=512)
    parser.add_argument("--use-fp16", action="store_true")
    parser.add_argument("--entity-weight", type=float, default=0.5)
    parser.add_argument("--lexical-weight", type=float, default=0.5)
    parser.add_argument("--merge-threshold", type=float, default=0.5)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_story_normalization(
            StoryNormalizationConfig(
                ingestion_run_id=args.ingestion_run_id,
                artifact_root=args.artifact_root,
                source_ids=tuple(args.source_ids) if args.source_ids else None,
                max_items_per_source=args.max_items_per_source,
                entity_model=args.entity_model,
                llm_endpoint=args.llm_endpoint,
                llm_timeout_seconds=args.llm_timeout_seconds,
                lexical_model=args.lexical_model,
                lexical_batch_size=args.lexical_batch_size,
                lexical_max_length=args.lexical_max_length,
                use_fp16=args.use_fp16,
                entity_weight=args.entity_weight,
                lexical_weight=args.lexical_weight,
                merge_threshold=args.merge_threshold,
            )
        )
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"story_normalization: failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ingestion_run_id": result.ingestion_run_id,
                "status": result.status,
                "item_count": result.item_count,
                "story_count": result.story_count,
                "output_dir": str(result.output_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.status in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
