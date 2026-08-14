"""Deterministic article chunking for event-focused semantic retrieval."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from .models import Article, ArticleChunk, Dataset, EmbeddingConfig


TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)?")


def chunk_dataset(
    dataset: Dataset,
    config: EmbeddingConfig,
) -> tuple[ArticleChunk, ...]:
    """Create and artifact-log deterministic chunks for every article."""

    if config.chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be positive")
    if not 0 <= config.chunk_overlap_tokens < config.chunk_size_tokens:
        raise ValueError("chunk_overlap_tokens must be within the chunk size")
    if config.max_chunks_per_article <= 0:
        raise ValueError("max_chunks_per_article must be positive")

    chunks = tuple(
        chunk
        for article in dataset.articles
        for chunk in chunk_article(article, config)
    )
    write_chunk_artifacts(chunks, dataset, config.chunk_artifact_dir)
    return chunks


def chunk_article(article: Article, config: EmbeddingConfig) -> tuple[ArticleChunk, ...]:
    """Build title, lead, and sliding-window body chunks for one article."""

    chunks: list[ArticleChunk] = []
    if config.max_chunks_per_article >= 1 and article.title.strip():
        chunks.append(
            ArticleChunk(
                article_id=article.article_id,
                chunk_id=f"{article.article_id}:title",
                chunk_type="title",
                text=article.title,
                paragraph_start=-1,
                paragraph_end=-1,
                token_count=len(_tokens(article.title)),
            )
        )

    if config.max_chunks_per_article >= 2:
        lead_text = "\n\n".join(
            value for value in (article.title, article.description, article.paragraphs[0] if article.paragraphs else "")
            if value.strip()
        )
        lead_words = lead_text.split()
        lead_words = lead_words[: config.chunk_size_tokens]
        if lead_words:
            chunks.append(
                ArticleChunk(
                    article_id=article.article_id,
                    chunk_id=f"{article.article_id}:lead",
                    chunk_type="lead",
                    text=" ".join(lead_words),
                    paragraph_start=0 if article.paragraphs else -1,
                    paragraph_end=0 if article.paragraphs else -1,
                    token_count=len(_tokens(" ".join(lead_words))),
                )
            )

    remaining = config.max_chunks_per_article - len(chunks)
    if remaining <= 0:
        return tuple(chunks)

    words: list[tuple[str, int]] = []
    for paragraph_index, paragraph in enumerate(article.paragraphs):
        words.extend((word, paragraph_index) for word in paragraph.split())
    if not words:
        return tuple(chunks)

    step = config.chunk_size_tokens - config.chunk_overlap_tokens
    start = 0
    body_index = 0
    while start < len(words) and body_index < remaining:
        window = words[start : start + config.chunk_size_tokens]
        if not window:
            break
        text = " ".join(word for word, _ in window).strip()
        chunks.append(
            ArticleChunk(
                article_id=article.article_id,
                chunk_id=f"{article.article_id}:body-{body_index:03d}",
                chunk_type="body",
                text=text,
                paragraph_start=window[0][1],
                paragraph_end=window[-1][1],
                token_count=len(_tokens(text)),
            )
        )
        body_index += 1
        if start + config.chunk_size_tokens >= len(words):
            break
        start += step
    return tuple(chunks)


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(TOKEN_RE.findall(text.lower()))


def write_chunk_artifacts(
    chunks: tuple[ArticleChunk, ...],
    dataset: Dataset,
    artifact_dir: Path,
) -> None:
    """Write inspectable chunk records and a deterministic chunking summary."""

    artifact_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "article_id": chunk.article_id,
                "chunk_id": chunk.chunk_id,
                "chunk_type": chunk.chunk_type,
                "text": chunk.text,
                "paragraph_start": chunk.paragraph_start,
                "paragraph_end": chunk.paragraph_end,
                "token_count": chunk.token_count,
            },
            sort_keys=True,
        )
        for chunk in chunks
    ]
    counts = Counter(chunk.chunk_type for chunk in chunks)
    per_article = Counter(chunk.article_id for chunk in chunks)
    summary = {
        "article_count": len(dataset.articles),
        "chunk_count": len(chunks),
        "chunks_by_type": dict(sorted(counts.items())),
        "chunks_per_article": dict(sorted(per_article.items())),
    }
    _atomic_write(artifact_dir / "article_chunks.jsonl", "\n".join(lines) + ("\n" if lines else ""))
    _atomic_write(artifact_dir / "chunking_summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n")


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
