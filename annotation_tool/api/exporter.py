from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from annotation_tool.api.db import LABELS, connect, get_run, initialize_database, utc_now


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
            SELECT p.run_id, p.article_id_a, p.article_id_b,
                   p.reference_article_id, p.label, p.notes, p.annotator_id,
                   p.created_at, p.updated_at
            FROM pair_annotations p
            WHERE p.run_id = ?
            ORDER BY p.article_id_a, p.article_id_b, p.annotator_id
            """,
            (run_id,),
        ).fetchall()
        records = [dict(row) | {"manifest_id": run["manifest_id"]} for row in rows]

        jsonl_path = destination / "pair_annotations.jsonl"
        jsonl_path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
        csv_path = destination / "pair_annotations.csv"
        fieldnames = [
            "manifest_id",
            "run_id",
            "article_id_a",
            "article_id_b",
            "reference_article_id",
            "label",
            "notes",
            "annotator_id",
            "created_at",
            "updated_at",
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        article_count = connection.execute(
            "SELECT COUNT(*) AS count FROM articles WHERE run_id = ?", (run_id,)
        ).fetchone()["count"]
        label_counts = {label: 0 for label in LABELS}
        for row in connection.execute(
            "SELECT label, COUNT(*) AS count FROM pair_annotations WHERE run_id = ? GROUP BY label",
            (run_id,),
        ):
            label_counts[row["label"]] = row["count"]
        summary = {
            "manifest_id": run["manifest_id"],
            "manifest_path": run["manifest_path"],
            "tool_version": run["tool_version"],
            "schema_version": run["schema_version"],
            "exported_at": utc_now(),
            "article_count": article_count,
            "pair_count": len(records),
            "label_counts": label_counts,
            "files": [jsonl_path.name, csv_path.name],
        }
        (destination / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export annotation labels")
    parser.add_argument("--db", default="data/phase0.sqlite3")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(json.dumps(export_annotations(args.db, args.out), indent=2))


if __name__ == "__main__":
    main()
