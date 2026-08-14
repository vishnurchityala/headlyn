"""Deterministic hybrid candidate retrieval for article batches."""

from __future__ import annotations

import math
import json
import os
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .models import (
    CandidateEvidence,
    CandidatePair,
    CandidateRetrievalConfig,
    CandidateSet,
    ChunkEmbeddingRecord,
    EmbeddingRecord,
    EmbeddingSet,
)


class CandidateRetrievalError(ValueError):
    """Raised when an embedding set cannot be searched safely."""


RETRIEVERS = ("semantic", "bm25", "title", "entity", "chunk_semantic")


def retrieve_candidates(
    embeddings: EmbeddingSet,
    config: CandidateRetrievalConfig = CandidateRetrievalConfig(),
) -> CandidateSet:
    """Retrieve and deduplicate candidate pairs for every embedded article."""

    records = _validate_embeddings(embeddings, config)
    article_ids = tuple(sorted(record.article_id for record in records))
    if len(records) < 2:
        result = CandidateSet(article_ids=article_ids, pairs=(), config=config)
        _write_artifacts(result)
        return result

    by_id = {record.article_id: record for record in records}
    lexical_index = _build_sparse_index(
        (record.article_id, record.lexical_weights) for record in records
    )
    title_index = _build_sparse_index(
        (record.article_id, record.title_representation) for record in records
    )
    entity_index = _build_entity_index(records)
    chunks_by_article: dict[str, tuple[ChunkEmbeddingRecord, ...]] = defaultdict(tuple)
    chunk_groups: dict[str, list[ChunkEmbeddingRecord]] = defaultdict(list)
    for chunk in embeddings.chunks:
        chunk_groups[chunk.article_id].append(chunk)
    chunks_by_article = {
        article_id: tuple(sorted(chunks, key=lambda item: item.chunk_id))
        for article_id, chunks in chunk_groups.items()
    }
    evidence_by_pair: dict[tuple[str, str], list[CandidateEvidence]] = defaultdict(list)

    for query_id in article_ids:
        query = by_id[query_id]
        retriever_hits = (
            ("semantic", _semantic_hits(query, records, config.top_k, embeddings)),
            ("bm25", _sparse_hits(query, lexical_index, config.top_k, "lexical")),
            ("title", _sparse_hits(query, title_index, config.top_k, "title")),
            ("entity", _entity_hits(query, entity_index, by_id, config.top_k)),
        )
        for retriever, hits in retriever_hits:
            for rank, (candidate_id, score) in enumerate(hits, start=1):
                pair = tuple(sorted((query_id, candidate_id)))
                evidence_by_pair[pair].append(
                    CandidateEvidence(
                        query_article_id=query_id,
                        candidate_article_id=candidate_id,
                        retriever=retriever,
                        rank=rank,
                        score=float(score),
                    )
                )

        for query_chunk in chunks_by_article.get(query_id, ()):
            for rank, (candidate_chunk, score) in enumerate(
                _chunk_hits(query_chunk, embeddings.chunks, config.chunk_top_k),
                start=1,
            ):
                pair = tuple(sorted((query_id, candidate_chunk.article_id)))
                evidence_by_pair[pair].append(
                    CandidateEvidence(
                        query_article_id=query_id,
                        candidate_article_id=candidate_chunk.article_id,
                        retriever="chunk_semantic",
                        rank=rank,
                        score=float(score),
                        query_chunk_id=query_chunk.chunk_id,
                        candidate_chunk_id=candidate_chunk.chunk_id,
                    )
                )

    pairs = tuple(
        CandidatePair(
            article_a=article_a,
            article_b=article_b,
            evidence=_ordered_evidence(evidence, config.max_chunk_evidence_per_pair),
        )
        for (article_a, article_b), evidence in sorted(evidence_by_pair.items())
    )
    result = CandidateSet(article_ids=article_ids, pairs=pairs, config=config)
    _write_artifacts(result)
    return result


