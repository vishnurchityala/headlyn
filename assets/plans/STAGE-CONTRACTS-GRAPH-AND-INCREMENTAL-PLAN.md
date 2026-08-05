### Algorithm Stages Contracts and Flow
```
The system should have one shared pipeline with two execution modes:

  Article
  → preprocessing
  → embedding + BM25 + entities
  → hybrid candidate retrieval
  → pair scoring
  → graph update
  → clustering
  → story generation

  The difference is whether the graph is being built from scratch or updated with one new article.

  ## Shared stage contracts

  Each stage should produce one model consumed by the next stage:

  Dataset
  → EmbeddingSet
  → CandidateSet
  → ScoredCandidateSet
  → StoryGraph
  → ClusterSet
  → StorySet

  ### 1. Embedding stage

  Input:

  Dataset / Article

  Output per article:

  EmbeddingRecord(
      article_id,
      semantic_vector,
      BM25_weights,
      title_representation,
      entities,
  )

  This stage prepares all retrieval information. Retrieval should not calculate BM25 weights or extract entities.

  ### 2. Hybrid candidate retrieval

  Input:

  EmbeddingSet

  For each search article, run four retrievers:

  semantic ANN
  BM25 lexical
  title similarity
  entity overlap

  Each retriever returns article IDs and raw retrieval scores.

  The stage unions these results into a CandidateSet:

  query_article_id
  candidate_article_id
  retriever_provenance
  retriever_ranks
  retriever_scores

  This stage answers:

  Which articles are worth comparing?

  It does not answer:

  Do these articles belong to the same story?

  ### 3. Pair scoring

  Input:

  CandidateSet

  For every candidate pair, compute comparison features:

  semantic similarity
  BM25 similarity
  title similarity
  entity overlap
  time distance
  source relationship

  Output:

  ScoredCandidateSet

  Each pair receives:

  article_a
  article_b
  feature values
  final score
  accepted/rejected status
  rejection reason

  This is the precision-control stage.

  ### 4. Graph construction

  Input:

  ScoredCandidateSet

  Build:

  node = article
  edge = accepted article pair
  edge weight = pair score
  edge metadata = retrieval and scoring evidence

  Important: candidate edges and accepted graph edges are different.

  CandidateSet → possible relationships
  StoryGraph   → accepted relationships

  ### 5. Clustering

  Input:

  StoryGraph

  Run graph clustering over accepted edges.

  Output:

  ClusterSet

  Each cluster represents one story:

  cluster_id
  member_article_ids
  internal edge statistics
  cluster confidence

  A cluster can contain one article if it has no accepted edges.

  ### 6. Story generation

  Input:

  ClusterSet + ArticleStore

  For every cluster:

  aggregate titles
  aggregate descriptions
  preserve source attribution
  build timeline/context
  generate canonical headline
  generate summary
  attach source articles

  Output:

  StorySet

  Story generation happens after clustering. Generated summaries must never be used as the primary clustering signal.

  ———

  # Task 1: Build the graph from a batch

  For the static evaluation dataset:

  Load all articles
  → generate embeddings and retrieval representations
  → retrieve candidates for every article
  → deduplicate candidate pairs
  → score every candidate pair
  → create accepted graph edges
  → cluster the graph
  → generate one story per cluster

  The graph should not necessarily be fully connected. “All articles are connected to other articles” should mean:

  - every article is represented as a graph node;
  - related articles have edges;
  - unrelated articles remain disconnected or form singleton clusters.

  The graph should be sparse. Connecting every article to every other article would make the graph lose its story boundaries.

  ## Full-batch evaluation

  Evaluate:

  - candidate recall: did retrieval find true same-story pairs?
  - pairwise precision: how many accepted edges are correct?
  - pairwise recall: how many true relationships were accepted?
  - cluster purity: are clusters free from false merges?
  - cluster completeness: did clusters collect all articles from a story?
  - hard-negative false merges;
  - singleton preservation.

  The most important separation is:

  retrieval recall
  vs
  graph-edge precision
  vs
  final cluster quality

  A retrieval miss cannot be fixed by the scorer or clustering stage.

  ———

  # Task 2: Add a new article to the graph

  There are two different cases.

  ## New article inside an unprocessed batch

  This is simple:

  append article to batch
  → generate its embedding/BM25/entities
  → retrieve candidates against batch articles
  → score its candidate pairs
  → add accepted edges
  → run clustering on the batch
  → generate stories

  For a static dataset, rebuilding the batch index is acceptable and safest because BM25 document statistics may change when the corpus changes.

  ## New article after stories already exist

  This is an incremental graph update:

  new article
  → preprocess with same model versions
  → query existing retrieval indexes
  → retrieve candidate articles
  → score new-article pairs
  → add new node and accepted edges
  → recluster affected graph region
  → update affected stories only

  The new article should not be compared against every article if indexes are available. It should query:

  semantic ANN index
  BM25 inverted index
  title index
  entity index

  The existing graph and indexes must therefore be persisted.

  Minimum persistent state:

  ArticleStore
  Embedding/ANN index
  BM25 index
  Title index
  Entity index
  GraphStore
  ClusterStore
  StoryStore

  ## Incremental cluster behavior

  ### New article connects strongly to one cluster

  new article → existing cluster

  Keep the existing cluster/story ID and add the article.

  ### New article has no accepted edges

  Create a singleton cluster and a new story.

  ### New article connects two existing clusters

  The article may be a bridge. Re-evaluate the union of:

  new article
  + cluster A
  + cluster B

  ### New article causes a weak or ambiguous connection

  Do not automatically merge. Mark it for review or leave it as a singleton until stronger evidence exists.

  ## Stable story identity

  Incremental updates require persistent story IDs, which the current batch-only design does not yet have.

  Recommended policy:

  - If an article joins one existing cluster, preserve its story ID.
  - If two clusters merge, create a new story ID and mark the old stories as superseded.
  - If a cluster splits, create new story IDs and mark the old story as superseded.
  - Regenerate canonical story content only for affected clusters.
  - Leave unaffected stories unchanged.

  ———

  # Incremental evaluation

  The current static dataset can evaluate insertion behavior using deterministic holdout scenarios:

  seed graph with existing articles
  → insert one held-out article
  → update graph
  → compare incremental result with full-batch result

  For each inserted article, measure:

  - did retrieval find its true story neighbors?
  - was it assigned to the correct cluster?
  - was it incorrectly attached to a hard-negative cluster?
  - did unrelated clusters remain unchanged?
  - did incremental clustering match a full rebuild?
  - were unaffected story IDs preserved?

  A useful benchmark is leave-one-out insertion:

  For each article:
      build graph without it
      insert it
      compare its assignment with gold labels

  The final algorithm should be tuned against both:

  full-batch clustering quality
  incremental insertion quality

  The current repository implements dataset loading and embedding preparation. The next hybrid retrieval stage should therefore produce a query-oriented CandidateSet,
  with a batch wrapper that runs retrieval for every article and returns deduplicated candidate pairs.
```