# Story Normalization with LLM Entities and BGE-M3

## Objective

Convert multiple RSS articles from the same daily ingestion run that report the
same real-world event into one normalized story point while preserving every
publisher's attribution and source link.

Example:

```text
Firstpost: PM Modi comments on India-US trade talks
NDTV: PM Modi says India will protect national interests in trade deal
Hindustan Times: PM Modi discusses India-US trade negotiations
```

These should become one story with three source articles.

This stage operates only on RSS titles and descriptions. It does not fetch
article pages, generate a new summary, or send email.

## Position in the newsletter pipeline

```text
RSS ingestion
  → story normalization
  → newsletter story selection
  → optional LLM rewriting
  → email rendering and delivery
```

The ingestion run is already limited to one daily edition, so publication time
is not used as an event-matching feature. Timestamps remain available for
ordering and representative-article selection.

## Core design

The matching model has only two parameters:

```text
entity_score  = overlap of LLM-extracted canonical entities
lexical_score = BGE-M3 sparse lexical similarity

final_score = 0.5 × entity_score + 0.5 × lexical_score
```

The initial merge rule is:

```text
at least one primary entity overlaps
AND
final_score >= 0.5
```

The threshold and weights are starting values. They must be evaluated against
manually labelled article pairs before production use.

## Model responsibilities

### LLM: entity extraction and canonicalization

The LLM receives only the RSS title and description. It extracts entities and
normalizes unambiguous aliases, but it does not decide whether two articles
belong to the same story.

Required behavior:

- Extract only entities explicitly present in the input.
- Mark primary and secondary entities.
- Normalize clear aliases such as `PM Modi`, `Narendra Modi`, and
  `Prime Minister Modi` to one canonical name.
- Preserve entity type: `PERSON`, `ORG`, `GPE`, `LOC`, `EVENT`, `PRODUCT`,
  `LAW`, or `OTHER`.
- Return strict JSON.
- Avoid inferred facts, invented entities, and unsupported relationships.

Example extraction result:

```json
{
  "article_id": "article-123",
  "entities": [
    {
      "text": "PM Modi",
      "canonical_name": "Narendra Modi",
      "type": "PERSON",
      "role": "primary"
    },
    {
      "text": "India",
      "canonical_name": "India",
      "type": "GPE",
      "role": "primary"
    },
    {
      "text": "US",
      "canonical_name": "United States",
      "type": "GPE",
      "role": "secondary"
    }
  ]
}
```

The extraction result should be cached by `article_id` and retained in the
stage artifacts for debugging and reproducibility.

### BGE-M3: lexical similarity

Use BGE-M3's sparse lexical representation over the article title and
description. Do not use its dense embedding output for this stage; dense
embeddings would introduce a third semantic-similarity behavior into the
two-parameter design.

The lexical comparison captures shared event terms, actions, subjects, names,
locations, and important phrases without requiring separate event, topic, or
subject scores.

## Processing pipeline

### 1. Load ingestion artifacts

Read normalized items from:

```text
artifacts/stages/rss_ingestion/<run_id>/<source_id>/items.jsonl
```

Use the run-level summary to discover healthy and failed sources. Healthy
source items continue to the normalization stage when another source failed.

### 2. Validate and prepare text

Require every item to contain:

- `article_id`
- `source_id`
- `source_name`
- `title`
- `description`
- `published_at`
- `url`

Build the model input from:

```text
Title: <RSS title>
Description: <RSS description>
```

Do not fetch or append article-page content.

### 3. Extract entities with the LLM

Run the strict entity-extraction prompt for every valid article. Persist the
raw extraction result, normalized entities, model identifier, and extraction
status. Invalid responses should be recorded and excluded from entity-based
matching rather than silently repaired with guesses.

### 4. Normalize entity aliases

Normalize case, whitespace, punctuation, known honorifics, and unambiguous
aliases. The canonical entity set should distinguish primary entities from
secondary context entities.

