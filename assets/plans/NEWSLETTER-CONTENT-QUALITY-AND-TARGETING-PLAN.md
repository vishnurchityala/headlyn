# Newsletter Content Quality and Targeting Plan

## Goal

Improve the quality and usefulness of Headlyn's newsletter generation while
preparing the pipeline for targeted user content and non-article media.

The work covers four connected problems:

- Improve same-event clustering and reduce false merges.
- Extract useful, inspectable metadata from candidate story points.
- Expand the source base beyond the current India-focused RSS feeds.
- Support video, podcast, media, and social content alongside articles.

Personalized ranking and delivery should follow the creation of a reliable,
structured content contract. More sources and user targeting should not be
introduced before the pipeline can explain why a story was selected.

## Current flow

```text
RSS feeds
  → normalized RSS items
  → entity extraction
  → pair scoring
  → story grouping
  → LLM rewrite
  → balanced selection
  → HTML/plain-text newsletter
  → delivery
```

The current input contract is article-oriented and contains title,
description, publisher, publication time, URL, category, scope, and tags.
Story normalization extracts entities and scores pairs with entity overlap and
lexical similarity. Newsletter rewriting produces a headline, summary, and
section.

## Known current limitations

- Story grouping is seed-based instead of full graph-component clustering.
- Candidate pairs require shared distinctive primary entities, which can miss
  events without named entities.
- Generic entities can create false matches.
- Entity overlap is not event-, action-, time-, or location-aware.
- Global normalized-title deduplication can remove legitimate reports from
  different publishers.
- The representative article is selected primarily by description length and
  publication time, not source quality or editorial usefulness.
- Rewrite output is schema-checked but not fully validated for word count,
  factual support, or claim-level evidence.
- Preselection happens before rewriting and can discard useful candidates too
  early.
- Candidate metadata is currently limited to entities, section, source counts,
  article counts, confidence, and timestamps.
- The ingestion contract assumes article-style RSS items.
- The source registry currently contains only four primary feeds.
- There is no offline editorial evaluation set or feedback loop.

## Roadmap

### Phase 0 — Establish a quality baseline

Create a manually reviewed evaluation set from existing RSS snapshots and
recent pipeline artifacts.

Work:

- Label same-story and different-story article pairs.
- Label acceptable and unacceptable clusters.
- Review generated headlines, summaries, and sections.
- Record unsupported claims, stale items, duplicate stories, and poor source
  selection.
- Add stage diagnostics for candidate counts, pair rejection reasons, cluster
  confidence, rewrite failures, and selection reasons.

Deliverables:

- An editorial evaluation set of approximately 100–300 labeled pairs/clusters.
- A content-quality rubric.
- Baseline clustering precision and recall.
- Baseline rewrite factuality and fallback metrics.
- A repeatable evaluation command and report artifact.

Exit criteria:

- A proposed pipeline change can be compared against the current baseline.
- Reviewers can identify whether a failure came from ingestion, clustering,
  metadata, rewriting, or selection.

### Phase 1 — Improve newsletter generation quality

Strengthen generated output before adding personalization.

Work:

- Enforce headline and summary length limits.
- Validate the selected section against the controlled section list.
- Preserve attribution and uncertainty.
- Detect duplicate or near-duplicate generated headlines.
- Attach source evidence to generated claims.
- Preserve representative and contributing source links.
- Improve representative-source selection using freshness, source quality,
  completeness, and cross-source support.
- Expand preselection to roughly 2–3 times the final edition size, then rank
  after metadata and rewrite validation.

Suggested rewrite output:

```json
{
  "headline": "...",
  "summary": "...",
  "section": "Technology & Science",
  "source_claims": [
    {
      "claim": "...",
      "article_ids": ["article-..."]
    }
  ],
  "confidence": 0.86
}
```

Exit criteria:

- Every approved claim is traceable to source input.
- Summaries meet the configured word range.
- Unsupported or malformed rewrites fall back safely.
- Rewrite and selection decisions are visible in artifacts.

### Phase 2 — Improve clustering

Replace the current seed-based grouping with a more reliable event-clustering
stage.

Work:

- Add blocking by time window, category, geography, and distinctive entities.
- Expand extraction to include event type, action, location, time, products,
  organizations, and claims.
- Use entity overlap, lexical similarity, event compatibility, and temporal
  compatibility together.
- Build connected components or union-find clusters from accepted edges.
- Add cluster cohesion checks and split weak or over-broad clusters.
- Reduce the influence of generic entities such as countries, governments, and
  common political names.
- Preserve pair scores and merge/split reasons for review.
- Revisit URL/title deduplication so distinct publisher reports are not removed
  before cross-source comparison.

Exit criteria:

- False merges decrease against the Phase 0 set.
- Missed same-event matches decrease against the Phase 0 set.
- Cluster confidence is based on explicit evidence.
- Every cluster has an inspectable list of supporting articles and links.

### Phase 3 — Add structured candidate metadata

Create a versioned metadata contract for article items and story clusters.

Recommended fields:

- Topic and subtopic.
- Geography and audience geography.
- Event type and development stage.
- Entities and entity roles.
- Industry or domain.
- Importance, urgency, novelty, and expected impact.
- Audience segments.
- Content format and language.
- Source quality metadata.
- Extraction confidence and evidence references.

Example:

