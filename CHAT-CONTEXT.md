# CONTEXT.md

# Headlyn — News Canonicalization & Personalized Feed Platform

## Project Vision

Headlyn is a news consumption platform focused on solving two major problems:

1. News redundancy — multiple outlets publishing separate articles about the same underlying event.
2. Poor personalization — feeds operating on article-level interactions rather than story-level interests.

The long-term goal is to create a story-centric news experience where users consume consolidated stories instead of navigating multiple duplicate articles.

---

# Product Direction

After extensive discussion, the current architectural direction is:

* Canonicalization is implemented first.
* Recommendation/personalization is built on top of canonical stories.
* Story objects are NOT persistent.
* No timeline tracking.
* No cross-batch reconciliation.
* No story versioning.
* No evolving story identities.

The system operates in batches.

A batch of articles is clustered into story groups, summarized into canonical stories, and published. Once generated, stories are effectively immutable.

Architecture philosophy:

```text
Articles
→ Cluster
→ Canonical Story
→ Feed
```

NOT:

```text
Articles
→ Persistent Story Object
→ Timeline Updates
→ Story Evolution
```

Canonicalization is therefore treated as:

```text
Batch-level News Consolidation
```

rather than:

```text
Long-term Story Tracking
```

---

# Why Canonicalization Exists

Canonicalization is NOT primarily a summarization problem.

It is primarily:

```text
Event Identity Resolution
```

The hard question is:

```text
Do these articles describe the same event?
```

The LLM summary is only useful if clustering is correct.

A perfect summary generated from a bad cluster is still wrong.

---

# Core Product Decision

The recommendation engine MUST NOT be built before canonicalization.

Reason:

Recommendations should learn from:

```text
Story interactions
```

instead of:

```text
Article interactions
```

Example:

A user skipping three articles about the same event indicates:

```text
Story fatigue
```

not:

```text
Disinterest in the topic
```

Building recommendations before story abstraction would produce invalid behavioral data and require retraining later.

Correct build order:

```text
1. Ingestion
2. Canonicalization
3. Feed
4. Personalization
```

---

# Current Canonicalization Scope

The current PoC only focuses on:

```text
Batch Event Clustering
```

Excluded from PoC:

* Story evolution
* Live updates
* Duplicate collapse
* Timeline tracking
* Cross-batch story linking
* Persistent story IDs

---

# Baseline Canonicalization Pipeline

Current proposed pipeline:

```text
RSS ingestion
→ article extraction + cleaning
→ embedding generation
→ ANN-based candidate retrieval
→ similarity graph construction
→ Leiden/Louvain clustering
→ cluster grounding context creation
→ canonical story generation
```

This is considered:

```text
Baseline V1
```

No graph refinement layer initially.

The benchmark dataset will determine whether edge refinement is required.

Potential future refinement layer:

```text
embedding similarity
+ entity overlap
+ headline overlap
+ temporal proximity
+ cross-encoder verification
```

---

# Canonical Story Generation

One LLM call per cluster.

Desired behavior:

1. Corroboration-first
2. Source attribution
3. Conflict surfacing
4. Neutral language
5. Structured output

Example:

Instead of:

```text
CRPF deployment was necessary.
```

or

```text
CRPF deployment intimidated voters.
```

Canonical output should say:

```text
CRPF personnel were deployed during the election. TMC leaders alleged the deployment intimidated voters, while BJP leaders stated it was necessary to prevent violence.
```

---

# Story Sourcing Philosophy

Canonical stories never replace sources.

Story structure:

```text
Canonical Story
├── Headline
├── Summary
├── Sources
│   ├── Source A
│   ├── Source B
│   └── Source C
└── Attribution Metadata
```

Users should always be able to access original reporting.

Principle:

```text
Story First
Sources Second
```

but never:

```text
AI Summary Only
```

---

# Ingestion Service Architecture

Technology:

* Python 3.11+
* feedparser
* httpx
* Playwright
* BeautifulSoup4
* APScheduler
* SQLAlchemy
* Alembic
* PostgreSQL
* pgvector
* Docker

Architecture:

```text
RSS Feed
→ Fetch URLs
→ URL Dedup
→ Fetch Article
→ Extract Body
→ Clean Content
→ Content Dedup
→ Store Raw Article
```

No FastAPI.

No Celery.

No Redis.

No MongoDB.

Single-process scheduler architecture.

---

# Database Decision

Chosen:

```text
PostgreSQL + pgvector
```

Reasons:

