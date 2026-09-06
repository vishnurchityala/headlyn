from __future__ import annotations

import math
from typing import Protocol, Sequence

from FlagEmbedding import BGEM3FlagModel

from .canonical import build_canonical_text, document_fingerprint
from .models import EncodedDocument, StoryDocument
from .vector_store import DocumentVectorStore


class DocumentEncoder(Protocol):
    """Encode normalized documents into dense and sparse model features."""

    model_name: str

    def encode(self, documents: Sequence[StoryDocument]) -> list[EncodedDocument]:
        ...


class BgeM3DocumentEncoder:
    """Produce BGE-M3 dense vectors and sparse lexical weights."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 16,
        max_length: int = 512,
        use_fp16: bool = False,
    ) -> None:
        """Validate configuration, load BGE-M3 once, and retain encoder settings."""
        if batch_size < 1 or max_length < 1:
            raise ValueError("batch_size and max_length must be positive")
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        self.use_fp16 = use_fp16
        self.model = BGEM3FlagModel(model_name, use_fp16=use_fp16)

    def encode(self, documents: Sequence[StoryDocument]) -> list[EncodedDocument]:
        """Encode documents in one batch and validate every returned feature."""
        if not documents:
            return []

        # Build the exact canonical strings that will be consumed by BGE-M3.
        texts = [build_canonical_text(document) for document in documents]

        # Request both retrieval representations from the single loaded model.
        output = self.model.encode(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense = output.get("dense_vecs")
        sparse = output.get("lexical_weights")
        if dense is None or sparse is None or len(dense) != len(documents) or len(sparse) != len(documents):
            raise RuntimeError("BGE-M3 returned an unexpected output shape")
        results: list[EncodedDocument] = []

        # Normalize dense vectors and validate sparse weights document by document.
        for document, text, vector, weights in zip(documents, texts, dense, sparse):
            normalized = normalize_vector(vector)
            sparse_weights = {
                str(key): finite_float(value, "sparse weight")
                for key, value in dict(weights).items()
            }
            results.append(
                EncodedDocument(
                    document_id=document.document_id,
                    input_fingerprint=document_fingerprint(document),
                    canonical_text=text,
                    dense_vector=tuple(normalized),
                    sparse_weights=sparse_weights,
                    model_name=self.model_name,
                    max_length=self.max_length,
                )
            )
        return results


class CachedDocumentEncoder:
    """Reuse compatible document features and encode only cache misses."""

    def __init__(
        self,
        encoder: DocumentEncoder,
        vector_store: DocumentVectorStore,
        *,
        vector_size: int = 1024,
        max_length: int = 512,
    ) -> None:
        """Configure a persistent feature cache around an existing encoder."""
        if vector_size < 1 or max_length < 1:
            raise ValueError("vector_size and max_length must be positive")
        self.encoder = encoder
        self.vector_store = vector_store
        self.model_name = encoder.model_name
        self.vector_size = vector_size
        self.max_length = max_length

    def encode(self, documents: Sequence[StoryDocument]) -> list[EncodedDocument]:
        """Load cache hits, encode misses, persist them, and restore input order."""
        if not documents:
            return []

        # Ensure the stable Qdrant collection exists before looking up features.
        self.vector_store.initialize(self.vector_size)
        cached = self.vector_store.get_many(
            documents,
            model_name=self.model_name,
            max_length=self.max_length,
        )
        missing = [document for document in documents if document.document_id not in cached]

        # Invoke BGE-M3 only for documents absent from, or incompatible with, the cache.
        generated = self.encoder.encode(missing) if missing else []
        for encoded in generated:
            self.vector_store.upsert(encoded)
            cached[encoded.document_id] = encoded

        if len(cached) != len(documents):
            missing_ids = [document.document_id for document in documents if document.document_id not in cached]
            raise RuntimeError(f"document embedding cache did not produce features: {missing_ids}")
        return [cached[document.document_id] for document in documents]


def finite_float(value: object, label: str) -> float:
    """Convert a value to a finite float or raise a descriptive validation error."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def normalize_vector(vector: object) -> list[float]:
    """Return an L2-normalized dense vector with finite non-zero values."""
    values = [finite_float(value, "dense vector value") for value in vector]
    if not values:
        raise ValueError("dense vector must not be empty")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ValueError("dense vector must not be zero")
    return [value / norm for value in values]
