from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from annotation_tool import __version__
from annotation_tool.api.db import (
    LABELS,
    SCHEMA_VERSION,
    article_payload,
    connect,
    get_run,
    get_run_id,
    initialize_database,
    utc_now,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def create_app(db_path: str | Path = "data/phase0.sqlite3") -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config["ANNOTATION_DB"] = str(db_path)
    app.config["SECRET_KEY"] = "headlyn-phase0-local"

    @app.template_filter("pretty_date")
    def pretty_date(value: str | None) -> str:
        if not value:
            return "Date unavailable"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.strftime("%d %b %Y · %H:%M")

    @app.get("/assets/<path:filename>")
    def asset(filename: str):
        return send_from_directory(REPO_ROOT / "assets" / "images", filename)

    with connect(app.config["ANNOTATION_DB"]) as connection:
        initialize_database(connection)

    def db_connection() -> sqlite3.Connection:
        connection = connect(app.config["ANNOTATION_DB"])
        initialize_database(connection)
        return connection

    @app.get("/")
    def home():
        return redirect(url_for("annotate"))

    @app.get("/annotate")
    def annotate():
        filters = {
            "search": request.args.get("search", "").strip(),
            "source": request.args.get("source", "").strip(),
            "category": request.args.get("category", "").strip(),
            "scope": request.args.get("scope", "").strip(),
        }
        reference_search = request.args.get("reference_search", "").strip()
        status = request.args.get("status", "unlabeled").strip() or "unlabeled"
        requested_reference = request.args.get("reference_id", "").strip()
        with db_connection() as connection:
            run = get_run(connection)
            if run is None:
                return render_template("annotate.html", run=None, labels=LABELS)
            run_id = int(run["id"])
            reference_rows = query_references(connection, run_id, reference_search, status)
            reference_ids = [row["article_id"] for row in reference_rows]
            reference_id = requested_reference if requested_reference in reference_ids else (
                reference_ids[0] if reference_ids else ""
            )
            reference = None
            candidate_rows = []
            previous_id = next_id = None
            if reference_id:
                reference = connection.execute(
                    "SELECT * FROM articles WHERE article_id = ? AND run_id = ?",
                    (reference_id, run_id),
                ).fetchone()
                candidate_rows = query_candidates(connection, run_id, reference_id, filters)
                position = reference_ids.index(reference_id)
                previous_id = reference_ids[position - 1] if position > 0 else None
                next_id = reference_ids[position + 1] if position + 1 < len(reference_ids) else None
            sources = connection.execute(
                "SELECT DISTINCT source_id, source_name FROM articles WHERE run_id = ? ORDER BY source_name",
                (run_id,),
            ).fetchall()
            categories = connection.execute(
                "SELECT DISTINCT category FROM articles WHERE run_id = ? AND category IS NOT NULL AND category <> '' ORDER BY category",
                (run_id,),
            ).fetchall()
            scopes = connection.execute(
                "SELECT DISTINCT scope FROM articles WHERE run_id = ? AND scope IS NOT NULL AND scope <> '' ORDER BY scope",
                (run_id,),
            ).fetchall()
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM articles WHERE run_id = ?", (run_id,)
            ).fetchone()["count"]
            labeled_references = connection.execute(
                "SELECT COUNT(DISTINCT reference_article_id) AS count FROM pair_annotations WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"]
            progress = {
                "total_references": total,
                "labeled_references": labeled_references,
                "remaining_references": max(total - labeled_references, 0),
                "labels": label_counts(connection, run_id),
            }
            return render_template(
                "annotate.html",
                run=run,
                article_count=total,
                progress=progress,
                references=[article_payload(row) | {"annotation_count": row["annotation_count"]} for row in reference_rows],
                reference=article_payload(reference) if reference else None,
                candidates=[candidate_payload(row) for row in candidate_rows],
                filters=filters,
                reference_search=reference_search,
                status=status,
                labels=LABELS,
                previous_id=previous_id,
                next_id=next_id,
                sources=[dict(row) for row in sources],
                categories=[row["category"] for row in categories],
                scopes=[row["scope"] for row in scopes],
            )

    @app.post("/annotate/save")
    def save_form_annotations():
        reference_id = request.form.get("reference_article_id", "").strip()
        candidate_ids = request.form.getlist("candidate_ids")
        annotations_body = [
            {
                "candidate_article_id": candidate_id,
                "label": request.form.get(f"label_{candidate_id}", "").strip(),
                "notes": request.form.get(f"notes_{candidate_id}", "").strip(),
            }
            for candidate_id in candidate_ids
        ]
        with db_connection() as connection:
            run_id = get_run_id(connection)
            if run_id is None:
                flash("Import an ingestion manifest before annotating.", "error")
            else:
                try:
                    saved = save_pair_records(connection, run_id, reference_id, annotations_body)
                    connection.commit()
                    flash(f"Saved {len(saved)} pair{'s' if len(saved) != 1 else ''}.", "success")
                except ValueError as exc:
                    connection.rollback()
                    flash(str(exc), "error")
        return redirect(url_for("annotate", reference_id=reference_id, status="unlabeled"))

    @app.after_request
    def add_local_cors(response):
        response.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "*"
        )
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "tool_version": __version__})

    @app.get("/api/run")
    def run_info():
        with db_connection() as connection:
            run = get_run(connection)
            if run is None:
                return jsonify({"error": "No annotation run has been imported."}), 404
            run_id = int(run["id"])
            article_count = connection.execute(
                "SELECT COUNT(*) AS count FROM articles WHERE run_id = ?", (run_id,)
            ).fetchone()["count"]
            pair_count = connection.execute(
                "SELECT COUNT(*) AS count FROM pair_annotations WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"]
            return jsonify(
                {
                    "run": run,
                    "article_count": article_count,
                    "pair_count": pair_count,
                    "labels": label_counts(connection, run_id),
                }
            )

    @app.get("/api/progress")
    def progress():
        with db_connection() as connection:
            run_id = get_run_id(connection)
            if run_id is None:
                return jsonify({"error": "No annotation run has been imported."}), 404
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM articles WHERE run_id = ?", (run_id,)
            ).fetchone()["count"]
            labeled = connection.execute(
                """
                SELECT COUNT(DISTINCT reference_article_id) AS count
                FROM pair_annotations WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()["count"]
            return jsonify(
                {
                    "total_references": total,
                    "labeled_references": labeled,
                    "remaining_references": max(total - labeled, 0),
                    "labels": label_counts(connection, run_id),
                }
            )

    @app.get("/api/references")
    def references():
        search = request.args.get("search", "").strip()
        status = request.args.get("status", "all")
        with db_connection() as connection:
            run_id = get_run_id(connection)
            if run_id is None:
                return jsonify({"error": "No annotation run has been imported."}), 404
            clauses = ["a.run_id = ?"]
            params: list[Any] = [run_id]
            if search:
                clauses.append("(a.title LIKE ? OR a.source_name LIKE ?)")
                pattern = f"%{search}%"
                params.extend([pattern, pattern])
            if status == "unlabeled":
                clauses.append(
                    "NOT EXISTS (SELECT 1 FROM pair_annotations p "
                    "WHERE p.run_id = a.run_id AND p.reference_article_id = a.article_id)"
                )
            elif status == "labeled":
                clauses.append(
                    "EXISTS (SELECT 1 FROM pair_annotations p "
                    "WHERE p.run_id = a.run_id AND p.reference_article_id = a.article_id)"
                )
            rows = connection.execute(
                f"""
                SELECT a.*, COUNT(p.id) AS annotation_count
                FROM articles a
                LEFT JOIN pair_annotations p
                  ON p.run_id = a.run_id AND p.reference_article_id = a.article_id
                WHERE {' AND '.join(clauses)}
                GROUP BY a.article_id
                ORDER BY COALESCE(a.published_at, '') DESC, a.article_id
                """,
                params,
            ).fetchall()
            items = []
            for row in rows:
                item = article_payload(row)
                item["annotation_count"] = row["annotation_count"]
                items.append(item)
            return jsonify({"items": items})

    @app.get("/api/articles/<article_id>")
    def article(article_id: str):
        with db_connection() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE article_id = ?", (article_id,)
            ).fetchone()
            if row is None:
                return jsonify({"error": "Article not found."}), 404
            return jsonify(article_payload(row))

    @app.get("/api/articles/<reference_id>/candidates")
    def candidates(reference_id: str):
        search = request.args.get("search", "").strip()
        source = request.args.get("source", "").strip()
        category = request.args.get("category", "").strip()
        scope = request.args.get("scope", "").strip()
        published_from = request.args.get("published_from", "").strip()
        published_to = request.args.get("published_to", "").strip()
        with db_connection() as connection:
            run_id = get_run_id(connection)
            if run_id is None:
                return jsonify({"error": "No annotation run has been imported."}), 404
            reference = connection.execute(
                "SELECT * FROM articles WHERE article_id = ? AND run_id = ?",
                (reference_id, run_id),
            ).fetchone()
            if reference is None:
                return jsonify({"error": "Reference article not found."}), 404
            clauses = ["a.run_id = ?", "a.article_id <> ?"]
            params: list[Any] = [run_id, reference_id]
            for field, value in (
                ("a.source_id", source),
                ("a.category", category),
                ("a.scope", scope),
            ):
                if value:
                    clauses.append(f"{field} = ?")
                    params.append(value)
            if published_from:
                clauses.append("a.published_at >= ?")
                params.append(published_from)
            if published_to:
                clauses.append("a.published_at <= ?")
                params.append(published_to)
            if search:
                clauses.append("(a.title LIKE ? OR a.description LIKE ?)")
                pattern = f"%{search}%"
                params.extend([pattern, pattern])
            rows = connection.execute(
                f"""
                SELECT a.*,
                       p.label AS existing_label,
                       p.notes AS existing_notes,
                       p.updated_at AS labeled_at
                FROM articles a
                LEFT JOIN pair_annotations p
                  ON p.run_id = a.run_id
                 AND p.article_id_a = CASE WHEN a.article_id < ? THEN a.article_id ELSE ? END
                 AND p.article_id_b = CASE WHEN a.article_id > ? THEN a.article_id ELSE ? END
                 AND p.annotator_id = 'local'
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(a.published_at, '') DESC, a.article_id
                """,
                [reference_id, reference_id, reference_id, reference_id, *params],
            ).fetchall()
            return jsonify(
                {
                    "reference": article_payload(reference),
                    "items": [article_payload(row) | {
                        "existing_label": row["existing_label"],
                        "existing_notes": row["existing_notes"],
                        "labeled_at": row["labeled_at"],
                    } for row in rows],
                }
            )

    @app.get("/api/annotations")
    def annotations():
        reference_id = request.args.get("reference_id", "").strip()
        with db_connection() as connection:
            run_id = get_run_id(connection)
            if run_id is None:
                return jsonify({"error": "No annotation run has been imported."}), 404
            clauses = ["p.run_id = ?"]
            params: list[Any] = [run_id]
            if reference_id:
                clauses.append("p.reference_article_id = ?")
                params.append(reference_id)
            rows = connection.execute(
                f"""
                SELECT p.*, a.title AS title_a, b.title AS title_b
                FROM pair_annotations p
                JOIN articles a ON a.article_id = p.article_id_a
                JOIN articles b ON b.article_id = p.article_id_b
                WHERE {' AND '.join(clauses)}
                ORDER BY p.updated_at DESC
                """,
                params,
            ).fetchall()
            return jsonify({"items": [dict(row) for row in rows]})

    @app.post("/api/annotations")
    def save_annotations():
        body = request.get_json(silent=True) or {}
        reference_id = str(body.get("reference_article_id", "")).strip()
        annotator_id = str(body.get("annotator_id", "local")).strip() or "local"
        annotations_body = body.get("annotations")
        if not reference_id or not isinstance(annotations_body, list):
            return jsonify({"error": "reference_article_id and annotations are required."}), 400
        with db_connection() as connection:
            run_id = get_run_id(connection)
            if run_id is None:
                return jsonify({"error": "No annotation run has been imported."}), 404
            article_ids = {
                row["article_id"]
                for row in connection.execute(
                    "SELECT article_id FROM articles WHERE run_id = ?", (run_id,)
                ).fetchall()
            }
            if reference_id not in article_ids:
                return jsonify({"error": "Reference article not found."}), 404
            try:
                saved = save_pair_records(
                    connection, run_id, reference_id, annotations_body, annotator_id
                )
                connection.commit()
            except (AttributeError, ValueError) as exc:
                connection.rollback()
                return jsonify({"error": str(exc)}), 400
            return jsonify({"saved": saved, "saved_count": len(saved)})

    return app


def query_references(
    connection: sqlite3.Connection,
    run_id: int,
    search: str = "",
    status: str = "all",
) -> list[sqlite3.Row]:
    clauses = ["a.run_id = ?"]
    params: list[Any] = [run_id]
    if search:
        clauses.append("(a.title LIKE ? OR a.source_name LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern])
    if status == "unlabeled":
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM pair_annotations p "
            "WHERE p.run_id = a.run_id AND p.reference_article_id = a.article_id)"
        )
    elif status == "labeled":
        clauses.append(
            "EXISTS (SELECT 1 FROM pair_annotations p "
            "WHERE p.run_id = a.run_id AND p.reference_article_id = a.article_id)"
        )
    return connection.execute(
        f"""
        SELECT a.*, COUNT(p.id) AS annotation_count
        FROM articles a
        LEFT JOIN pair_annotations p
          ON p.run_id = a.run_id AND p.reference_article_id = a.article_id
        WHERE {' AND '.join(clauses)}
        GROUP BY a.article_id
        ORDER BY COALESCE(a.published_at, '') DESC, a.article_id
        """,
        params,
    ).fetchall()


def query_candidates(
    connection: sqlite3.Connection,
    run_id: int,
    reference_id: str,
    filters: dict[str, str],
) -> list[sqlite3.Row]:
    clauses = ["a.run_id = ?", "a.article_id <> ?"]
    params: list[Any] = [run_id, reference_id]
    for field, value in (
        ("a.source_id", filters.get("source", "")),
        ("a.category", filters.get("category", "")),
        ("a.scope", filters.get("scope", "")),
    ):
        if value:
            clauses.append(f"{field} = ?")
            params.append(value)
    if filters.get("search"):
        clauses.append("(a.title LIKE ? OR a.description LIKE ?)")
        pattern = f"%{filters['search']}%"
        params.extend([pattern, pattern])
    return connection.execute(
        f"""
        SELECT a.*,
               p.label AS existing_label,
               p.notes AS existing_notes,
               p.updated_at AS labeled_at
        FROM articles a
        LEFT JOIN pair_annotations p
          ON p.run_id = a.run_id
         AND p.article_id_a = CASE WHEN a.article_id < ? THEN a.article_id ELSE ? END
         AND p.article_id_b = CASE WHEN a.article_id > ? THEN a.article_id ELSE ? END
         AND p.annotator_id = 'local'
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(a.published_at, '') DESC, a.article_id
        """,
        [reference_id, reference_id, reference_id, reference_id, *params],
    ).fetchall()


def candidate_payload(row: sqlite3.Row) -> dict[str, Any]:
    return article_payload(row) | {
        "existing_label": row["existing_label"],
        "existing_notes": row["existing_notes"],
        "labeled_at": row["labeled_at"],
    }


def save_pair_records(
    connection: sqlite3.Connection,
    run_id: int,
    reference_id: str,
    annotations_body: list[dict[str, Any]],
    annotator_id: str = "local",
) -> list[dict[str, str]]:
    article_ids = {
        row["article_id"]
        for row in connection.execute(
            "SELECT article_id FROM articles WHERE run_id = ?", (run_id,)
        ).fetchall()
    }
    if reference_id not in article_ids:
        raise ValueError("Reference article not found.")
    now = utc_now()
    saved = []
    for item in annotations_body:
        candidate_id = str(item.get("candidate_article_id", "")).strip()
        label = str(item.get("label", "")).strip()
        notes = item.get("notes")
        if candidate_id == reference_id:
            raise ValueError("Reference and candidate articles must differ.")
        if candidate_id not in article_ids:
            raise ValueError(f"Candidate article not found: {candidate_id}")
        if label not in LABELS:
            raise ValueError(f"Invalid label: {label}")
        article_a, article_b = sorted((reference_id, candidate_id))
        connection.execute(
            """
            INSERT INTO pair_annotations(
              run_id, article_id_a, article_id_b, reference_article_id,
              label, notes, annotator_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, article_id_a, article_id_b, annotator_id)
            DO UPDATE SET
              reference_article_id = excluded.reference_article_id,
              label = excluded.label,
              notes = excluded.notes,
              updated_at = excluded.updated_at
            """,
            (
                run_id,
                article_a,
                article_b,
                reference_id,
                label,
                str(notes).strip() if notes is not None else None,
                annotator_id,
                now,
                now,
            ),
        )
        saved.append({"candidate_article_id": candidate_id, "label": label})
    return saved


def label_counts(connection: sqlite3.Connection, run_id: int) -> dict[str, int]:
    counts = {label: 0 for label in LABELS}
    rows = connection.execute(
        "SELECT label, COUNT(*) AS count FROM pair_annotations WHERE run_id = ? GROUP BY label",
        (run_id,),
    ).fetchall()
    for row in rows:
        counts[row["label"]] = row["count"]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 0 annotation API")
    parser.add_argument("--db", default="data/phase0.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    create_app(args.db).run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
