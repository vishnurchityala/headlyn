from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from annotation_tool import __version__
from annotation_tool.api.db import SCHEMA_VERSION, connect, initialize_database, utc_now


def import_manifest(
    manifest_dir: str | Path,
    db_path: str | Path,
    manifest_id: str | None = None,
) -> dict[str, Any]:
    root = Path(manifest_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Manifest directory does not exist: {root}")
    run_name = manifest_id or root.name
    item_files = sorted(
        path / "items.jsonl"
        for path in root.iterdir()
        if path.is_dir() and (path / "items.jsonl").is_file()
    )
    if not item_files:
        raise ValueError(f"No feed-level items.jsonl files found under {root}")

    rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()
    source_counts: dict[str, int] = {}
    for item_file in item_files:
        for line_number, line in enumerate(
            item_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                invalid_rows.append(
                    {"file": str(item_file), "line": line_number, "error": str(exc)}
                )
                continue
            article_id = str(item.get("article_id", "")).strip()
            title = str(item.get("title", "")).strip()
            if not article_id or not title:
                invalid_rows.append(
                    {
                        "file": str(item_file),
                        "line": line_number,
                        "error": "article_id and title are required",
                    }
                )
                continue
            if article_id in seen_ids:
                duplicate_ids.append(article_id)
                continue
            seen_ids.add(article_id)
            source_id = str(item.get("source_id", "")).strip() or item_file.parent.name
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
            rows.append(
                {
                    "article_id": article_id,
                    "source_id": source_id,
                    "source_name": str(item.get("source_name", source_id)).strip(),
                    "scope": item.get("scope"),
                    "category": item.get("category"),
                    "title": title,
                    "description": item.get("description"),
                    "published_at": item.get("published_at"),
                    "url": item.get("url"),
                    "tags_json": json.dumps(item.get("tags") or [], ensure_ascii=False),
                    "ingested_at": item.get("ingested_at"),
                    "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True),
                }
            )

    with connect(db_path) as connection:
        initialize_database(connection)
        existing = connection.execute(
            "SELECT id, manifest_path FROM annotation_runs WHERE manifest_id = ?",
            (run_name,),
        ).fetchone()
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO annotation_runs(
                  manifest_id, manifest_path, tool_version, schema_version, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_name, str(root), __version__, SCHEMA_VERSION, utc_now()),
            )
            run_id = cursor.lastrowid
        else:
            run_id = existing["id"]
            if existing["manifest_path"] != str(root):
                raise ValueError(
                    f"Manifest ID {run_name!r} already belongs to {existing['manifest_path']}"
                )

        inserted_count = 0
        for row in rows:
            current = connection.execute(
                "SELECT run_id, raw_json FROM articles WHERE article_id = ?",
                (row["article_id"],),
            ).fetchone()
            if current is not None:
                if current["run_id"] != run_id:
                    raise ValueError(
                        f"Article ID {row['article_id']} already belongs to another run"
                    )
                continue
            connection.execute(
                """
                INSERT INTO articles(
                  article_id, run_id, source_id, source_name, scope, category,
                  title, description, published_at, url, tags_json, ingested_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["article_id"],
                    run_id,
                    row["source_id"],
                    row["source_name"],
                    row["scope"],
                    row["category"],
                    row["title"],
                    row["description"],
                    row["published_at"],
                    row["url"],
                    row["tags_json"],
                    row["ingested_at"],
                    row["raw_json"],
                ),
            )
            inserted_count += 1
        connection.commit()

    return {
        "manifest_id": run_name,
        "manifest_path": str(root),
        "source_count": len(item_files),
        "source_counts": source_counts,
        "article_count": len(rows),
        "inserted_count": inserted_count,
        "duplicate_count": len(duplicate_ids),
        "duplicate_ids": duplicate_ids,
        "invalid_count": len(invalid_rows),
        "invalid_rows": invalid_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import RSS items into annotation SQLite")
    parser.add_argument("--manifest-dir", required=True)
    parser.add_argument("--db", default="data/phase0.sqlite3")
    parser.add_argument("--manifest-id")
    args = parser.parse_args()
    result = import_manifest(args.manifest_dir, args.db, args.manifest_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
