# Phase 0 Annotation Tool Plan

## Purpose

Create the evaluation dataset needed to measure story clustering quality
before changing the clustering pipeline.

The first input will be the pinned ingestion run:

```text
artifacts/stages/rss_ingestion/20260815T200549Z
```

That run contains 170 normalized RSS articles across four source directories.
The annotation tool must preserve the manifest's stable `article_id` values so
the resulting labels can be joined directly with story-normalization
artifacts.

## Tool decision

Build a standalone local Flask application with SQLite, Jinja HTML templates,
and a small amount of vanilla JavaScript. Flask owns importing, persistence,
validation, progress, export, and page rendering. The templates and CSS own
the interactive three-panel annotation workflow and card-based visual design.

Recommended project boundary:

```text
annotation_tool/
  api/
    app.py
    db.py
    importer.py
    exporter.py
    tests/
  templates/
  static/
  tests/
requirements.txt
```

### Why Flask templates + SQLite

- The workflow is local and single-user initially, but the UI still needs fast
  filtering, selection state, and responsive cards.
- Flask is small and explicit as both the page renderer and local JSON API.
- SQLite provides transactions, uniqueness constraints, and easy export
  without operating a separate database service.
- Jinja templates keep the first version easy to run, inspect, and debug.
- Vanilla JavaScript is enough for selection state and selected-pair controls;
  plain CSS provides the visual system without a frontend build step.
- Keeping the complete tool in `annotation_tool/` isolates annotation
  dependencies from the production newsletter pipeline.

### Options not selected for the first version

- Streamlit is convenient for data exploration but less suitable for a
  resumable multi-panel labeling workflow and a deliberately styled card UI.
- A separate frontend SPA would add a build and dependency layer that the
  first local annotation pass does not need.
- Django is unnecessarily large for this local tool.
- A hosted annotation service would add account, data-storage, and export
  coordination before the labeling schema is settled.

## Scope of the first version

### Included

- Import all `*/items.jsonl` files from a selected ingestion run.
- Store an immutable local snapshot of article metadata.
- Expose article, progress, annotation, and export operations through Flask
  routes, with JSON endpoints retained for future tooling.
- Select one reference article at a time.
- Display every other article as a candidate.
- Search and filter candidates by source, category, scope, and publication
  time.
- Select multiple candidates for the current reference.
- Assign a relationship label and optional note to each selected pair.
- Save all selected pairs in one transaction.
- Resume from the next unlabeled reference or revisit existing labels.
- Prevent self-pairs and duplicate canonical pairs.
- Export versioned JSONL and CSV evaluation files.
- Show progress and counts by label.

### Explicitly not included yet

- Automatic clustering or LLM-assisted labeling.
- Article-page fetching or full-text extraction.
- User accounts, remote hosting, or production authentication.
- Final cluster-level adjudication UI.
- Personalized ranking or newsletter generation.

## Annotation labels

Use a small controlled vocabulary in the UI and database:

| Stored label | Meaning |
| --- | --- |
| `same_story` | Both articles report the same real-world event or development. |
| `related` | The articles are meaningfully connected but are not the same story/event. |
| `opposite` | The articles make contradictory, opposing, or directly disputing claims. |
| `unrelated` | There is no meaningful relationship. |
| `unclear` | The available title/description is insufficient for a reliable judgment. |

The UI may display friendlier text such as “Same story” and “Opposite /
contradicting.” “Other” should initially be an optional note, not an unlimited
free-form label. A new stored label should be added only after repeated notes
show a missing relationship type.

## Data model

Use a local SQLite database, defaulting to an ignored `data/` directory.
Allow the database path to be overridden for tests and separate annotation
runs.

### `annotation_runs`

Records the imported input snapshot and schema/tool versions.

```text
id                 INTEGER PRIMARY KEY
manifest_id        TEXT NOT NULL
manifest_path      TEXT NOT NULL
tool_version       TEXT NOT NULL
schema_version     TEXT NOT NULL
created_at         TEXT NOT NULL
```

### `articles`

Stores the article snapshot required to render and export annotations.

