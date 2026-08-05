# Headlyn Evaluation Pipeline

## Summary

Build an offline, deterministic article-clustering pipeline evaluated against
`assets/datasets/articles/clustering-evaluation.json`.

The implementation will use an importable `headlyn_clustering/` package, stop
at clustering and evaluation, and produce metrics plus inspectable run
artifacts. No LLM, network service, or model download is required.

## Key Changes

- Add immutable models for:
  - `Article`
  - `GoldLabel`
  - `CandidatePair`
  - `CandidateEvidence`
  - `PairScore`
  - `Cluster`
  - `EvaluationReport`
  - `PipelineRequest` and `ClusteringRunResult`

- Add stages under `headlyn_clustering/`:
  - `data.py`: load and validate the evaluation JSON; separate gold labels
    from runtime articles.
  - `text.py`: normalize paragraphs into deterministic `clean_text` and
    embedding input.
  - `embedding.py`: Sentence Transformer vectors plus deterministic BM25
    lexical weights and spaCy entities using title, description, and body.
  - `hybrid_candidate.py`: union semantic, lexical, and title-similarity
    candidates with rank and provenance.
  - `scoring.py`: combine semantic, lexical, title, entity/anchor, and
    temporal features.
  - `graph.py`: build accepted-edge graph and preserve rejected-edge
    explanations.
  - `clustering.py`: deterministic thresholded connected-component clustering
    with singleton preservation.
  - `evaluation.py`: calculate pairwise precision/recall/F1, purity,
    completeness, false merges, missed links, and hard-negative results.
  - `artifacts.py`: write deterministic JSON/JSONL run artifacts.
  - `pipeline.py`: expose the reusable `ClusteringPipeline.run(...)` API.

- Use this pipeline order:

  ```text
  Load dataset
  → separate gold labels
  → normalize articles
  → generate deterministic embeddings
  → retrieve hybrid candidates
  → score candidate pairs
  → build similarity graph
  → cluster articles
  → evaluate against gold labels
  → persist artifacts
  ```

- Use these defaults:
  - `test` split for the main evaluation runner.
  - Top 8 candidates per retriever and article.
  - Weighted pair score: semantic 45%, lexical 25%, title 15%,
    anchor/entity overlap 10%, temporal proximity 5%.
  - Configurable acceptance threshold, default `0.58`.
  - Stable pair ordering by sorted article IDs.
  - Stable cluster IDs derived from sorted member IDs and algorithm version.
  - Quality thresholds are configurable and report-only by default until the
    baseline is measured.

- Add thin root wrappers:
  - `pipeline.py`: build default dependencies and expose `run_pipeline()`.
  - `main.py`: execute the default pipeline evaluation.
  - `test.py`: run fixed evaluation scenarios from the dataset’s `test` split.

- Move the current scraper runner into `scripts/run_scrapers.py` so scraper
  functionality remains available while `main.py` becomes the clustering entry
  point.

## Artifacts

Each run writes to `artifacts/runs/<run_id>/`:

- `run_manifest.json`
- `clusters.json`
- `candidate_pairs.jsonl`
- `pair_scores.jsonl`
- `evaluation_report.json`
- `error_cases.jsonl`

Pipeline-stage artifacts contain only article/runtime data. Gold labels appear
only in evaluation reports and error-analysis artifacts.

## Manual Verification

- Run `python3 main.py` to confirm the pipeline entry point loads the test
  split and reports success.
- Run `python3 test.py` to inspect the loaded split, article count, and label
  count.
- Confirm the dataset has 56 articles split evenly into 28 dev and 28 test
  records when loading without a split filter.
- Confirm runtime `Article` values do not expose gold-label fields.
- Preserve all existing datasets, RSS snapshots, scraper behavior, and user
  changes in existing planning files.

## Assumptions

- `headlyn_clustering` is the Python package name; `headlyn-clustering` is the
  descriptive project name.
- V1 ends at article clusters and evaluation; canonical story generation is
  deferred.
  - `BAAI/bge-small-en-v1.5` is the default semantic embedding backend.
    BM25 lexical weights are generated in the embedding stage so hybrid
    retrieval only consumes them and does not calculate weights.
- The evaluation dataset remains unchanged; the loader separates labels in
  memory.
- This iteration uses manual verification only; no automated test package is
  included.