```json
{
  "topic": "Technology & Science",
  "subtopics": ["AI", "Cloud Infrastructure"],
  "geographies": ["India", "Global"],
  "event_type": "product_launch",
  "importance": 0.78,
  "urgency": 0.61,
  "novelty": 0.84,
  "audiences": ["developers", "founders"],
  "format": "article",
  "confidence": 0.90
}
```

Use deterministic extraction for source, timestamps, URLs, media type,
authors, feed tags, and channel information. Use the LLM for semantic fields,
with strict JSON validation, confidence, caching, and input fingerprints.

Exit criteria:

- Metadata is available before final selection.
- Metadata failures are explicit and do not silently become facts.
- Selection diagnostics explain which metadata influenced inclusion.
- Metadata artifacts can be reviewed independently of the email renderer.

### Phase 4 — Expand and govern the source base

Add sources incrementally after the content contract is stable.

Source batches:

- Indian national, business, and policy news.
- World news.
- Technology and science publications.
- Official company and engineering blogs.
- Cybersecurity and open-source sources.
- Research and developer sources.
- Sports, culture, and other audience-relevant verticals.

Extend `FeedConfig` with:

- Source type and format.
- Geographic scope.
- Topic scope.
- Publisher tier or quality notes.
- Language.
- Expected update frequency.
- Enable/disable state.
- Health information.

Add feed-health metrics:

- Last successful fetch.
- Staleness.
- Parse failures.
- Empty-feed rate.
- Duplicate rate.
- Average metadata completeness.
- Contribution to selected editions.

Exit criteria:

- New feeds can be added through registry configuration.
- A failed or noisy source is isolated without failing the whole run.
- Source expansion increases useful coverage without increasing repetitive
  newsletter content.

### Phase 5 — Generalize beyond articles

Replace the article-only assumption with a common content model.

```text
ContentItem
  ├── article
  ├── video
  ├── podcast
  ├── social_post
  └── media_report
```

Common fields:

- Canonical URL.
- Title and description.
- Publisher or creator.
- Published time.
- Content type.
- Thumbnail or media URL.
- Duration.
- Transcript availability.
- Language.
- Tags.
- Source attribution.

Initial integrations:

- YouTube channel RSS feeds.
- Official publisher video feeds.
- Podcast RSS feeds.
- Publisher media pages.
- Link-only social posts from approved sources.

For social content, preserve the original author and post URL. Treat it as a
source item, not automatically as verified fact. Use official APIs or stable
feed interfaces where possible and avoid fragile scraping as a dependency.

Update rendering with format-specific cards:

- Article: headline, summary, publisher, source link.
- Video: title, creator, duration, watch link.
- Podcast: episode, duration, listen link.
- Social post: author, excerpt, original post link.

Exit criteria:

- Non-article items pass through ingestion, metadata, selection, and rendering.
- Every format retains attribution and an original link.
- Unsupported media fails gracefully without blocking article content.

### Phase 6 — Introduce targeted user ranking

Begin with explainable targeting and cohort-level personalization rather than
fully independent newsletters for every user.

Initial preference fields:

- Topics and subtopics.
- Geography.
- Role or interest profile.
- Preferred content formats.
- Preferred depth.
- Language.
- Muted topics.
- Delivery frequency.

Use explicit preferences first. Add behavioral signals later:

- Opened.
- Clicked.
- Saved.
- Skipped.
- Unsubscribed.
- Requested more or less of a topic.

Suggested ranking model:

```text
user_score =
  global_importance
  × freshness
  × topic_affinity
  × geography_affinity
  × format_affinity
  × novelty
  × source_quality
  × diversity_adjustment
```

Keep a shared core of important stories and personalize a smaller portion of
the edition. Generate facts once from the vetted story object. Do not create
independent factual summaries per user until consistency is proven.

Exit criteria:

- Users can control preferences.
- Every selected story has an explainable relevance score.
- Personalization does not remove critical shared news.
- Preference changes, unsubscribe behavior, and approval state are respected.

### Phase 7 — Feedback and continuous improvement

Connect delivery feedback back to the stage that caused the result.

```text
Source
  → extraction
  → clustering
  → metadata
  → rewrite
  → selection
  → delivery
  → user feedback
```

Classify failures as source, parsing, clustering, metadata, rewriting,
ranking, format, or preference failures. Version source snapshots, prompts,
model versions, metadata schemas, and selection parameters so an edition can
be reproduced.

## Cross-cutting requirements

- Keep artifacts inspectable and versioned by stage.
- Preserve original source links and attribution.
- Make LLM output schema-validated and cacheable.
- Separate source quality from story importance.
- Prefer deterministic rules for safety-critical fields.
- Keep a safe held-edition state when content is insufficient.
- Add tests for every new content type and metadata field.
- Protect user preference and engagement data from diagnostic artifacts.

## Recommended implementation order

1. Phase 0: baseline and evaluation.
2. Phase 1: grounded newsletter generation.
3. Phase 2: clustering improvements.
4. Phase 3: structured metadata.
5. Phase 4: source expansion.
6. Phase 5: video, podcast, media, and social support.
7. Phase 6: targeted ranking and user preferences.
8. Phase 7: feedback and continuous optimization.

## Immediate next milestone

Before adding more feeds, build the evaluation set and implement:

- Full graph-based cluster grouping.
- Cluster debug and merge/split diagnostics.
- Rewrite word-count and evidence validation.
- Candidate preselection headroom.
- A first versioned candidate metadata artifact.

This milestone establishes whether future source and personalization work is
improving the newsletter rather than only increasing the amount of content.
