### Algorithm
```
RSS ingestion
→ article extraction and normalization
    • parse feed items
    • extract title, description, body, source, URL, timestamp
    • canonicalize URLs
    • clean boilerplate and duplicate text
    • generate article_id
    • extract entities, keywords, tags
    • build recall_text

→ embedding generation
    • embed title + description + clean_text
    • cache using input hash and model metadata
    • store one embedding per article

→ hybrid candidate retrieval
    • ANN semantic retrieval (top-k nearest neighbors)
    • BM25/TF-IDF lexical retrieval
    • title similarity retrieval
    • entity-based retrieval
    • union candidate pairs with provenance tracking

→ pairwise similarity scoring
    • semantic similarity
    • lexical similarity
    • title similarity
    • entity overlap
    • temporal similarity
    • source penalty
    • compute final edge weight
    • apply precision guardrails

→ similarity graph construction
    • node = article
    • edge = accepted candidate pair
    • weight = story similarity score
    • retain only high-confidence edges
    • store accepted and rejected edges

→ Leiden/Louvain clustering
    • weighted undirected graph
    • Leiden as primary algorithm
    • Louvain fallback
    • retain singleton clusters
    • generate stable cluster IDs

→ cluster refinement
    • split weakly connected clusters
    • split mixed-event clusters
    • validate entity cohesion
    • merge only strongly supported clusters

→ cluster grounding context creation
    • aggregate titles
    • descriptions
    • timestamps
    • sources
    • URLs
    • key paragraphs
    • deduplicate repeated content
    • preserve conflicting claims with attribution

→ canonical story generation
    • generate story_id
    • generate canonical headline
    • generate summary
    • attach sources
    • attach member article IDs
    • attach member URLs
    • attach timeline metadata
    • assign review status

→ canonical story storage
    • persist stories
    • persist cluster mappings
    • persist grounding context
    • persist clustering/debug metadata
```