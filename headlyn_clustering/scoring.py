"""Precision-oriented scoring of retrieved article candidate pairs."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .models import (
    Article,
    CandidateEvidence,
    CandidateSet,
    ChunkEmbeddingRecord,
    Dataset,
    EmbeddingRecord,
    EmbeddingSet,
    PairFeatures,
    PairScoringConfig,
    ScoredCandidate,
    ScoredCandidateSet,
)


class PairScoringError(ValueError):
    """Raised when pair scoring inputs or configuration are invalid."""


def score_candidates(
    dataset: Dataset,
    embeddings: EmbeddingSet,
    candidates: CandidateSet,
    config: PairScoringConfig = PairScoringConfig(),
) -> ScoredCandidateSet:
    """Calculate pair features, scores, and acceptance decisions."""

    articles, records = _validate_inputs(dataset, embeddings, candidates, config)
    chunks_by_article: dict[str, tuple[ChunkEmbeddingRecord, ...]] = {}
    grouped: dict[str, list[ChunkEmbeddingRecord]] = {}
    for chunk in embeddings.chunks:
        grouped.setdefault(chunk.article_id, []).append(chunk)
    chunks_by_article = {
        article_id: tuple(sorted(chunks, key=lambda item: item.chunk_id))
        for article_id, chunks in grouped.items()
    }
    scored = tuple(
        _score_pair(
            pair.article_a,
            pair.article_b,
            pair.evidence,
            articles,
            records,
            chunks_by_article,
            config,
        )
        for pair in candidates.pairs
    )
    result = ScoredCandidateSet(
        article_ids=candidates.article_ids,
        candidates=scored,
        config=config,
    )
    _write_artifacts(result)
    return result


def _validate_inputs(
    dataset: Dataset,
    embeddings: EmbeddingSet,
    candidates: CandidateSet,
    config: PairScoringConfig,
) -> tuple[dict[str, Article], dict[str, EmbeddingRecord]]:
    weights = (
        config.semantic_weight,
        config.lexical_weight,
        config.title_weight,
        config.entity_weight,
        config.temporal_weight,
    )
    if not all(math.isfinite(weight) and weight >= 0 for weight in weights):
        raise PairScoringError("scoring weights must be finite and non-negative")
    if not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise PairScoringError("scoring weights must sum to 1.0")
    if not 0 <= config.acceptance_threshold <= 1:
        raise PairScoringError("acceptance threshold must be between 0 and 1")
    if not math.isfinite(config.temporal_decay_hours) or config.temporal_decay_hours <= 0:
        raise PairScoringError("temporal decay must be positive and finite")
    if not math.isfinite(config.same_source_penalty) or not 0 <= config.same_source_penalty <= 1:
        raise PairScoringError("same-source penalty must be between 0 and 1")
    if not math.isfinite(config.chunk_match_threshold) or not 0 <= config.chunk_match_threshold <= 1:
        raise PairScoringError("chunk match threshold must be between 0 and 1")

    articles = {article.article_id: article for article in dataset.articles}
    records = {record.article_id: record for record in embeddings.records}
    if len(articles) != len(dataset.articles) or len(records) != len(embeddings.records):
        raise PairScoringError("dataset and embedding article IDs must be unique")
    if set(candidates.article_ids) != set(articles) or set(candidates.article_ids) != set(records):
        raise PairScoringError("dataset, embeddings, and candidates must contain the same article IDs")
    for pair in candidates.pairs:
        if pair.article_a == pair.article_b:
            raise PairScoringError("candidate pairs must not contain self-pairs")
        if pair.article_a not in articles or pair.article_b not in articles:
            raise PairScoringError("candidate pair references an unknown article")
    return articles, records


def _score_pair(
    article_a_id: str,
    article_b_id: str,
    evidence: tuple[CandidateEvidence, ...],
    articles: dict[str, Article],
    records: dict[str, EmbeddingRecord],
    chunks_by_article: dict[str, tuple[ChunkEmbeddingRecord, ...]],
    config: PairScoringConfig,
) -> ScoredCandidate:
    article_a = articles[article_a_id]
    article_b = articles[article_b_id]
    record_a = records[article_a_id]
    record_b = records[article_b_id]
    source_relationship = "same_source" if article_a.source == article_b.source else "different_source"
    source_penalty = (
        config.same_source_penalty if source_relationship == "same_source" else 0.0
    )
    global_semantic_similarity = _cosine(record_a.vector, record_b.vector)
    chunk_features = _chunk_semantic_features(
        chunks_by_article.get(article_a_id, ()),
        chunks_by_article.get(article_b_id, ()),
        config.chunk_match_threshold,
    )
    if chunk_features[4] == 0 and not chunks_by_article.get(article_a_id) and not chunks_by_article.get(article_b_id):
        chunk_features = (
            global_semantic_similarity,
            global_semantic_similarity,
            global_semantic_similarity,
            global_semantic_similarity,
            1,
        )
    features = PairFeatures(
        semantic_similarity=0.85 * chunk_features[0] + 0.15 * global_semantic_similarity,
        lexical_similarity=_sparse_cosine(record_a.lexical_weights, record_b.lexical_weights),
        title_similarity=_sparse_cosine(
            record_a.title_representation,
            record_b.title_representation,
        ),
        entity_overlap=_entity_overlap(record_a, record_b),
        temporal_similarity=_temporal_similarity(article_a, article_b, config),
        source_relationship=source_relationship,
        source_penalty=source_penalty,
        global_semantic_similarity=global_semantic_similarity,
        chunk_semantic_similarity=chunk_features[0],
        chunk_best_match=chunk_features[1],
        chunk_top2_mean=chunk_features[2],
        chunk_bidirectional_coverage=chunk_features[3],
        chunk_match_count=chunk_features[4],
    )
    weighted_score = (
        config.semantic_weight * features.semantic_similarity
        + config.lexical_weight * features.lexical_similarity
        + config.title_weight * features.title_similarity
        + config.entity_weight * features.entity_overlap
        + config.temporal_weight * features.temporal_similarity
        - features.source_penalty
    )
    final_score = min(1.0, max(0.0, weighted_score))
    accepted = final_score >= config.acceptance_threshold
    return ScoredCandidate(
        article_a=article_a_id,
        article_b=article_b_id,
        features=features,
        final_score=final_score,
        accepted=accepted,
        rejection_reason=None if accepted else "below_threshold",
        retrieval_evidence=evidence,
    )


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = tuple(left)
    right_values = tuple(right)
    if len(left_values) != len(right_values):
        raise PairScoringError("semantic vectors must have matching dimensions")
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return _bounded_similarity(
        sum(a * b for a, b in zip(left_values, right_values)) / (left_norm * right_norm)
    )


def _sparse_cosine(
    left: Iterable[tuple[str, float]],
    right: Iterable[tuple[str, float]],
) -> float:
    left_map = dict(left)
    right_map = dict(right)
    left_norm = math.sqrt(sum(value * value for value in left_map.values()))
    right_norm = math.sqrt(sum(value * value for value in right_map.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(value * right_map.get(token, 0.0) for token, value in left_map.items())
    return _bounded_similarity(dot / (left_norm * right_norm))


def _entity_overlap(left: EmbeddingRecord, right: EmbeddingRecord) -> float:
    left_keys = {(entity.canonical.casefold(), entity.type) for entity in left.entities}
    right_keys = {(entity.canonical.casefold(), entity.type) for entity in right.entities}
    union = left_keys | right_keys
    return len(left_keys & right_keys) / len(union) if union else 0.0


def _chunk_semantic_features(
    left: tuple[ChunkEmbeddingRecord, ...],
    right: tuple[ChunkEmbeddingRecord, ...],
    match_threshold: float,
) -> tuple[float, float, float, float, int]:
    """Aggregate chunk similarities without averaging unrelated chunk pairs."""

    if not left or not right:
        return 0.0, 0.0, 0.0, 0.0, 0
    matrix = [
        [_cosine(left_chunk.vector, right_chunk.vector) for right_chunk in right]
        for left_chunk in left
    ]
    row_best = [max(row) for row in matrix]
    column_best = [max(matrix[row_index][column_index] for row_index in range(len(left))) for column_index in range(len(right))]
    all_scores = sorted((score for row in matrix for score in row), reverse=True)
    best = all_scores[0]
    top2_mean = sum(all_scores[: min(2, len(all_scores))]) / min(2, len(all_scores))
    coverage_values = sorted(row_best + column_best, reverse=True)[:6]
    bidirectional_coverage = sum(coverage_values) / len(coverage_values)
    match_count = sum(score >= match_threshold for score in row_best) + sum(
        score >= match_threshold for score in column_best
    )

    lead_scores = [
        matrix[left_index][right_index]
        for left_index, left_chunk in enumerate(left)
        if left_chunk.chunk_id.endswith(":title") or left_chunk.chunk_id.endswith(":lead")
        for right_index, right_chunk in enumerate(right)
        if right_chunk.chunk_id.endswith(":title") or right_chunk.chunk_id.endswith(":lead")
    ]
    lead_similarity = max(lead_scores) if lead_scores else best
    aggregate = (
        0.35 * best
        + 0.30 * top2_mean
        + 0.20 * bidirectional_coverage
        + 0.15 * lead_similarity
    )
    return aggregate, best, top2_mean, bidirectional_coverage, match_count


def _temporal_similarity(
    left: Article,
    right: Article,
    config: PairScoringConfig,
) -> float:
    hours = abs((left.published_at - right.published_at).total_seconds()) / 3600.0
    return math.exp(-hours / config.temporal_decay_hours)


def _bounded_similarity(value: float) -> float:
    if not math.isfinite(value):
        raise PairScoringError("pair feature calculation produced a non-finite value")
    return min(1.0, max(0.0, value))


def _write_artifacts(scored_set: ScoredCandidateSet) -> None:
    artifact_dir = Path(scored_set.config.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    rejection_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    scores: list[float] = []
    lines: list[str] = []
    for candidate in scored_set.candidates:
        features = candidate.features
        if candidate.rejection_reason:
            rejection_counts[candidate.rejection_reason] += 1
        source_counts[features.source_relationship] += 1
        scores.append(candidate.final_score)
        lines.append(
            json.dumps(
                {
                    "article_a": candidate.article_a,
                    "article_b": candidate.article_b,
                    "features": {
                        "semantic_similarity": features.semantic_similarity,
                        "lexical_similarity": features.lexical_similarity,
                        "title_similarity": features.title_similarity,
                        "entity_overlap": features.entity_overlap,
                        "temporal_similarity": features.temporal_similarity,
                        "source_relationship": features.source_relationship,
                        "source_penalty": features.source_penalty,
                        "global_semantic_similarity": features.global_semantic_similarity,
                        "chunk_semantic_similarity": features.chunk_semantic_similarity,
                        "chunk_best_match": features.chunk_best_match,
                        "chunk_top2_mean": features.chunk_top2_mean,
                        "chunk_bidirectional_coverage": features.chunk_bidirectional_coverage,
                        "chunk_match_count": features.chunk_match_count,
                    },
                    "final_score": candidate.final_score,
                    "accepted": candidate.accepted,
                    "rejection_reason": candidate.rejection_reason,
                    "retrieval_evidence": [
                        {
                            "query_article_id": evidence.query_article_id,
                            "candidate_article_id": evidence.candidate_article_id,
                            "retriever": evidence.retriever,
                            "rank": evidence.rank,
                            "score": evidence.score,
                            "query_chunk_id": evidence.query_chunk_id,
                            "candidate_chunk_id": evidence.candidate_chunk_id,
                        }
                        for evidence in candidate.retrieval_evidence
                    ],
                },
                sort_keys=True,
            )
        )
    summary = {
        "version": scored_set.config.version,
        "article_count": len(scored_set.article_ids),
        "candidate_count": len(scored_set.candidates),
        "accepted_count": sum(candidate.accepted for candidate in scored_set.candidates),
        "rejected_count": sum(not candidate.accepted for candidate in scored_set.candidates),
        "acceptance_threshold": scored_set.config.acceptance_threshold,
        "chunk_match_threshold": scored_set.config.chunk_match_threshold,
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "score_mean": sum(scores) / len(scores) if scores else None,
        "rejections_by_reason": dict(sorted(rejection_counts.items())),
        "pairs_by_source_relationship": dict(sorted(source_counts.items())),
    }
    _atomic_write(
        artifact_dir / "scored_candidates.jsonl",
        "\n".join(lines) + ("\n" if lines else ""),
    )
    _atomic_write(
        artifact_dir / "scoring_summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
