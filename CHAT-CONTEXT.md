# Headlyn — Current Chat Context

## Project pivot

Headlyn has pivoted from a complex news canonicalization system to a daily
newsletter. The active goal is to aggregate multiple RSS/feed sources,
normalize related reports into story clusters, rewrite the selected stories
with a local LLM, and send one concise briefing to users by email. The initial
sourcing scope is India for general news, while Technology & Science and Sports
can include worldwide developments.

The earlier work explored article embeddings, chunking, hybrid retrieval,
pairwise scoring, graph construction, and story clustering. That work is now
legacy research. It should not be extended as part of the newsletter product
unless the product direction is explicitly changed again.

## Product promise

Deliver a useful shared morning briefing that answers: “What are the important
headlines I should know today?” General news begins with India-only coverage;
Technology & Science and Sports can cover important worldwide developments.
The edition should be quick to scan, balanced across publishers, and honest
about its relationship to the source reporting.

## Reader experience

- One shared edition for all subscribers in v1.
- India-only coverage for National, Politics, Business & Economy, and Other.
- Worldwide coverage is allowed for Technology & Science and Sports.
- Morning delivery, with India Standard Time as the working default.
- Approximately 8–10 items for a five-minute read.
- Items organized into topic sections.
- Each item shows a headline, short source description, publisher, publication
  time, and link to the original article.
- Empty topic sections are omitted.

Suggested sections:

1. National
2. Politics
3. Business & Economy
4. Technology & Science
5. World
6. Sports
7. Other

These are presentation sections, not story clusters. Story normalization may
combine reports about the same event into one source-linked story, while
unrelated reports remain separate newsletter stories.

## End-to-end product flow

```text
RSS/feed sources
  → collect the current day's items
  → validate required metadata
  → lightly clean descriptions and titles
  → remove exact duplicate URLs/titles
  → normalize same-event articles into source-linked stories
  → rewrite and classify stories with Gemma
  → choose a balanced daily set
  → assign topic sections
  → render the shared edition
  → deliver by email
```

The first implementation stage is a concurrent RSS ingestion pipeline. It is
live by default and can replay checked-in RSS snapshots. It produces normalized
RSS item records and run diagnostics under `artifacts/stages/`. It never fetches
article pages.

### Source aggregation

The active source pool contains Firstpost, The Indian Express, NDTV, and
Hindustan Times India News. RSS is the primary input. Every source retains its
publisher identity and direct article link for the final edition.

The source registry stores each source's website, RSS URL, scope, and category.
These four feeds are currently configured as `india-general`; worldwide
Technology & Science or Sports feeds can be added later without changing the
normalized item contract.

### Freshness and validation

An item should be considered valid only when it has a usable headline,
description, source, publication timestamp, and original URL. The daily run
should select items from the intended morning edition window and retain enough
metadata to diagnose feed failures or stale content.

The ingestion pipeline writes a feed snapshot, normalized RSS JSONL, and
source summary under `artifacts/stages/rss_ingestion/<run_id>/<source_id>/`,
plus a run summary under `artifacts/stages/rss_ingestion/<run_id>/summary.json`.

### Cleanup and duplicate handling

Cleanup is intentionally light: strip feed HTML, normalize whitespace, and
truncate descriptions only as needed for email readability. Remove duplicate
URLs and repeated normalized titles. Same-day articles may then be normalized
into one source-linked story by the story-normalization stage, which uses the
local Gemma 4 model for entity extraction and BGE-M3 sparse lexical matching. It does not
fetch article pages or create new prose.

Each concurrent source task writes only its own source directory, avoiding
shared-file collisions. A failed source is recorded in its own summary while
healthy sources continue; the overall run is marked `partial` when appropriate.

### Selection and balance

Selection should prioritize useful, current items within each section's
geographic scope while avoiding publisher concentration. When enough content
exists, aim for at least four publishers and cap a publisher at roughly three
selected items. Topic balance should guide the edition, but weak or repetitive
items should not be included merely to fill a section.

### Newsletter rewriting, rendering, and delivery

The newsletter stage consumes `newsletter_stories.json` and asks the local
Gemma model for a grounded headline, 30–70 word summary, and one controlled
topic section. The prompt receives every article title, description, and
publisher in the story cluster. Failed rewrites fall back to the
representative RSS title and description.

The email has a clear date/header, short introduction, topic sections, source
attribution, representative original links, and a footer. It is rendered as
both HTML and plain text. Preview is the default; Mailjet delivery is explicit and
uses environment-based Mailjet settings for an internal/test recipient
list. Sending is idempotent by edition date and supports an explicit forced
resend.

Newsletter artifacts are written under
`artifacts/stages/daily_newsletter/<edition_date>/` and include rewrites,
selection diagnostics, JSON edition data, HTML/text bodies, delivery state, and
a summary. Recipient addresses are not persisted in artifacts.

## Reliability and failure behavior

- A failed feed should not necessarily fail the whole run.
- Healthy feeds may produce the edition when one or more sources are down.
- Fewer than five valid items should result in a failed or held edition rather
  than a misleadingly empty email.
- The run should retain enough logs/output to explain source failures, item
  counts, duplicate removal, selection, and delivery status.
- A shared edition should be deterministic after selection so all subscribers
  receive the same content.

## Success criteria

The first newsletter workflow is successful when it can consistently produce a
morning edition with:

- 8–10 valid items when source inventory permits;
- at least four publishers when possible;
- no exact duplicate URLs or normalized titles;
- a headline, readable description, source, timestamp, and link for every item;
- clear, non-empty topic sections;
- a safe failure state when content is insufficient; and
- the same edition for every subscriber.

## Explicitly out of scope

Do not treat the following as requirements for the current product:

- dense embeddings and semantic similarity scoring;
- article chunking and chunk-level aggregation;
- semantic retrieval and graph clustering;
- cross-day story timelines;
- personalized feeds or personalized newsletter editions;
- production subscriber management, campaign automation, and website
  delivery.

## Repository context

- [`README.md`](./README.md) contains the current product contract.
- [`NOTES.md`](./NOTES.md) records product decisions and open questions.
- [`assets/rss-feeds/raw/`](./assets/rss-feeds/raw/) contains RSS snapshots.
- [`headlyn/ingestion/`](./headlyn/ingestion/) contains the registry and pipeline.
- [`tests/`](./tests/) contains deterministic ingestion contract tests.
- [`artifacts/stages/`](./artifacts/stages/) contains ignored stage outputs.
- Existing clustering artifacts are historical and not active runtime
  requirements.
