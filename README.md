# Headlyn

Headlyn aggregates RSS news, groups reports about the same event into stories,
rewrites selected stories with a local Gemma model, and produces a shared daily
newsletter.

## Pipeline

```text
RSS feeds
  → ingestion and validation
  → canonical document text
  → BGE-M3 dense and sparse features
  → Gemma entity extraction
  → chronological story clustering
  → story selection and rewriting
  → newsletter rendering
  → preview or email delivery
```

## Story clustering algorithm

For each document, the pipeline searches active story representations using
Qdrant dense retrieval and SQLite FTS5 lexical retrieval. Candidates are
unioned and reranked with semantic, lexical, and entity signals.

Current configuration:

```text
semantic weight: 0.70
lexical weight:  0.15
entity weight:   0.15
match threshold: 0.70
```

Scores at or above `0.70` attach the document to the best story; otherwise a
new singleton story is created. Story representations use:

- mean dense embedding
- element-wise maximum sparse weights
- union of extracted entities
- latest article as the newsletter representative

Embeddings and successful entity extractions are cached in the persistent
Qdrant document collection. Cache entries are validated by document
fingerprint, model, and prompt version.

## Newsletter flow

```text
clustered stories
  → balanced selection across sources and topics
  → Gemma headline and summary rewriting
  → topic section organization
  → HTML/text newsletter
  → preview or Mailjet delivery
```

## Running locally

```bash
source venv/bin/activate
ollama serve
ollama pull gemma4:e4b-it-q4_K_M
docker run -p 6333:6333 qdrant/qdrant
```

Run the complete application pipeline:

```bash
python -m headlyn.pipeline --edition-date 2026-08-15
```

Use `--send` only when Mailjet credentials are configured. Preview is the
default.

## Dataset evaluation

The phase 0 dataset contains 170 articles and 14,365 pair annotations:

```text
same_story: 146
unrelated:  14,147
related:    72
```

Run the real document and clustering pipeline:

```bash
python -m unittest tests.test_story_clustering_dataset -v
```

Evaluate generated stories:

```bash
python scripts/evaluate_story_clusters.py \
  --stories artifacts/stages/story_clustering/phase0-real-dataset-test/newsletter_stories.json \
  --annotations assets/datasets/phase0/pair_annotations.json \
  --output artifacts/evaluations/phase0-story-clustering.json
```

Threshold results using the selected weights:

| Threshold | Precision | Recall | F1 | False merges | Missed same-story |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.60 | 0.1818 | 0.8493 | 0.2995 | 558 | 22 |
| 0.65 | 0.5491 | 0.6507 | 0.5956 | 78 | 51 |
| **0.70** | **0.8763** | **0.5822** | **0.6996** | **12** | **61** |
| 0.75 | 0.9697 | 0.2192 | 0.3575 | 1 | 114 |
| 0.80 | 1.0000 | 0.0548 | 0.1039 | 0 | 138 |

Threshold `0.70` was selected for the best F1 and practical precision/recall
balance. Lower thresholds created too many false merges; higher thresholds
missed too many same-story pairs.

Run the threshold sweep:

```bash
python scripts/run_story_threshold_sweep.py \
  --features artifacts/stages/document_preparation/phase0-real-dataset-test/document_features.jsonl \
  --annotations assets/datasets/phase0/pair_annotations.json \
  --output artifacts/evaluations/threshold-sweep.json
```

## Configuration and links

Copy `.env.example` to `.env` for Qdrant, Ollama, and optional Mailjet settings.
Never commit `.env` or credentials.

- Ingestion: [`headlyn/ingestion/`](./headlyn/ingestion/)
- Document processing: [`headlyn/document_processing/`](./headlyn/document_processing/)
- Story clustering: [`headlyn/story_clustering/`](./headlyn/story_clustering/)
- Story index: [`headlyn/story_index/`](./headlyn/story_index/)
- Newsletter: [`headlyn/newsletter/`](./headlyn/newsletter/)
- Dataset: [`assets/datasets/phase0/`](./assets/datasets/phase0/)
- Plans: [`assets/plans/`](./assets/plans/)
- Artifacts: [`artifacts/stages/`](./artifacts/stages/)
