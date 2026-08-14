# Headlyn — Current Chat Context

## Project pivot

Headlyn has pivoted from a complex news canonicalization system to a daily
newsletter. The active goal is to aggregate multiple RSS/feed sources and send
one concise briefing to users by email. The initial sourcing scope is India for
general news, while Technology & Science and Sports can include worldwide
developments.

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

These are presentation sections, not story clusters. Two reports about the same
event may remain two separate newsletter items.

## End-to-end product flow

```text
RSS/feed sources
  → collect the current day's items
  → validate required metadata
  → lightly clean descriptions and titles
  → remove exact duplicate URLs/titles
  → choose a balanced daily set
  → assign topic sections
  → render the shared edition
  → deliver by email
```

### Source aggregation

The initial source pool includes Firstpost, The Hindu, Hindustan Times, News18,
PIB, and NDTV. RSS is the primary input. The source pool may expand, but a
source should retain attribution and a direct link in the final edition.

### Freshness and validation

An item should be considered valid only when it has a usable headline,
description, source, publication timestamp, and original URL. The daily run
should select items from the intended morning edition window and retain enough
metadata to diagnose feed failures or stale content.

### Cleanup and duplicate handling

Cleanup is intentionally light: strip feed HTML, normalize whitespace, and
truncate descriptions only as needed for email readability. Remove duplicate
URLs and repeated normalized titles. Do not use semantic similarity to merge
articles or construct a canonical event record.

### Selection and balance

Selection should prioritize useful, current items within each section's
geographic scope while avoiding publisher concentration. When enough content
exists, aim for at least four publishers and cap a publisher at roughly three
selected items. Topic balance should guide the edition, but weak or repetitive
items should not be included merely to fill a section.

### Rendering and delivery

The email should have a clear date/header, a short introduction, topic sections,
source attribution, links, and a footer. Unsubscribe information is mandatory
before sending to external subscribers. Transport/provider and subscription
management remain open decisions.

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

- Qwen or other embedding models;
- article chunking and chunk-level aggregation;
- semantic/lexical candidate retrieval;
- pair scoring thresholds;
- similarity graphs, Leiden, or Louvain;
- canonical story IDs or story timelines;
- cross-source story merging;
- generated canonical headlines or AI summaries; and
- personalized feeds or personalized newsletter editions.

## Repository context

- [`README.md`](./README.md) contains the current product contract.
- [`NOTES.md`](./NOTES.md) records product decisions and open questions.
- [`assets/rss-feeds/raw/`](./assets/rss-feeds/raw/) contains RSS snapshots.
- [`assets/datasets/`](./assets/datasets/) contains historical article data.
- [`scripts/`](./scripts/) contains source/feed experiments.
- Existing clustering code and artifacts are historical and not active runtime
  requirements.
