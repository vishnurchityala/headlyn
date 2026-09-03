from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def parse_json_value(value: str, fallback: Any) -> Any:
    """Decode a JSON column while retaining a safe fallback for malformed data."""
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def iter_records(database_path: Path) -> Iterable[dict[str, Any]]:
    """Yield dataset metadata, articles, and pair annotations as JSONL records."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row

        # Read the annotation run that gives the exported records their provenance.
        run = connection.execute(
            """
            SELECT id, manifest_id, manifest_path, tool_version, schema_version, created_at
            FROM annotation_runs
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if run is not None:
            yield {
                "record_type": "dataset_metadata",
                "run_id": run["id"],
                "manifest_id": run["manifest_id"],
                "manifest_path": run["manifest_path"],
                "tool_version": run["tool_version"],
                "schema_version": run["schema_version"],
                "created_at": run["created_at"],
            }

        # Emit normalized article fields and retain raw source data for debugging.
        articles = connection.execute(
            """
            SELECT article_id, run_id, source_id, source_name, scope, category,
                   title, description, published_at, url, tags_json, ingested_at, raw_json
            FROM articles
            ORDER BY published_at, article_id
            """
        )
        for article in articles:
            yield {
                "record_type": "article",
                "document_id": article["article_id"],
                "run_id": article["run_id"],
                "source_id": article["source_id"],
                "source_name": article["source_name"],
                "scope": article["scope"],
                "category": article["category"],
                "title": article["title"],
                "description": article["description"],
                "published_at": article["published_at"],
                "url": article["url"],
                "tags": parse_json_value(article["tags_json"], []),
                "ingested_at": article["ingested_at"],
                "raw": parse_json_value(article["raw_json"], {}),
            }

        # Keep pair labels separate because the source database has no story IDs.
        annotations = connection.execute(
            """
            SELECT id, run_id, article_id_a, article_id_b, reference_article_id,
                   label, notes, annotator_id, created_at, updated_at
            FROM pair_annotations
            ORDER BY id
            """
        )
        for annotation in annotations:
            yield {
                "record_type": "pair_annotation",
                "annotation_id": annotation["id"],
                "run_id": annotation["run_id"],
                "article_id_a": annotation["article_id_a"],
                "article_id_b": annotation["article_id_b"],
                "reference_article_id": annotation["reference_article_id"],
                "label": annotation["label"],
                "notes": annotation["notes"],
                "annotator_id": annotation["annotator_id"],
                "created_at": annotation["created_at"],
                "updated_at": annotation["updated_at"],
            }


def convert(database_path: Path, output_path: Path) -> int:
    """Convert an annotation SQLite database into a UTF-8 JSONL file."""
    records = list(iter_records(database_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return len(records)


def parse_args() -> argparse.Namespace:
    """Parse source database and destination JSONL paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Source annotation SQLite database")
    parser.add_argument("output", type=Path, help="Destination JSONL file")
    return parser.parse_args()


def main() -> None:
    """Convert the requested annotation database and report the record count."""
    arguments = parse_args()
    count = convert(arguments.database, arguments.output)
    print(f"Wrote {count} records to {arguments.output}")


if __name__ == "__main__":
    main()
