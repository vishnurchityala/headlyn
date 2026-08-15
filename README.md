<p align="center">
  <img src="./assets/images/HEADLYN-BLUE-LOGO.png" alt="Headlyn Logo" width="280" />
</p>

# Headlyn

Headlyn is a daily news briefing. It aggregates RSS feeds from multiple
publishers, selects a small and balanced set of useful headlines, and delivers
one shared morning newsletter by email.

## Product direction

The first product is an editorially light newsletter, not a story
canonicalization platform. An RSS item is the unit shown to a reader. Each item
keeps its original publisher, headline, description, publication time, and link
so readers can open the source article.

The initial geographic scope is India for National, Politics, Business &
Economy, and other current-affairs coverage. Technology & Science and Sports
can include important developments from anywhere in the world. The intended
reading experience is a balanced five-minute briefing with about 8–10 items,
organized into topic sections such as National, Politics, Business & Economy,
Technology & Science, World, Sports, and Other. Empty sections are omitted.
All subscribers receive the same daily edition in v1.

## Daily flow

```text
RSS feeds
  → collect fresh items
  → clean and validate feed metadata
  → remove exact duplicate URLs and titles
  → normalize same-event articles into story points
  → select a balanced set across publishers and topics
  → organize items into topic sections
  → render the morning email
  → send the shared edition to subscribers
```

The first implementation stage is a concurrent RSS ingestion pipeline. It
supports live feeds and replay of checked-in RSS snapshots, then writes
normalized RSS items and diagnostics under `artifacts/stages/`. Article pages
are not fetched in this stage. All registered sources run by default; a source
can be selected by repeating `--source`.

Run the stage with:

```text
python -m headlyn.ingestion.pipeline \
  --source firstpost \
  --source ndtv \
  --source hindustan-times \
  --mode snapshot \
  --snapshot-date 2026-05-28 \
  --run-id local-test
python -m headlyn.ingestion.pipeline --mode live

# Run only selected sources:
python -m headlyn.ingestion.pipeline \
  --source firstpost \
  --source ndtv \
  --mode live
```

The ingestion pipeline uses only the Python standard library. Each source is
processed concurrently and writes only to its own source-scoped artifact
directory. A run-level `summary.json` records successful, failed, and partial
source results.

The story-normalization stage consumes an ingestion run and uses the local
Gemma 4 model through Ollama for entity extraction and BAAI/BGE-M3 sparse lexical
weights for pair scoring. It writes source-linked stories under
`artifacts/stages/story_normalization/<run_id>/`.

Run it after ingestion:

```text
python -m headlyn.story_normalization.pipeline \
  --ingestion-run-id local-test
```

The local runtime must have the `gemma4:e4b-it-q4_K_M` Ollama model available and the
`FlagEmbedding` dependency installed for BGE-M3. Use `--entity-model` and
`--llm-endpoint` to override the LLM defaults.

Selection should avoid allowing one publisher to dominate when alternatives
are available. The edition should generally represent at least four publishers
and cap a publisher at roughly three items where the day's inventory allows it.
This is a diversity guardrail, not a semantic story-merging rule.

## Newsletter item contract

Every selected item should contain:

- headline
- cleaned RSS description
- publisher/source name
- publication timestamp
- original article URL
- topic section

Descriptions may be lightly cleaned for HTML, whitespace, and length. Headlyn
does not generate canonical summaries in this phase; the newsletter presents
the source-provided description with clear attribution.

## Editorial and delivery rules

- The edition uses India as the initial scope for general news and is designed
  for a morning delivery window in India Standard Time.
- Technology & Science and Sports may contain worldwide coverage.
- The target length is approximately 8–10 items, suitable for a five-minute
  read.
- Exact duplicate URLs and repeated normalized titles are removed.
- Articles from different publishers remain separate items, even when they
  discuss the same event.
- If a source fails, healthy sources may still contribute to the edition.
- If fewer than five valid items are available, the edition should fail safely
  rather than send an empty or misleading newsletter.
- External delivery must include unsubscribe information before launch.

## Current source and data assets

The current RSS source pool contains Firstpost plus three India-wide feeds:
The Indian Express, NDTV, and Hindustan Times. Every source has a separate
registry configuration and source-scoped artifact directory.

| Source ID | Website | RSS feed |
| --- | --- | --- |
| `firstpost` | [Firstpost](https://www.firstpost.com/) | `https://www.firstpost.com/commonfeeds/v1/mfp/rss/india.xml` |
| `indian-express` | [The Indian Express](https://indianexpress.com/) | `https://indianexpress.com/section/india/feed/` |
| `ndtv` | [NDTV](https://www.ndtv.com/) | `https://feeds.feedburner.com/ndtvnews-india-news` |
| `hindustan-times` | [Hindustan Times](https://www.hindustantimes.com/) | `https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml` |

- RSS snapshots: [`assets/rss-feeds/raw/`](./assets/rss-feeds/raw/)
- RSS snapshot notes: [`assets/rss-feeds/README.md`](./assets/rss-feeds/README.md)
- RSS ingestion code: [`headlyn/ingestion/`](./headlyn/ingestion/)
- Story normalization code: [`headlyn/story_normalization/`](./headlyn/story_normalization/)
- Story normalization plan: [`assets/plans/STORY-NORMALIZATION-LLM-ENTITY-BGE-M3-PLAN.md`](./assets/plans/STORY-NORMALIZATION-LLM-ENTITY-BGE-M3-PLAN.md)
- Stage outputs and diagnostics: [`artifacts/stages/`](./artifacts/stages/)
- Ingestion tests: [`tests/`](./tests/)

## Explicitly out of scope for v1

The following research direction is paused for the newsletter product:

- dense embeddings and semantic similarity scoring
- article chunking and chunk aggregation
- hybrid semantic/lexical retrieval
- pairwise scoring and similarity thresholds
- similarity graphs and graph clustering
- cross-day story timelines
- LLM-generated headline rewriting and summaries; these are later pipeline stages
- personalized ranking or personalized editions

The existing clustering artifacts are retained as historical research context.
They are not part of the active newsletter flow and should not determine the
current product requirements.

## Success criteria for the first edition

A successful daily edition should have 8–10 valid items when enough source
content exists, include at least four publishers when possible, contain no
exact duplicates, preserve a source link for every item, and render clear
non-empty topic sections. The same edition should be reproducible for every
subscriber for that morning.
