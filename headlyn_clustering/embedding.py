"""Sentence Transformer embeddings with deterministic per-article caching."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Sequence
from collections import Counter
from pathlib import Path
from typing import Any

from .models import (
    Article,
    Dataset,
    EmbeddingConfig,
    EmbeddingMetadata,
    EmbeddingRecord,
    EmbeddingSet,
    Entity,
)


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be generated or loaded safely."""


Encoder = Callable[[Sequence[str]], Sequence[Sequence[float]]]
EntityExtractor = Callable[[Sequence[str]], Sequence[Sequence[Entity]]]
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)?")
ENTITY_KEY_RE = re.compile(r"[^a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be by for from in is it of on or that the this to was with".split()
)
ENTITY_TYPES = frozenset({"PERSON", "ORG", "GPE", "LOC", "EVENT", "LAW", "PRODUCT"})
ENTITY_ALIASES = {
    "dk shivakumar": "D.K. Shivakumar",
    "ed": "Enforcement Directorate",
    "sc": "Supreme Court",
}


def generate_embeddings(
    dataset: Dataset,
    config: EmbeddingConfig = EmbeddingConfig(),
    *,
    encoder: Encoder | None = None,
    entity_extractor: EntityExtractor | None = None,
) -> EmbeddingSet:
    """Generate one embedding per article, reusing valid cache entries."""

    if not dataset.articles:
        raise EmbeddingError("cannot embed an empty dataset")
    if config.bm25_k1 <= 0 or not 0 <= config.bm25_b <= 1:
        raise EmbeddingError("BM25 requires k1 > 0 and b between 0 and 1")

    metadata = EmbeddingMetadata(
        model_name=config.model_name,
        revision=config.revision,
        dimension=config.dimension,
        normalized=config.normalize_embeddings,
        input_version=config.input_version,
        lexical_version=config.lexical_version,
        lexical_vocabulary_hash=_lexical_vocabulary_hash(dataset.articles, config),
        bm25_k1=config.bm25_k1,
        bm25_b=config.bm25_b,
        title_weight=config.title_weight,
        description_weight=config.description_weight,
        body_weight=config.body_weight,
        entity_model=config.entity_model,
        entity_version=config.entity_version,
        entity_alias_version=config.entity_alias_version,
        entity_types=config.entity_types,
    )
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    model_hash = _model_hash(metadata)
    inputs = [(article, _embedding_input(article)) for article in dataset.articles]
    lexical_weights = _lexical_weights(dataset.articles, config)
    records: dict[str, EmbeddingRecord] = {}
    misses: list[tuple[Article, str, str, Path]] = []

    for article, text in inputs:
        input_hash = _hash(text)
        cache_path = config.cache_dir / f"{input_hash}-{model_hash}.json"
        record = _read_cache(cache_path, article.article_id, input_hash, metadata)
        if record is None:
            misses.append((article, text, input_hash, cache_path))
        else:
            records[article.article_id] = record

    if misses:
        vectors = (encoder or _load_encoder(config))(
            tuple(text for _, text, _, _ in misses)
        )
        if len(vectors) != len(misses):
            raise EmbeddingError("embedding backend returned the wrong number of vectors")
        texts = tuple(text for _, text, _, _ in misses)
        extracted_entities = (entity_extractor or _load_entity_extractor(config))(texts)
        if len(extracted_entities) != len(misses):
            raise EmbeddingError("entity backend returned the wrong number of results")
        for (article, _, input_hash, cache_path), vector, entities in zip(
            misses, vectors, extracted_entities
        ):
            record = _record(
                article.article_id,
                input_hash,
                vector,
                lexical_weights[article.article_id],
                entities,
                metadata,
            )
            records[article.article_id] = record
            _write_cache(cache_path, record, metadata)

    return EmbeddingSet(
        metadata=metadata,
        records=tuple(records[article.article_id] for article, _ in inputs),
    )