An article with no primary entities should not be merged solely because its
wording is generally similar to another article.

### 5. Generate candidate pairs

Avoid all-pairs comparison. A pair becomes a candidate when:

- both articles have at least one shared primary canonical entity; or
- lexical similarity is exceptionally strong and both articles have compatible
  topic metadata.

Candidate blocking reduces computation and prevents unrelated articles about
the same public figure from being treated as one event automatically.

### 6. Calculate the two scores

Entity score is calculated from the canonical entity sets. A weighted entity
type policy may be introduced later, but the initial version should remain
simple and inspectable.

Lexical score is calculated from BGE-M3 sparse lexical matching over the title
and description. Store both component scores and the final score for every
accepted or rejected candidate pair.

### 7. Build conservative story groups

Use representative-based clustering rather than unrestricted graph connected
components. Graph transitivity can incorrectly merge unrelated events:

```text
article A matches article B
article B matches article C
article A and article C are different events
```

Recommended procedure:

1. Sort unassigned articles by description completeness and publication time.
2. Start a story with the strongest unassigned article.
3. Compare candidates with the story representative.
4. Add a candidate only when it passes the entity gate and final threshold.
5. Re-check every member against the representative to prevent cluster drift.
6. Start a new story for candidates that do not match.

### 8. Select a representative article

Initially select the article with the most complete description, using
publication time as a tie-breaker. Preserve all source articles under the
story, including their original headlines, descriptions, timestamps, and
links.

LLM rewriting of the representative headline or description is a later stage.

## Proposed output artifacts

```text
artifacts/stages/story_normalization/<run_id>/
  entity_extractions.jsonl
  pair_scores.jsonl
  stories.jsonl
  newsletter_stories.json
  summary.json
```

Each story should have this shape:

```json
{
  "story_id": "story-...",
  "representative_title": "...",
  "representative_description": "...",
  "latest_published_at": "...",
  "source_count": 3,
  "article_count": 3,
  "confidence": 0.86,
  "articles": [
    {
      "source_name": "Firstpost",
      "title": "...",
      "description": "...",
      "published_at": "...",
      "url": "..."
    }
  ]
}
```

## Configuration

The stage should expose a configuration object similar to:

```python
StoryNormalizationConfig(
    ingestion_run_id="daily-run",
    entity_model="gemma4:e4b-it-q4_K_M",
    llm_endpoint="http://127.0.0.1:11434/api/generate",
    lexical_model="BAAI/bge-m3",
    entity_weight=0.5,
    lexical_weight=0.5,
    merge_threshold=0.5,
    require_primary_entity=True,
    artifact_root="artifacts/stages",
)
```

Model outputs should be cached by article ID. Models should be loaded once per
pipeline process and reused across items.

## Failure handling

- A failed LLM extraction must not stop the complete daily run.
- Articles with invalid extraction output remain available as singleton stories
  when they pass basic validation.
- A failed BGE-M3 comparison should be logged and treated as a rejected match.
- Every source and model failure must appear in `summary.json`.
- No TLS, source, or article-page fallback should be introduced here.

## Evaluation KPIs

Before tuning production thresholds, create a manually labelled set of article
pairs with `same_story` or `different_story` labels.

Track:

- Pair precision: accepted matches that are truly the same event
- Pair recall: same-event pairs that were successfully matched
- Over-merge rate: unrelated events placed in one story
- Under-merge rate: same event split across stories
- Multi-source story rate
- Singleton story rate
- Entity extraction JSON validity rate
- Average articles per story
- Source coverage per edition

Precision should be prioritized initially. A missed merge is preferable to
combining two unrelated events in the newsletter.

## Out of scope

- Article-page scraping
- Full article summarization
- LLM-generated newsletter prose
- Personalized ranking
- Story timelines across multiple days
- Cross-day event continuity
- Email rendering and delivery