```text
article_id         TEXT PRIMARY KEY
run_id             INTEGER NOT NULL
source_id          TEXT NOT NULL
source_name        TEXT NOT NULL
scope              TEXT
category           TEXT
title              TEXT NOT NULL
description        TEXT
published_at       TEXT
url                TEXT
tags_json          TEXT
ingested_at        TEXT
raw_json           TEXT NOT NULL
```

### `pair_annotations`

Stores one annotator's judgment for a canonical unordered pair.

```text
id                    INTEGER PRIMARY KEY
run_id                INTEGER NOT NULL
article_id_a          TEXT NOT NULL
article_id_b          TEXT NOT NULL
reference_article_id  TEXT NOT NULL
label                 TEXT NOT NULL
notes                 TEXT
annotator_id          TEXT NOT NULL DEFAULT 'local'
created_at            TEXT NOT NULL
updated_at            TEXT NOT NULL
UNIQUE(run_id, article_id_a, article_id_b, annotator_id)
```

`article_id_a` and `article_id_b` must be stored in deterministic sorted order.
`reference_article_id` preserves the UI's display direction but must not be
part of the uniqueness key. This prevents saving the same relationship twice
when the two articles are later viewed in reverse order.

For the initial single-user tool, the default annotator is `local`. The schema
should still retain `annotator_id` so multiple raw judgments can be supported
later without overwriting the first annotation.

## Import design

Provide a repeatable command that takes an ingestion-run directory and a
database path:

```text
python -m annotation_tool.importer \
  --manifest-dir artifacts/stages/rss_ingestion/20260815T200549Z \
  --db data/phase0-20260815T200549Z.sqlite3
```

Importer requirements:

- Read only feed-level `items.jsonl` files, not `feed.xml` or summary files.
- Derive `manifest_id` from the run directory name or explicit argument.
- Preserve the original article JSON in `raw_json`.
- Insert or safely re-run the same import without duplicating articles.
- Reject rows missing `article_id` or `title` with a useful error.
- Report source counts, article count, skipped rows, and duplicate IDs.
- Never silently replace an article from a different manifest/run.

The first import should result in 170 article records for the supplied run.

## Annotation workflow and UI

The templates should use a simple editorial/newsroom theme with reusable card
classes and CSS custom properties. It should feel like a focused workbench,
not an admin table.

### Visual direction

- Warm off-white page background with dark ink text.
- White cards with thin neutral borders, modest radius, and restrained
  shadows.
- One blue accent for actions and links.
- Compact uppercase metadata labels and readable article headlines.
- Distinct label colors: blue for `same_story`, amber for `related`, red for
  `opposite`, gray for `unrelated`, and purple for `unclear`.
- Use CSS variables for colors, spacing, borders, and radii so a dark theme can
  be added without rewriting templates.

### Main layout

The main page should have three clearly separated areas:

1. **Reference card** — title, description, source, timestamp, tags, and link
   to the original URL. Keep it visually prominent and sticky on larger
   screens.
2. **Candidate card collection** — every article except the reference, with
   search, source/category/scope/time filters, selection controls, and a visible
   existing-label state. Cards should show title, source, publication time,
   short description, and tags.
3. **Selected-pairs rail** — selected candidates grouped under the reference,
   with label control, optional note, remove action, and one Save button. On
   narrow screens this becomes a bottom drawer or stacked section.

Add a compact header containing the run name, annotation progress, label
counts, and next/previous reference controls. Use loading, empty, saved, and
error states as designed UI states rather than browser alerts.

The template should use a normal HTML form for saving, with vanilla JavaScript
building the selected-pairs rail and validating that every selected candidate
has a label. The backend remains the source of truth after every save.

Recommended navigation:

- Next unlabeled reference.
- Previous reference.
- Jump to article/reference by search.
- Show only references with incomplete work.
- Show annotation progress and label totals.

The candidate list can begin with pagination or a compact list because the
current run has 170 articles. The data model should not assume that size;
future runs may require server-side filtering and pagination.

Save behavior:

