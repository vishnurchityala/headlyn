# Headlyn product notes

## Current product

Headlyn is being pivoted from a news canonicalization and clustering project
into a daily newsletter. The initial sourcing scope is India for general news;
Technology & Science and Sports can be sourced globally.

The first edition is a single shared morning briefing for all subscribers. It
should take about five minutes to read and contain roughly 8–10 headlines with
short descriptions. Items are grouped into topic sections, not merged into
canonical stories.

## Desired reader flow

```text
Multiple RSS sources
  → fresh daily feed items
  → metadata cleanup and validation
  → exact duplicate removal
  → balanced editorial selection
  → topic sections
  → one morning email edition
```

## First implementation stage: RSS ingestion

The first active stage is a config-driven, source-scoped RSS worker. It currently
supports only the Firstpost India feed, live execution, and RSS snapshot replay.
Each feed item is normalized and exact duplicate URLs and titles are removed.
Article pages are not fetched.

The normalized record contains the source, scope, category, title, description,
publication timestamp, canonical URL, tags, stable article ID, and ingestion
timestamp. Later pipeline stages may use an LLM to rewrite and structure these
RSS items into the newsletter.

Run outputs are written to ignored directories:

```text
artifacts/stages/rss_ingestion/<run_id>/<source_id>/
```

Workers can be invoked independently:

```text
python -m headlyn.ingestion.worker --source firstpost --mode live
```

Existing clustering artifacts remain untouched. No cache directory is used.

The newsletter should feel useful without pretending to provide original
reporting. The source headline and description remain visible, and every item
links to the publisher's article.

## Editorial decisions already made

- Promise: a daily briefing with India-first general news and worldwide
  Technology & Science and Sports coverage.
- Format: topic sections.
- Balance: broad source coverage rather than one-publisher dominance.
- Length: approximately a five-minute read.
- Cadence: morning briefing.
- Audience model: one shared edition for all subscribers in v1.
- Initial sections: National, Politics, Business & Economy, Technology &
  Science, World, Sports, and Other. National, Politics, Business & Economy,
  and Other begin with India-only sourcing; Technology & Science and Sports
  are worldwide. World should be limited to international developments that
  are relevant to the initial audience.

Sections may be omitted when there is no worthwhile item. A practical diversity
guardrail is to aim for at least four publishers and no more than about three
items from one publisher when enough alternatives exist.

## Content rules

Use RSS metadata as the initial content contract:

- headline
- description
- source/publisher
- published time
- original URL

Only light cleanup is expected: remove HTML, normalize whitespace, and keep
descriptions readable in an email. Remove duplicate URLs and repeated
normalized titles. Do not semantically merge articles from different sources;
multiple reports about one event may appear as separate headlines if selected.

If a feed is unavailable, use the remaining healthy feeds. Do not send a nearly
empty edition: fewer than five valid items should be treated as a failed
edition requiring review or retry.

## Product boundary

The current product does not need embeddings, Qwen models, chunking, hybrid
retrieval, pair scoring, graphs, clustering, canonical story records,
cross-source merging, AI summaries, or personalized ranking. Those components
belong to the earlier research direction and should remain clearly separated
from the newsletter flow.

Subscription management, transport/provider selection, and launch operations
are still open product decisions. Unsubscribe support is required before real
external sending. The RSS worker does not perform topic classification,
newsletter selection, LLM rewriting, or delivery.

## Open questions

- Which email delivery provider and sender identity will be used?
- What is the exact morning delivery time and timezone policy?
- Which topics should receive a fixed minimum number of slots?
- Should readers be able to reply with feedback or suggest sources?
- What is the approval/review policy for an edition with fewer than 8 items?

## Historical research

RSS snapshots, clustering experiments, and debugging artifacts remain useful
for reference and benchmarking, but they are not acceptance criteria for the
newsletter. The active product contract is documented in [`README.md`](./README.md).
