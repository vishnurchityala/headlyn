from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LABELS = ("same_story", "related", "opposite", "unrelated", "unclear")
SCHEMA_VERSION = "1"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS annotation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manifest_id TEXT NOT NULL UNIQUE,
    manifest_path TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    article_id TEXT PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES annotation_runs(id),
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    scope TEXT,
    category TEXT,
    title TEXT NOT NULL,
    description TEXT,
    published_at TEXT,
    url TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    ingested_at TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_run ON articles(run_id);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);

CREATE TABLE IF NOT EXISTS pair_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES annotation_runs(id),
    article_id_a TEXT NOT NULL REFERENCES articles(article_id),
    article_id_b TEXT NOT NULL REFERENCES articles(article_id),
    reference_article_id TEXT NOT NULL REFERENCES articles(article_id),
    label TEXT NOT NULL CHECK(label IN ('same_story', 'related', 'opposite', 'unrelated', 'unclear')),
    notes TEXT,
    annotator_id TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, article_id_a, article_id_b, annotator_id),
    CHECK(article_id_a < article_id_b),
    CHECK(article_id_a <> article_id_b)
);

CREATE INDEX IF NOT EXISTS idx_pairs_reference ON pair_annotations(run_id, reference_article_id);
CREATE INDEX IF NOT EXISTS idx_pairs_label ON pair_annotations(run_id, label);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def tags_from_row(row: sqlite3.Row | dict[str, Any]) -> list[str]:
    value = row["tags_json"]
    try:
        tags = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(tag) for tag in tags] if isinstance(tags, list) else []


def article_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("raw_json", None)
    payload.pop("tags_json", None)
    payload["tags"] = tags_from_row(row)
    return payload


def get_run(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM annotation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row_to_dict(row)


def get_run_id(connection: sqlite3.Connection) -> int | None:
    row = connection.execute(
        "SELECT id FROM annotation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None