1. Validate that the reference and all candidates exist in the active run.
2. Reject self-pairs and invalid labels.
3. Canonicalize article ID order.
4. Upsert all selected annotations in one transaction.
5. Return a success message and update progress without losing unsaved
   selections on validation failure.

## Sampling strategy

The UI should support a complete pass and focused passes:

- Complete pass for broad coverage.
- Same-source and cross-source filters.
- Publication-time window.
- Shared-tag or category filters.
- Existing pipeline candidate pairs when available.
- Random negative sampling so the dataset is not made only of likely matches.

The first evaluation set should intentionally include near-duplicate titles,
follow-up reports, opinion-style items, sparse descriptions, different events
sharing an entity, and obvious unrelated articles. These hard cases will be
more useful for clustering evaluation than only labeling obvious matches.

## Export design

Provide a repeatable export command:

```text
python -m annotation_tool.exporter \
  --db data/phase0-20260815T200549Z.sqlite3 \
  --out artifacts/evaluations/phase0/20260815T200549Z
```

Export at least:

- `pair_annotations.jsonl`
- `pair_annotations.csv`
- `summary.json` with article count, pair count, label counts, manifest ID,
  tool/schema versions, and export timestamp.

Example JSONL row:

```json
{
  "run_id": "20260815T200549Z",
  "article_id_a": "article-...",
  "article_id_b": "article-...",
  "label": "same_story",
  "notes": "Both describe the same announcement.",
  "annotator_id": "local"
}
```

For initial clustering precision/recall, treat `same_story` as the positive
class, report `related` separately, and exclude `unclear` from strict metrics.
Retain `opposite` and `unrelated` for future contradiction, diversity, and
recommendation evaluations. Cluster-level labels can initially be derived
from the `same_story` pair graph; a dedicated cluster-review pass can follow.

## Implementation milestones

### Milestone 1 — Project skeleton and import

- Create the isolated Flask application, Jinja templates, and static assets.
- Add the annotation requirements file without a frontend build dependency.
- Add configuration for manifest path, database path, host, and port.
- Implement schema initialization and manifest import.
- Verify the supplied run imports 170 articles.

### Milestone 2 — Pair persistence

- Implement pair validation and canonicalization.
- Add transactional upsert behavior.
- Add progress and label-count queries.
- Add tests for self-pairs, duplicate reverse-order pairs, invalid labels, and
  re-import behavior.

### Milestone 3 — Flask routes and HTML annotation interface

- Implement API endpoints for runs, references, candidates, progress, and
  annotation upserts.
- Implement the HTML three-panel reference/candidate/selection workflow.
- Add reusable article, label, filter, progress, and selected-pair cards.
- Add search and basic filters.
- Add existing-label display and resumable navigation.
- Preserve selection state when form validation fails.
- Add responsive layout and light/dark theme variables.

### Milestone 4 — Export and evaluation handoff

- Implement JSONL/CSV export and summary artifact.
- Add a smoke test using the pinned ingestion run.
- Document the exact commands for import, run, annotate, and export.
- Update the Phase 0 roadmap with the completed tool link and baseline
  dataset location.

## Acceptance criteria

- A fresh database can be created from the pinned manifest with one command.
- The pinned manifest imports 170 articles and displays their metadata.
- An annotator can select one reference and multiple candidates, label them,
  save them, and continue later.
- Reverse-order views do not create duplicate pair records.
- The database contains stable article IDs and auditable run/version metadata.
- Exported labels can be joined to pipeline artifacts using article IDs.
- The app runs locally without a separate database service or production
  credentials or frontend build step.
- No production ingestion, clustering, or newsletter code is changed by the
  annotation tool's first implementation.

## Decisions to confirm before implementation

1. Whether the first pass should be exhaustive over all article pairs or use a
   mixed candidate-focused and random-negative sample. Recommended: mixed
   sampling first, followed by targeted hard-case expansion.
2. Whether only one annotator is needed initially. Recommended: keep the raw
   `annotator_id` field even if the first UI defaults to `local`.
3. Whether labels should be assigned per selected candidate in the UI or one
   label applied to a batch. Recommended: allow batch selection, but require
   each selected pair to have an explicit saved label.