def _embedding_input(article: Article) -> str:
    return "\n\n".join(
        (
            "TITLE:\n" + article.title,
            "DESCRIPTION:\n" + article.description,
            "BODY:\n" + article.clean_text,
        )
    )


def _lexical_weights(
    articles: Sequence[Article],
    config: EmbeddingConfig,
) -> dict[str, tuple[tuple[str, float], ...]]:
    counts: dict[str, dict[str, float]] = {}
    document_frequency: Counter[str] = Counter()
    for article in articles:
        article_counts: dict[str, float] = {}
        for text, field_weight in (
            (article.title, config.title_weight),
            (article.description, config.description_weight),
            (article.clean_text, config.body_weight),
        ):
            for token in _tokens(text):
                article_counts[token] = article_counts.get(token, 0.0) + field_weight
        counts[article.article_id] = article_counts
        document_frequency.update(article_counts)

    article_count = len(articles)
    idf = {
        token: math.log(1.0 + (article_count - frequency + 0.5) / (frequency + 0.5))
        for token, frequency in document_frequency.items()
    }
    average_length = sum(sum(article_counts.values()) for article_counts in counts.values()) / article_count
    result: dict[str, tuple[tuple[str, float], ...]] = {}
    for article_id, article_counts in counts.items():
        document_length = sum(article_counts.values())
        weighted = {
            token: idf[token]
            * (
                (count * (config.bm25_k1 + 1.0))
                / (
                    count
                    + config.bm25_k1
                    * (1.0 - config.bm25_b + config.bm25_b * document_length / average_length)
                )
            )
            for token, count in article_counts.items()
        }
        result[article_id] = tuple(
            (token, value) for token, value in sorted(weighted.items())
        )
    return result


