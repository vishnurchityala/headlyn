# Streaming Story Clustering with Hybrid Retrieval

## Objective

Replace article-pairwise clustering with incremental clustering over a
persistent story index. New documents are matched against story
representations rather than against every previous article.

The same algorithm supports both historical rebuilds and production
streaming:

```text
articles/videos
  → canonical text
  → BGE-M3 dense embedding + lexical representation
  → Gemma entity extraction
  → active-story hybrid retrieval
  → composite reranking
  → attach to best story or create singleton
  → update story index
```

This makes the main path approximately `O(n log m)`, where `m` is the active
story count and is much smaller than the document count. A periodic merge pass
may perform `O(m²)` work because it compares stories rather than articles.

## Document representation

The pipeline accepts both articles and videos through a common document
contract:

- `document_id`
- `document_type`: `article` or `video`
- `title`
- `description` for articles or `summary` for videos
- `source_id` and `source_name`
- `published_at` and `ingested_at`
- category and labels
- extracted entities

Build the embedding input as:

```text
Article: Title + description
Video:   Title + transcript-derived summary
```

Use the same BAAI/BGE-M3 model for dense embeddings and sparse lexical
features so articles and videos share one retrieval space. Video summaries
are preferred over raw platform descriptions because platform descriptions
may be promotional or boilerplate.

## Persistent indexes

Use two coordinated local indexes:

- Qdrant stores dense story vectors and story payloads.
- SQLite FTS5 stores representative text, BM25 data, document idempotency
  state, and operational metadata.

The index must expose an adapter equivalent to:

```python
class StoryIndex(Protocol):
    def search_active(self, document: StoryDocument, limit: int) -> list[StoryCandidate]: ...
    def get(self, story_id: str) -> StoryRecord | None: ...
    def upsert(self, story: StoryRecord) -> None: ...
    def close_inactive(self, cutoff: datetime) -> list[str]: ...
    def iter_active(self) -> Iterable[StoryRecord]: ...
    def merge(self, survivor_id: str, absorbed_id: str) -> StoryRecord: ...
```

Configuration should include the Qdrant endpoint, collection name, SQLite
path, embedding model/version, candidate limits, lifecycle window, scoring
weights, and match threshold.

## Story record

Each story stores:

- stable `story_id`
- member document IDs and complete source records
- running centroid embedding
- latest display document
- canonical entity set
- `first_seen`
- `latest_published_at`
- `last_updated_at`
- article/document count and source count
- `status`: `active` or `closed`
- merge lineage and absorbed story IDs

The centroid is used for retrieval. The latest published article or video is
used as the newsletter/display representative.

## Incremental clustering algorithm

For each document, ordered by `published_at` during a rebuild:

1. Validate the normalized document and skip duplicate `document_id` values.
2. Build canonical text and generate its BGE-M3 embedding/lexical features.
3. Extract explicit entities with Gemma and normalize unambiguous aliases.
4. Remove or archive stories inactive for more than 72 hours.
5. Retrieve the top 20 active stories from Qdrant by dense similarity.
6. Retrieve the top 20 active stories from SQLite FTS5 by BM25.
7. Union both candidate sets and rerank them.
8. Attach the document to the best story when its score meets the threshold;
   otherwise create a singleton story.
9. Persist the assignment, scores, updated story, and index state.

Use entity overlap as a reranking signal, not a hard gate. Category and labels
are soft features or filters and must not prevent a strong cross-modal match.

Late-arriving documents match the current active index immediately. They do
not rewind or replay the stream. Full backfills use a fresh index namespace
and process all documents chronologically.

## Reranking

Normalize each component to `[0, 1]`:

```text
semantic_score = dense cosine similarity
lexical_score  = normalized BM25 score
entity_score   = canonical entity overlap
time_score     = exp(-age_hours / 24)
```

Initial precision-first weights are:

```text
final_score =
    0.50 × semantic_score
  + 0.25 × lexical_score
  + 0.20 × entity_score
  + 0.05 × time_score
```

Start with a configurable `match_threshold` of `0.70`. Calibrate this value
against the labelled same-story/different-story dataset before production.
If entity extraction fails, use `entity_score = 0` and record degraded
matching rather than inventing entities.

## Story updates and lifecycle

When a document joins a story, update the centroid incrementally:

```text
new_centroid = normalize(
    (member_count × old_centroid + document_embedding)
    / (member_count + 1)
)
```

Keep `latest_published_at` separate from `last_updated_at`. The former is
source event time; the latter records the most recent indexed activity and is
used for lifecycle decisions.

Stories with no update for 72 hours become `closed`. Closed stories remain
available for audit/history but are excluded from normal retrieval. A late
document that cannot match an active story creates a new story rather than
reopening a closed one.

## Daily maintenance merge

Run a daily merge-only maintenance job over active story representatives:

- compare story representations, never all member-document pairs;
- use the same hybrid reranker with a stricter precision-oriented threshold;
- retain the older story ID as the survivor;
- update the survivor centroid and member/source counts;
- record absorbed IDs and merge lineage;
- do not automatically split stories in v1.

## Artifacts

Write the following under
`artifacts/stages/story_normalization/<run_id>/`:

```text
entity_extractions.jsonl
embedding_events.jsonl
story_assignments.jsonl
story_merges.jsonl
stories.jsonl
newsletter_stories.json
summary.json
```

Every assignment should include the document ID, candidate story IDs, dense
score, BM25 score, entity score, time score, final score, threshold, decision,
rejection reason, model versions, and index version.

## Failure and idempotency behavior

- Cache entity and embedding results by document fingerprint and model version.
- Never attach one document more than once.
- Continue with degraded scoring when entity extraction fails.
- Record Qdrant, SQLite, embedding, and LLM failures in `summary.json`.
- Hold or fail the clustering run when retrieval infrastructure is unavailable;
  do not silently create uncontrolled singleton stories.

## Evaluation and acceptance criteria

Evaluate:

- pair precision and recall;
- over-merge and under-merge rates;
- multi-source and singleton story rates;
- entity extraction validity;
- average documents per story;
- cross-modal article/video matching;
- late-arrival and 72-hour closure behavior;
- idempotent replay and merge-lineage correctness.

Precision is prioritized initially: incorrectly merging unrelated events is
worse than leaving a same-event report as a separate story.

Tests must verify chronological rebuilds, active-story-only retrieval,
dense/BM25/entity scoring, singleton creation, centroid updates, lifecycle
closure, late-arrival handling, duplicate suppression, daily merges, and
diagnostics for index/model failures.

## Assumptions

- Qdrant is the persistent dense-vector backend.
- SQLite FTS5 supplies BM25 lexical retrieval and operational state.
- BGE-M3 is the initial shared model for articles and videos.
- Timestamps are normalized to UTC; newsletter scheduling remains in India
  Standard Time.
- The existing pair-annotation dataset is used for threshold calibration.