* Uniform schema
* Relational querying
* Transactional integrity
* Embedding storage
* No separate vector DB required

---

# Initial Canonicalization Approach

Embeddings:

```text
headline + first 300-500 chars
```

Candidate model options:

* all-MiniLM-L6-v2
* Qwen3-Embedding-0.6B

Graph construction:

```text
Node = Article
Edge = Similarity
Weight = Similarity Score
```

Clustering:

Preferred:

```text
Leiden
```

Fallback:

```text
Louvain
```

---

# Leiden vs Louvain

Both are graph clustering algorithms.

Goal:

```text
Find densely connected communities.
```

Node:

```text
Article
```

Edge:

```text
Similarity
```

Louvain:

* Maximizes modularity
* Fast
* No k required

Leiden:

* Improved Louvain
* Produces better connected communities
* Preferred for production

Current recommendation:

```text
Use Leiden if available.
```

---

# Story Identity Is More Important Than Topic Similarity

Critical realization:

```text
Story ≠ Topic
```

Example:

```text
NEET paper leak
SSC paper leak
```

Same topic:

```text
Exam scams
```

Different stories.

The system must cluster by:

```text
Event Identity
```

not:

```text
Topic Similarity
```

---

# Benchmark Dataset Design

Dataset size:

```text
50–60 articles
```

Target:

```text
7–8 story clusters
```

Approx:

```text
5–7 articles per cluster
```

---

# Current Story Clusters

## NEET Scam

Purpose:

* Same event
* Different reporting styles
* Political framing

---

## SSC Rigging

Purpose:

```text
Same Topic
Different Event
```

Must not merge with NEET.

---

## SSC GD Constable Controversy

Additional exam-related ambiguity.

---

## Bengal Elections — CRPF Deployment

Most valuable benchmark cluster.

Contains:

* Neutral reporting
* TMC framing
* BJP framing
* Political interpretation
* Institutional reporting

Tests:

```text
Event Identity Under Narrative Variation
```

---

## Andhra Pradesh Tech Investments

Tests:

* Economic reporting
* Government announcements

---

## Andhra Pradesh Child Allowance Policy

Tests:

```text
Same Entities
Different Event
```

Overlap:

* AP Government
* Chandrababu Naidu

Should not merge with Tech Investment cluster.

---

## Iran / India / Gold

Currently weakest cluster.

Needs additional articles.

Should contain:

* Geopolitical reporting
* Economic effects
* Gold market impact
* India response

---

# Benchmark Categories Retained

Current evaluation dataset should include:

### Same Event, Different Wording

Tests paraphrase robustness.

---

### Same Event, Conflicting Framing

Example:

```text
TMC vs BJP explanations for CRPF deployment
```

Tests narrative robustness.

---

### Same Topic, Different Event

Example:

```text
NEET vs SSC
```

Tests false merge resistance.

---

### Same Entities, Different Event

Example:

```text
AP Tech Investments
vs
AP Child Policy
```

Tests entity ambiguity.

---

### Opinion vs Report

Opinion articles reference the same event but focus on interpretation rather than reporting.

Used to evaluate semantic confusion.

---

### Short vs Long Form

Tests embedding robustness.

---

### Different Article Focus

Example:

Multiple articles covering the same event but emphasizing:

* Politics
* Economy
* Security
* Reactions

Tests semantic drift.

---

# Categories Explicitly Deferred

Not part of current PoC:

* Event evolution
* Timeline continuity
* Duplicate wire copies
* Live updates
* Story versioning
* Cross-batch reconciliation

These are future problems.

---

# Evaluation Metrics

Primary metrics:

### Pairwise Precision

Question:

```text
Of all article pairs clustered together,
how many truly belong together?
```

Measures:

```text
False Merges
```

Most important early metric.

---

### Pairwise Recall

Question:

```text
Of all true same-story pairs,
how many were discovered?
```

Measures:

```text
Missed Connections
```

---

### Cluster Purity

Question:

```text
How clean is a cluster?
```

Measures:

```text
Overmerging
```

---

### Cluster Completeness

Question:

```text
Did the system gather all articles of a story?
```

Measures:

```text
Oversplitting
```

---

# Strategic Conclusion

Headlyn is currently positioned as:

```text
Story Consolidation Platform
```

rather than:

```text
Story Tracking Platform
```

The immediate objective is to validate:

```text
Can a graph-based clustering pipeline correctly recover story identity from a batch of news articles?
```

If clustering quality is sufficient, canonical summaries become the primary feed objects and future personalization systems will operate at the story level rather than the article level.
