from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from annotation_tool.api.db import LABELS, article_payload, connect, get_run, initialize_database, utc_now


def export_annotations(db_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        initialize_database(connection)
        run = get_run(connection)
        if run is None:
            raise ValueError("No annotation run has been imported")
        run_id = int(run["id"])
        rows = connection.execute(
            """
            SELECT p.article_id_a, p.article_id_b,
                   p.reference_article_id, p.label
            FROM pair_annotations p
            WHERE p.run_id = ?
            ORDER BY p.article_id_a, p.article_id_b
            """,
            (run_id,),
        ).fetchall()
        records = [dict(row) for row in rows]

        article_rows = connection.execute(
            """
            SELECT article_id, source_id, source_name, scope, category,
                   title, description, published_at, url, tags_json, ingested_at
            FROM articles
            WHERE run_id = ?
            ORDER BY article_id
            """,
            (run_id,),
        ).fetchall()
        articles = [article_payload(row) for row in article_rows]

        json_path = destination / "pair_annotations.json"
        json_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        csv_path = destination / "pair_annotations.csv"
        fieldnames = [
            "article_id_a",
            "article_id_b",
            "reference_article_id",
            "label",
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)

        articles_path = destination / "articles.json"
        articles_path.write_text(
            json.dumps(articles, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        article_count = connection.execute(
            "SELECT COUNT(*) AS count FROM articles WHERE run_id = ?", (run_id,)
        ).fetchone()["count"]
        label_counts = {label: 0 for label in LABELS}
        for row in connection.execute(
            "SELECT label, COUNT(*) AS count FROM pair_annotations WHERE run_id = ? GROUP BY label",
            (run_id,),
        ):
            label_counts[row["label"]] = row["count"]
        manifest = {
            "dataset_id": run["manifest_id"],
            "schema_version": run["schema_version"],
            "exported_at": utc_now(),
            "article_count": article_count,
            "pair_count": len(records),
            "label_counts": label_counts,
            "files": {
                "articles": articles_path.name,
                "annotations_json": json_path.name,
                "annotations_csv": csv_path.name,
            },
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export annotation labels")
    parser.add_argument("--db", default="data/phase0.sqlite3")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(json.dumps(export_annotations(args.db, args.out), indent=2))


if __name__ == "__main__":
    main()
