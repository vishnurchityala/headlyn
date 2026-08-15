<p align="center">
  <img src="./assets/images/HEADLYN-BLUE-LOGO.png" alt="Headlyn Logo" width="280" />
</p>

# Headlyn

Headlyn is a daily news briefing. It aggregates RSS feeds from multiple
publishers, normalizes related reports into story clusters, rewrites the
selected stories with a local LLM, and delivers one shared morning newsletter
by email.

## Product direction

The first product is a shared, editorially grounded newsletter. RSS items are
normalized into source-linked story clusters before selection. The newsletter
uses a local LLM to create a concise headline and summary from the clustered
RSS titles and descriptions while preserving a representative source link.

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
  → rewrite and classify stories with Gemma
  → select a balanced set across publishers and topics
  → organize items into topic sections
  → render the morning email
  → preview or send the shared edition to subscribers
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

The newsletter stage consumes `newsletter_stories.json`, asks the local Gemma
model for a grounded headline, summary, and controlled topic section, then
selects a balanced set of stories. Preview is the default and does not require
Mailjet credentials:

```text
python -m headlyn.newsletter.pipeline \
  --story-run-id 20260815T091659Z \
  --edition-date 2026-08-15
```

The complete one-shot pipeline can run ingestion, story normalization, and
newsletter generation together:

```text
python -m headlyn.pipeline --edition-date 2026-08-15
```

Use `--send` only after configuring the Mailjet Send API environment variables:

Copy `.env.example` to `.env`, replace the placeholders, and load it into the
shell before running the send command. Never commit `.env` or real credentials.

```text
MJ_APIKEY_PUBLIC=...
MJ_APIKEY_PRIVATE=...
HEADLYN_MAILJET_FROM=your-confirmed-sender@example.com
HEADLYN_MAILJET_FROM_NAME=Headlyn
HEADLYN_MAILJET_REPLY_TO=your-confirmed-sender@example.com
HEADLYN_RECIPIENTS=one@example.com,two@example.com
HEADLYN_UNSUBSCRIBE_INSTRUCTIONS="Reply to this email to unsubscribe."
```

The first mailing version is intended for an internal/test recipient list.
Preview artifacts and delivery state are written under
`artifacts/stages/daily_newsletter/<edition_date>/`. Sending is idempotent by
edition date; use `--force-resend` only when an intentional repeat delivery is
required.

Selection should avoid allowing one publisher to dominate when alternatives
are available. The edition should generally represent at least four publishers
and cap a publisher at roughly three items where the day's inventory allows it.
This is a diversity guardrail, not a semantic story-merging rule.

## Newsletter story contract

Every selected story contains:

- LLM-rewritten headline
- grounded LLM summary
- controlled topic section
- representative publisher/source name
- publication timestamp
- representative original article URL
- source story ID and cluster counts

The LLM receives only the clustered RSS titles, descriptions, and publisher
names. If rewriting fails for a story, the representative RSS title and
description are used as a diagnosed fallback. All contributing source records
remain available in the story-normalization debugging artifacts.

## Editorial and delivery rules

- The edition uses India as the initial scope for general news and is designed
  for a morning delivery window in India Standard Time.
- Technology & Science and Sports may contain worldwide coverage.
- The target length is approximately 8–10 items, suitable for a five-minute
  read.
- Exact duplicate URLs and repeated normalized titles are removed.
- Related articles from different publishers are represented by one
  source-linked story cluster when story normalization accepts the match.
- The daily edition targets ten stories, requires at least five valid stories,
  and caps a representative source at three stories where inventory allows.
- Preview generation is the default; Mailjet delivery requires `--send`.
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
- Newsletter code: [`headlyn/newsletter/`](./headlyn/newsletter/)
- Daily newsletter plan: [`assets/plans/DAILY-NEWSLETTER-MAILING-PLAN.md`](./assets/plans/DAILY-NEWSLETTER-MAILING-PLAN.md)
- Mailjet environment template: [`.env.example`](./.env.example)
- Stage outputs and diagnostics: [`artifacts/stages/`](./artifacts/stages/)
- Ingestion tests: [`tests/`](./tests/)

## Explicitly out of scope for v1

The following research direction is paused for the newsletter product:

- dense embeddings and semantic similarity scoring
- article chunking and chunk aggregation
- hybrid semantic/lexical retrieval
- cross-day story timelines
- personalized ranking or personalized editions
- production subscriber management and campaign automation
- website delivery; the newsletter is the first user interaction

The existing clustering artifacts are retained as historical research context.
They are not part of the active newsletter flow and should not determine the
current product requirements.

## Success criteria for the first edition

A successful daily edition should have 8–10 valid stories when enough source
content exists, include at least four publishers when possible, contain no
exact duplicates, preserve a representative source link for every story, use
grounded rewritten content or a source-text fallback, and render clear
non-empty topic sections. The same edition should be reproducible for every
subscriber for that morning.
