# Headlyn — Current Implementation Context

## Product goal

Headlyn aggregates RSS news, groups reports about the same event into stories,
rewrites selected stories with a local Gemma model, and produces one shared
daily newsletter. The initial source scope is India-focused general news;
Technology & Science and Sports may include global coverage.

## Active end-to-end flow

```text
RSS/article inputs
  → adapter validation
  → canonical text
  → BGE-M3 dense and sparse features
  → Gemma entity extraction
  → cached document features
  → chronological story clustering
  → story selection and rewriting
  → topic sections
  → HTML/text newsletter
  → preview or Mailjet delivery
```

Video document models and adapters exist, but video sourcing and ingestion are
not active in the current phase.

## Document preparation

`StoryDocument` is the shared input model for RSS articles and pre-sourced
videos. Adapters validate required fields and build a canonical representation
from title plus body/summary.

Document preparation produces:

- normalized document records;
- BGE-M3 normalized dense vectors;
- BGE-M3 sparse lexical weights;
- Gemma entity results in CSV-derived internal entity records; and
- `document_features.jsonl` for downstream clustering.

The persistent Qdrant document collection caches embeddings and successful
entity extractions. Cache compatibility requires the same document fingerprint,
model, and relevant configuration (`max_length` for embeddings, prompt version
for entities). Failed entity extractions are not cached.

## Streaming story clustering

Documents are sorted by publication time and processed serially. Each document
searches only active story representations:

1. Qdrant retrieves dense candidates.
2. SQLite FTS5 retrieves lexical candidates.
3. Candidate lists are unioned and deduplicated.
4. Each candidate is scored with semantic, BGE sparse lexical, and entity
   overlap signals.
5. The best candidate is attached when its score reaches the cutoff; otherwise
   a singleton story is created.

Current production configuration:

```text
semantic weight: 0.70
lexical weight:  0.15
entity weight:   0.15
match threshold: 0.70
```

The score is:

```text
0.70 × semantic_score
+ 0.15 × lexical_score
+ 0.15 × entity_score
```

Temporal scoring remains available but is currently weighted at zero. Stories
are closed after the configured inactivity window, currently 72 hours.

When a document is attached, story state is updated using:

- mean of all member dense vectors;
- element-wise maximum of all member sparse weights;
- union of all member entity names; and
- the latest article as the newsletter/display representative.

The story state of record is SQLite. Qdrant stores the searchable story vector
and compact payload. Assignment diagnostics and newsletter-compatible story
artifacts are written under `artifacts/stages/story_clustering/<run_id>/`.

The former `headlyn/story_normalization/` implementation is legacy research;
the active path is `document_processing` → `story_clustering` → `story_index`.

## Dataset results and selected operating point

The phase 0 dataset contains 170 articles and 14,365 pair annotations:

```text
same_story: 146
unrelated:  14,147
related:    72
```

The selected weights were evaluated across cutoff values:

| Threshold | Precision | Recall | F1 | False merges | Missed same-story |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.60 | 0.1818 | 0.8493 | 0.2995 | 558 | 22 |
| 0.65 | 0.5491 | 0.6507 | 0.5956 | 78 | 51 |
| **0.70** | **0.8763** | **0.5822** | **0.6996** | **12** | **61** |
| 0.75 | 0.9697 | 0.2192 | 0.3575 | 1 | 114 |
| 0.80 | 1.0000 | 0.0548 | 0.1039 | 0 | 138 |

`0.70` is the current operating point because it produced the best F1 and a
practical precision/recall balance. Lower thresholds caused excessive false
merges; higher thresholds missed too many same-story pairs.

Evaluation commands:

```bash
python -m unittest tests.test_story_clustering_dataset -v

python scripts/evaluate_story_clusters.py \
  --stories artifacts/stages/story_clustering/phase0-real-dataset-test/newsletter_stories.json \
  --annotations assets/datasets/phase0/pair_annotations.json \
  --output artifacts/evaluations/phase0-story-clustering.json

python scripts/run_story_threshold_sweep.py \
  --features artifacts/stages/document_preparation/phase0-real-dataset-test/document_features.jsonl \
  --annotations assets/datasets/phase0/pair_annotations.json \
  --output artifacts/evaluations/threshold-sweep.json
```

The sweep reuses prepared features and creates a fresh story index per
threshold. It does not regenerate BGE or entity features.

## Newsletter flow

```text
active clustered stories
  → balanced source/topic selection
  → Gemma headline and summary rewrite
  → controlled topic classification
  → HTML and plain-text rendering
  → preview or explicit Mailjet send
```

The newsletter keeps source attribution, publication time, original URL, and
cluster membership. Failed rewrites fall back to the representative source
title and description. Preview is the default; sending is explicit and
environment-configured.

## Current risks and next ideas

- Recall remains limited: the selected operating point misses 61 labelled
  same-story pairs.
- BGE sparse score calibration should be improved before increasing lexical
  weight again; its scale is materially lower than semantic scores.
- Candidate retrieval should be evaluated separately from reranking so a
  valid story absent from the dense/FTS candidate union is distinguishable from
  a candidate rejected by scoring.
- Entity normalization and alias handling can improve cross-source overlap.
- A periodic active-story merge pass can repair early singleton decisions.
- Assignment diagnostics should retain top rejected candidates and component
  scores for false-negative analysis.
- Qdrant and Ollama availability should be health-checked before long dataset
  runs; local-service timeouts can otherwise produce partial runs.

## Repository anchors

- `headlyn/document_processing/`: adapters, canonical text, embeddings,
  entities, caches, and preparation artifacts.
- `headlyn/story_clustering/`: scoring, assignment, lifecycle, and artifacts.
- `headlyn/story_index/`: Qdrant and SQLite state adapters.
- `headlyn/newsletter/`: selection, rewriting, rendering, and delivery.
- `scripts/evaluate_story_clusters.py`: labelled-pair evaluation.
- `scripts/run_story_threshold_sweep.py`: threshold calibration.
- `tests/test_story_clustering_dataset.py`: real-model dataset integration run.
- `README.md`: concise setup, flow, and reported results.
- `.env.example`: Qdrant, Ollama, and optional Mailjet configuration.