def _write_artifacts(candidate_set: CandidateSet) -> None:
    """Write deterministic candidate output and summary files for debugging."""

    artifact_dir = Path(candidate_set.config.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    evidence_count = sum(len(pair.evidence) for pair in candidate_set.pairs)
    retriever_counts: dict[str, int] = {retriever: 0 for retriever in RETRIEVERS}
    query_counts: dict[str, dict[str, int]] = {
        article_id: {retriever: 0 for retriever in RETRIEVERS}
        for article_id in candidate_set.article_ids
    }
    pair_lines: list[str] = []
    for pair in candidate_set.pairs:
        evidence_payload = []
        for evidence in pair.evidence:
            retriever_counts[evidence.retriever] += 1
            query_counts[evidence.query_article_id][evidence.retriever] += 1
            evidence_payload.append(
                {
                    "query_article_id": evidence.query_article_id,
                    "candidate_article_id": evidence.candidate_article_id,
                    "retriever": evidence.retriever,
                    "rank": evidence.rank,
                    "score": evidence.score,
                    "query_chunk_id": evidence.query_chunk_id,
                    "candidate_chunk_id": evidence.candidate_chunk_id,
                }
            )
        pair_lines.append(
            json.dumps(
                {
                    "article_a": pair.article_a,
                    "article_b": pair.article_b,
                    "evidence": evidence_payload,
                },
                sort_keys=True,
            )
        )

    summary = {
        "version": candidate_set.config.version,
        "top_k": candidate_set.config.top_k,
        "article_count": len(candidate_set.article_ids),
        "article_ids": list(candidate_set.article_ids),
        "candidate_pair_count": len(candidate_set.pairs),
        "evidence_count": evidence_count,
        "evidence_by_retriever": retriever_counts,
        "evidence_by_query": query_counts,
    }
    _atomic_write(
        artifact_dir / "candidate_pairs.jsonl",
        "\n".join(pair_lines) + ("\n" if pair_lines else ""),
    )
    _atomic_write(
        artifact_dir / "retrieval_summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _validate_embeddings(
    embeddings: EmbeddingSet,
    config: CandidateRetrievalConfig,
) -> tuple[EmbeddingRecord, ...]:
    if config.top_k <= 0:
        raise CandidateRetrievalError("candidate retrieval top_k must be positive")
    if config.chunk_top_k <= 0:
        raise CandidateRetrievalError("chunk retrieval chunk_top_k must be positive")
    if config.max_chunk_evidence_per_pair <= 0:
        raise CandidateRetrievalError("max chunk evidence per pair must be positive")
    if not embeddings.records:
        raise CandidateRetrievalError("cannot retrieve candidates from an empty embedding set")

    records = tuple(embeddings.records)
    ids = [record.article_id for record in records]
    if len(set(ids)) != len(ids):
        raise CandidateRetrievalError("embedding records must have unique article IDs")
    for record in records:
        if len(record.vector) != embeddings.metadata.dimension:
            raise CandidateRetrievalError(
                f"embedding dimension mismatch for article {record.article_id!r}"
            )
        if not all(math.isfinite(value) for value in record.vector):
            raise CandidateRetrievalError(
                f"embedding vector contains a non-finite value for {record.article_id!r}"
            )
        _validate_sparse(record.lexical_weights, record.article_id, "lexical weights")
        _validate_sparse(
            record.title_representation,
            record.article_id,
            "title representation",
        )
    seen_chunks: set[str] = set()
    for chunk in embeddings.chunks:
        if chunk.chunk_id in seen_chunks:
            raise CandidateRetrievalError(f"duplicate chunk ID {chunk.chunk_id!r}")
        seen_chunks.add(chunk.chunk_id)
        if chunk.article_id not in ids or len(chunk.vector) != embeddings.metadata.dimension:
            raise CandidateRetrievalError(f"invalid chunk embedding for {chunk.chunk_id!r}")
        if not all(math.isfinite(value) for value in chunk.vector):
            raise CandidateRetrievalError(f"chunk vector contains a non-finite value for {chunk.chunk_id!r}")
    return records


def _ordered_evidence(
    evidence: list[CandidateEvidence],
    max_chunk_evidence: int,
) -> tuple[CandidateEvidence, ...]:
    chunk_evidence = sorted(
        (item for item in evidence if item.retriever == "chunk_semantic"),
        key=lambda item: (-item.score, item.query_chunk_id or "", item.candidate_chunk_id or ""),
    )[:max_chunk_evidence]
    other_evidence = [item for item in evidence if item.retriever != "chunk_semantic"]
    return tuple(
        sorted(
            (*other_evidence, *chunk_evidence),
            key=lambda item: (
                RETRIEVERS.index(item.retriever),
                item.query_article_id,
                item.candidate_article_id,
                item.rank,
                item.query_chunk_id or "",
                item.candidate_chunk_id or "",
            ),
        )
    )


def _validate_sparse(
    values: Iterable[tuple[str, float]],
    article_id: str,
    name: str,
) -> None:
    seen: set[str] = set()
    for token, weight in values:
        if not token or token in seen or not math.isfinite(weight):
            raise CandidateRetrievalError(
                f"invalid {name} for article {article_id!r}"
            )
        seen.add(token)


def _semantic_hits(
    query: EmbeddingRecord,
    records: tuple[EmbeddingRecord, ...],
    top_k: int,
    embeddings: EmbeddingSet,
) -> tuple[tuple[str, float], ...]:
    query_norm = math.sqrt(sum(value * value for value in query.vector))
    results: list[tuple[str, float]] = []
    for candidate in records:
        if candidate.article_id == query.article_id:
            continue
        candidate_norm = math.sqrt(sum(value * value for value in candidate.vector))
        if query_norm == 0 or candidate_norm == 0:
            score = 0.0
        elif embeddings.metadata.normalized:
            score = sum(a * b for a, b in zip(query.vector, candidate.vector))
        else:
            score = sum(a * b for a, b in zip(query.vector, candidate.vector)) / (
                query_norm * candidate_norm
            )
        results.append((candidate.article_id, score))
    return _rank(results, top_k)


def _chunk_hits(
    query: ChunkEmbeddingRecord,
    chunks: tuple[ChunkEmbeddingRecord, ...],
    top_k: int,
) -> tuple[tuple[ChunkEmbeddingRecord, float], ...]:
    query_norm = math.sqrt(sum(value * value for value in query.vector))
    results: list[tuple[ChunkEmbeddingRecord, float]] = []
    for candidate in chunks:
        if candidate.article_id == query.article_id:
            continue
        candidate_norm = math.sqrt(sum(value * value for value in candidate.vector))
        if query_norm == 0 or candidate_norm == 0:
            score = 0.0
        else:
            score = sum(a * b for a, b in zip(query.vector, candidate.vector)) / (
                query_norm * candidate_norm
            )
        results.append((candidate, score))
    return tuple(
        sorted(results, key=lambda item: (-item[1], item[0].article_id, item[0].chunk_id))[:top_k]
    )


def _build_sparse_index(
    records: Iterable[tuple[str, Iterable[tuple[str, float]]]],
) -> dict[str, tuple[tuple[str, float], ...]]:
    index: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for article_id, values in records:
        for token, weight in values:
            index[token].append((article_id, weight))
    return {token: tuple(values) for token, values in index.items()}


def _sparse_hits(
    query: EmbeddingRecord,
    index: dict[str, tuple[tuple[str, float], ...]],
    top_k: int,
    representation: str,
) -> tuple[tuple[str, float], ...]:
    values = (
        query.lexical_weights
        if representation == "lexical"
        else query.title_representation
    )
    scores: defaultdict[str, float] = defaultdict(float)
    for token, query_weight in values:
        for candidate_id, candidate_weight in index.get(token, ()):
            if candidate_id != query.article_id:
                scores[candidate_id] += query_weight * candidate_weight
    return _rank(
        ((candidate_id, score) for candidate_id, score in scores.items() if score > 0),
        top_k,
    )


def _build_entity_index(
    records: tuple[EmbeddingRecord, ...],
) -> dict[tuple[str, str], tuple[str, ...]]:
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in records:
        for key in _entity_keys(record):
            index[key].append(record.article_id)
    return {key: tuple(article_ids) for key, article_ids in index.items()}


def _entity_hits(
    query: EmbeddingRecord,
    index: dict[tuple[str, str], tuple[str, ...]],
    by_id: dict[str, EmbeddingRecord],
    top_k: int,
) -> tuple[tuple[str, float], ...]:
    query_keys = _entity_keys(query)
    shared: defaultdict[str, int] = defaultdict(int)
    for key in query_keys:
        for candidate_id in index.get(key, ()):
            if candidate_id != query.article_id:
                shared[candidate_id] += 1
    results = []
    for candidate_id, intersection in shared.items():
        union = len(query_keys | _entity_keys(by_id[candidate_id]))
        if union:
            results.append((candidate_id, intersection / union))
    return _rank(results, top_k)


def _entity_keys(record: EmbeddingRecord) -> set[tuple[str, str]]:
    return {
        (entity.canonical.casefold(), entity.type)
        for entity in record.entities
    }


def _rank(
    values: Iterable[tuple[str, float]],
    top_k: int,
) -> tuple[tuple[str, float], ...]:
    ranked = sorted(values, key=lambda item: (-item[1], item[0]))
    return tuple(ranked[:top_k])
