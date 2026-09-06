from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import StoryCandidate, StoryMetadata


SCHEMA_VERSION = 1


class SQLiteStoryStore:
    """SQLite source of truth for story metadata, members, lineage, and FTS5."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Open SQLite, enable safe pragmas, and create the metadata/FTS schema."""
        try:
            # Create the parent directory and open one reusable connection.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA foreign_keys=ON")

            # Create metadata, membership, idempotency, lineage, and outbox tables.
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stories (
                    story_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('active', 'closed')),
                    representative_document_id TEXT NOT NULL,
                    canonical_text TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    latest_published_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    document_count INTEGER NOT NULL,
                    source_count INTEGER NOT NULL,
                    category TEXT,
                    entity_names_json TEXT NOT NULL,
                    merged_story_ids_json TEXT NOT NULL,
                    centroid_json TEXT NOT NULL DEFAULT '[]',
                    dense_sum_json TEXT NOT NULL DEFAULT '[]',
                    sparse_weights_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS story_members (
                    story_id TEXT NOT NULL REFERENCES stories(story_id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL,
                    PRIMARY KEY(story_id, document_id)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL REFERENCES stories(story_id),
                    input_fingerprint TEXT,
                    document_json TEXT,
                    indexed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS story_aliases (
                    alias_story_id TEXT PRIMARY KEY,
                    survivor_story_id TEXT NOT NULL REFERENCES stories(story_id)
                );
                CREATE TABLE IF NOT EXISTS assignment_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS story_outbox (
                    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS stories_fts USING fts5(
                    story_id UNINDEXED,
                    canonical_text,
                    entity_names
                );
                INSERT OR IGNORE INTO index_metadata(key, value)
                    VALUES ('schema_version', '1');
                """
            )
            self._ensure_column("stories", "centroid_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column("stories", "dense_sum_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column("stories", "sparse_weights_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column("documents", "document_json", "TEXT")
            self.connection.commit()
        except (OSError, sqlite3.Error) as exc:
            self.close()
            raise RuntimeError(f"SQLite initialization failed: {exc}") from exc

    def health_check(self) -> None:
        """Verify the SQLite connection and FTS5 table are usable."""
        connection = self._connection()
        try:
            connection.execute("SELECT value FROM index_metadata WHERE key='schema_version'").fetchone()
            connection.execute("SELECT count(*) FROM stories_fts").fetchone()
        except sqlite3.Error as exc:
            raise RuntimeError(f"SQLite health check failed: {exc}") from exc

    def get_story(self, story_id: str) -> StoryMetadata | None:
        """Load complete story metadata and member IDs by story ID."""
        connection = self._connection()
        row = connection.execute("SELECT * FROM stories WHERE story_id = ?", (story_id,)).fetchone()
        if row is None:
            return None
        members = connection.execute(
            "SELECT document_id FROM story_members WHERE story_id = ? ORDER BY document_id",
            (story_id,),
        ).fetchall()
        return StoryMetadata(
            story_id=row["story_id"],
            status=row["status"],
            representative_document_id=row["representative_document_id"],
            member_document_ids=[member["document_id"] for member in members],
            canonical_text=row["canonical_text"],
            first_seen=parse_datetime(row["first_seen"]),
            latest_published_at=parse_datetime(row["latest_published_at"]),
            last_updated_at=parse_datetime(row["last_updated_at"]),
            document_count=row["document_count"],
            source_count=row["source_count"],
            entity_names=json.loads(row["entity_names_json"]),
            merged_story_ids=json.loads(row["merged_story_ids_json"]),
            category=row["category"],
            centroid=tuple(json.loads(row["centroid_json"] or "[]")),
            dense_sum=tuple(json.loads(row["dense_sum_json"] or "[]")),
            sparse_weights=json.loads(row["sparse_weights_json"] or "{}"),
            member_documents=[
                json.loads(member["document_json"])
                for member in connection.execute(
                    """
                    SELECT documents.document_json
                    FROM story_members
                    JOIN documents ON documents.document_id = story_members.document_id
                    WHERE story_members.story_id = ? AND documents.document_json IS NOT NULL
                    ORDER BY documents.document_id
                    """,
                    (story_id,),
                ).fetchall()
            ],
        )

    def upsert_story(self, story: StoryMetadata) -> None:
        """Upsert story metadata, members, and its FTS5 representative text."""
        connection = self._connection()
        try:
            # Update the relational story record and replace its membership atomically.
            with connection:
                connection.execute(
                    """
                    INSERT INTO stories(
                        story_id, status, representative_document_id, canonical_text,
                        first_seen, latest_published_at, last_updated_at,
                        document_count, source_count, category, entity_names_json,
                        merged_story_ids_json, centroid_json, dense_sum_json, sparse_weights_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(story_id) DO UPDATE SET
                        status=excluded.status,
                        representative_document_id=excluded.representative_document_id,
                        canonical_text=excluded.canonical_text,
                        first_seen=excluded.first_seen,
                        latest_published_at=excluded.latest_published_at,
                        last_updated_at=excluded.last_updated_at,
                        document_count=excluded.document_count,
                        source_count=excluded.source_count,
                        category=excluded.category,
                        entity_names_json=excluded.entity_names_json,
                        merged_story_ids_json=excluded.merged_story_ids_json,
                        centroid_json=excluded.centroid_json,
                        dense_sum_json=excluded.dense_sum_json,
                        sparse_weights_json=excluded.sparse_weights_json
                    """,
                    story_values(story),
                )
                connection.execute("DELETE FROM story_members WHERE story_id = ?", (story.story_id,))
                connection.executemany(
                    "INSERT INTO story_members(story_id, document_id) VALUES (?, ?)",
                    [(story.story_id, document_id) for document_id in story.member_document_ids],
                )
                for document in story.member_documents:
                    document_id = str(document.get("document_id", ""))
                    if document_id:
                        connection.execute(
                            """
                            INSERT INTO documents(document_id, story_id, input_fingerprint, document_json, indexed_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(document_id) DO UPDATE SET
                                story_id=excluded.story_id,
                                document_json=excluded.document_json
                            """,
                            (
                                document_id,
                                story.story_id,
                                document.get("input_fingerprint"),
                                json.dumps(document),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                connection.execute("DELETE FROM stories_fts WHERE story_id = ?", (story.story_id,))
                connection.execute(
                    "INSERT INTO stories_fts(story_id, canonical_text, entity_names) VALUES (?, ?, ?)",
                    (story.story_id, story.canonical_text, " ".join(story.entity_names)),
                )
        except sqlite3.Error as exc:
            raise RuntimeError(f"SQLite story upsert failed for {story.story_id}: {exc}") from exc

    def search_active_lexical(self, query_text: str, *, limit: int) -> list[StoryCandidate]:
        """Search active story representatives with FTS5 BM25 ranking."""
        tokens = [token for token in query_text.split() if token.strip()]
        if not tokens:
            return []
        # Quote terms and join with OR to avoid treating user punctuation as FTS syntax.
        match_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
        rows = self._connection().execute(
            """
            SELECT stories_fts.story_id, bm25(stories_fts) AS score
            FROM stories_fts
            JOIN stories ON stories.story_id = stories_fts.story_id
            WHERE stories.status = 'active' AND stories_fts MATCH ?
            ORDER BY score ASC
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
        return [
            StoryCandidate(row["story_id"], float(row["score"]), rank, "lexical")
            for rank, row in enumerate(rows, start=1)
        ]

    def mark_status(self, story_id: str, status: str) -> None:
        """Change a story status while retaining its FTS row for auditability."""
        if status not in {"active", "closed"}:
            raise ValueError("status must be active or closed")
        try:
            with self._connection():
                self._connection().execute(
                    "UPDATE stories SET status = ? WHERE story_id = ?", (status, story_id)
                )
        except sqlite3.Error as exc:
            raise RuntimeError(f"SQLite status update failed for {story_id}: {exc}") from exc

    def is_document_indexed(self, document_id: str) -> bool:
        """Return whether a document has already been assigned to a story."""
        row = self._connection().execute(
            "SELECT 1 FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        return row is not None

    def get_active_stories(self) -> list[StoryMetadata]:
        """Return complete metadata for every active story."""
        rows = self._connection().execute(
            "SELECT story_id FROM stories WHERE status = 'active' ORDER BY story_id"
        ).fetchall()
        return [story for row in rows if (story := self.get_story(row["story_id"])) is not None]

    def record_document(
        self,
        document_id: str,
        story_id: str,
        *,
        input_fingerprint: str | None = None,
        document_payload: dict[str, object] | None = None,
    ) -> None:
        """Record document idempotency state for a successful assignment."""
        try:
            with self._connection():
                self._connection().execute(
                    """
                    INSERT INTO documents(document_id, story_id, input_fingerprint, document_json, indexed_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(document_id) DO NOTHING
                    """,
                    (
                        document_id,
                        story_id,
                        input_fingerprint,
                        json.dumps(document_payload) if document_payload is not None else None,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.Error as exc:
            raise RuntimeError(f"SQLite document record failed for {document_id}: {exc}") from exc

    def close(self) -> None:
        """Close the SQLite connection when the index owner is shutting down."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _connection(self) -> sqlite3.Connection:
        """Return the initialized connection or raise a clear lifecycle error."""
        if self.connection is None:
            raise RuntimeError("SQLite store is not initialized")
        return self.connection

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """Add a column to an older local database without destructive migration."""
        columns = {
            row["name"]
            for row in self._connection().execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._connection().execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def story_values(story: StoryMetadata) -> tuple[object, ...]:
    """Convert a story model into the SQLite row parameter order."""
    return (
        story.story_id,
        story.status,
        story.representative_document_id,
        story.canonical_text,
        story.first_seen.isoformat(),
        story.latest_published_at.isoformat(),
        story.last_updated_at.isoformat(),
        story.document_count,
        story.source_count,
        story.category,
        json.dumps(story.entity_names),
        json.dumps(story.merged_story_ids),
        json.dumps(list(story.centroid)),
        json.dumps(list(story.dense_sum)),
        json.dumps(story.sparse_weights),
    )


def parse_datetime(value: str) -> datetime:
    """Parse a stored timestamp and normalize it to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
