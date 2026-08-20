# Phase 0 annotation tool

This is a local article-pair labeling tool for creating the first Headlyn
clustering evaluation set. It imports a pinned RSS ingestion run into SQLite,
serves a Flask JSON API, and provides a polished card-based annotation UI
through Jinja templates and vanilla JavaScript.

## Setup

From the repository root:

```bash
python3 -m venv .venv-annotation
.venv-annotation/bin/pip install -r requirements.txt
```

The local virtual environment is intentionally separate from the production
newsletter runtime. The UI is rendered by Flask and does not require a
frontend build step.

## Import the pinned run

```bash
.venv-annotation/bin/python -m annotation_tool.api.importer \
  --manifest-dir artifacts/stages/rss_ingestion/20260815T200549Z \
  --db data/phase0-20260815T200549Z.sqlite3
```

The import summary should report 170 articles.

## Run the tool

Start the Flask application:

```bash
.venv-annotation/bin/python -m annotation_tool.api.app \
  --db data/phase0-20260815T200549Z.sqlite3 \
  --port 5050
```

Open <http://127.0.0.1:5050/annotate>. The card-based interface is rendered
from Flask templates and enhanced with small vanilla JavaScript interactions.

## Export labels

```bash
.venv-annotation/bin/python -m annotation_tool.api.exporter \
  --db data/phase0-20260815T200549Z.sqlite3 \
  --out artifacts/evaluations/phase0/20260815T200549Z
```

The export writes `pair_annotations.jsonl`, `pair_annotations.csv`, and
`summary.json`.

## Tests

```bash
.venv-annotation/bin/python -m unittest discover -s annotation_tool/tests
```