def _lexical_vocabulary_hash(
    articles: Sequence[Article],
    config: EmbeddingConfig,
) -> str:
    document_frequency: Counter[str] = Counter()
    for article in articles:
        terms = set(_tokens(article.title))
        terms.update(_tokens(article.description))
        terms.update(_tokens(article.clean_text))
        document_frequency.update(terms)
    payload = {
        "version": config.lexical_version,
        "k1": config.bm25_k1,
        "b": config.bm25_b,
        "weights": [config.title_weight, config.description_weight, config.body_weight],
        "document_frequency": sorted(document_frequency.items()),
        "document_lengths": sorted(
            (article.article_id, _document_length(article, config))
            for article in articles
        ),
    }
    return _hash(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _document_length(article: Article, config: EmbeddingConfig) -> float:
    return sum(
        weight * len(_tokens(text))
        for text, weight in (
            (article.title, config.title_weight),
            (article.description, config.description_weight),
            (article.clean_text, config.body_weight),
        )
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS)


def _load_encoder(config: EmbeddingConfig) -> Encoder:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "sentence-transformers is required for embedding generation"
        ) from exc

    try:
        model = SentenceTransformer(
            config.model_name,
            device=config.device,
            revision=config.revision,
        )
        dimension = model.get_sentence_embedding_dimension()
    except Exception as exc:
        raise EmbeddingError(f"could not load embedding model {config.model_name!r}") from exc

    if dimension != config.dimension:
        raise EmbeddingError(
            f"model dimension {dimension} does not match configured dimension {config.dimension}"
        )

    def encode(texts: Sequence[str]) -> Sequence[Sequence[float]]:
        try:
            return model.encode(
                list(texts),
                batch_size=config.batch_size,
                convert_to_numpy=True,
                normalize_embeddings=config.normalize_embeddings,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingError("embedding model failed to encode article text") from exc

    return encode


def _load_entity_extractor(config: EmbeddingConfig) -> EntityExtractor:
    try:
        import spacy
    except ImportError as exc:
        raise EmbeddingError("spaCy is required for entity extraction") from exc

    try:
        nlp = spacy.load(config.entity_model)
    except Exception as exc:
        raise EmbeddingError(
            f"could not load entity model {config.entity_model!r}"
        ) from exc

    def extract(texts: Sequence[str]) -> Sequence[Sequence[Entity]]:
        return tuple(
            _entities_from_doc(doc.ents)
            for doc in nlp.pipe(texts, batch_size=config.batch_size)
        )

    return extract


def _entities_from_doc(entities: Sequence[Any]) -> tuple[Entity, ...]:
    result: list[Entity] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        entity_type = getattr(entity, "label_", "")
        surface = str(getattr(entity, "text", "")).strip()
        if entity_type not in ENTITY_TYPES or not surface:
            continue
        canonical = _canonical_entity(surface)
        key = (canonical.casefold(), entity_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(Entity(surface=surface, canonical=canonical, type=entity_type))
    return tuple(result)


def _canonical_entity(surface: str) -> str:
    key = ENTITY_KEY_RE.sub(" ", surface.casefold()).strip()
    return ENTITY_ALIASES.get(key, " ".join(surface.split()).casefold())


def _record(
    article_id: str,
    input_hash: str,
    vector: Sequence[float],
    lexical_weights: Sequence[Sequence[float] | tuple[str, float]],
    entities: Sequence[Entity | dict[str, Any]],
    metadata: EmbeddingMetadata,
) -> EmbeddingRecord:
    values = tuple(float(value) for value in vector)
    if len(values) != metadata.dimension or not all(math.isfinite(value) for value in values):
        raise EmbeddingError(f"invalid embedding vector for article {article_id!r}")
    lexical = tuple(
        (str(token), float(weight))
        for token, weight in lexical_weights
    )
    if not all(token and math.isfinite(weight) for token, weight in lexical):
        raise EmbeddingError(f"invalid lexical weights for article {article_id!r}")
    normalized_entities = tuple(_entity(value) for value in entities)
    return EmbeddingRecord(
        article_id=article_id,
        input_hash=input_hash,
        vector=values,
        lexical_weights=lexical,
        entities=normalized_entities,
    )


def _entity(value: Entity | dict[str, Any]) -> Entity:
    if isinstance(value, Entity):
        entity = value
    elif isinstance(value, dict):
        entity = Entity(
            surface=str(value.get("surface", "")).strip(),
            canonical=str(value.get("canonical", "")).strip(),
            type=str(value.get("type", "")).strip(),
        )
    else:
        raise EmbeddingError("invalid entity record")
    if not entity.surface or not entity.canonical or entity.type not in ENTITY_TYPES:
        raise EmbeddingError("invalid entity record")
    return entity


def _model_hash(metadata: EmbeddingMetadata) -> str:
    return _hash(json.dumps(metadata.__dict__, sort_keys=True, separators=(",", ":")))[:16]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_cache(
    path: Path,
    article_id: str,
    input_hash: str,
    metadata: EmbeddingMetadata,
) -> EmbeddingRecord | None:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict) or (
        payload.get("article_id") != article_id
        or payload.get("input_hash") != input_hash
        or payload.get("metadata") != metadata.__dict__
        or not isinstance(payload.get("vector"), list)
        or not isinstance(payload.get("lexical_weights"), list)
        or not isinstance(payload.get("entities"), list)
    ):
        return None
    try:
        return _record(
            article_id,
            input_hash,
            payload["vector"],
            payload["lexical_weights"],
            payload["entities"],
            metadata,
        )
    except (EmbeddingError, TypeError, ValueError):
        return None


def _write_cache(path: Path, record: EmbeddingRecord, metadata: EmbeddingMetadata) -> None:
    payload = {
        "article_id": record.article_id,
        "input_hash": record.input_hash,
        "metadata": metadata.__dict__,
        "vector": list(record.vector),
        "lexical_weights": [list(item) for item in record.lexical_weights],
        "entities": [entity.__dict__ for entity in record.entities],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
