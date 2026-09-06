from __future__ import annotations

import uuid
from typing import Protocol, Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from headlyn.document_processing.canonical import document_fingerprint
from headlyn.document_processing.models import EncodedDocument, EntityExtraction, ExtractedEntity, StoryDocument
from headlyn.story_index.config import StoryIndexConfig


class DocumentVectorStore(Protocol):
    """Persist and retrieve reusable document-level embedding features."""

    def initialize(self, vector_size: int) -> None:
        ...

    def health_check(self) -> None:
        ...

    def get_many(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        max_length: int,
    ) -> dict[str, EncodedDocument]:
        ...

    def upsert(self, encoded: EncodedDocument) -> None:
        ...

    def get_many_entities(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        prompt_version: str,
    ) -> dict[str, EntityExtraction]:
        ...

    def upsert_entity(self, document: StoryDocument, extraction: EntityExtraction) -> None:
        ...


class QdrantDocumentVectorStore(DocumentVectorStore):
    """Store reusable BGE-M3 document vectors in a persistent Qdrant collection."""

    def __init__(self, config: StoryIndexConfig) -> None:
        """Create a Qdrant client using the shared .env connection settings."""
        self.config = config
        self.client = QdrantClient(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            timeout=config.qdrant_timeout_seconds,
        )

    def initialize(self, vector_size: int) -> None:
        """Create the stable embedding collection or validate its vector schema."""
        try:
            try:
                info = self.client.get_collection(self.config.document_embedding_collection)
            except Exception as exc:
                if not self._looks_missing(exc):
                    raise
                self.client.create_collection(
                    collection_name=self.config.document_embedding_collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
                return
            existing_size, existing_distance = document_vector_schema(info)
            if existing_size != vector_size or existing_distance.upper() != "COSINE":
                raise ValueError(
                    f"collection {self.config.document_embedding_collection} has vector schema "
                    f"size={existing_size}, distance={existing_distance}; "
                    f"expected size={vector_size}, distance=COSINE"
                )
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"unable to initialize document embedding collection: {exc}") from exc

    def health_check(self) -> None:
        """Verify that the persistent document embedding collection is readable."""
        try:
            self.client.get_collection(self.config.document_embedding_collection)
        except Exception as exc:
            raise RuntimeError(f"document embedding Qdrant health check failed: {exc}") from exc

    def get_many(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        max_length: int,
    ) -> dict[str, EncodedDocument]:
        """Retrieve only cache entries matching document and model fingerprints."""
        if not documents:
            return {}
        try:
            points = self.client.retrieve(
                collection_name=self.config.document_embedding_collection,
                ids=[document_point_id(document.document_id) for document in documents],
                with_payload=True,
                with_vectors=True,
            )
            by_point_id = {str(point.id): point for point in points}
            results: dict[str, EncodedDocument] = {}
            for document in documents:
                point = by_point_id.get(document_point_id(document.document_id))
                encoded = decode_point(point) if point is not None else None
                if encoded is None:
                    continue
                if encoded.input_fingerprint != document_fingerprint(document):
                    continue
                if encoded.model_name != model_name or encoded.max_length != max_length:
                    continue
                results[document.document_id] = encoded
            return results
        except Exception as exc:
            raise RuntimeError(f"document embedding Qdrant lookup failed: {exc}") from exc

    def upsert(self, encoded: EncodedDocument) -> None:
        """Persist one dense vector and complete encoded feature payload."""
        try:
            self.client.upsert(
                collection_name=self.config.document_embedding_collection,
                points=[
                    PointStruct(
                        id=document_point_id(encoded.document_id),
                        vector=list(encoded.dense_vector),
                        payload={
                            "document_id": encoded.document_id,
                            "input_fingerprint": encoded.input_fingerprint,
                            "canonical_text": encoded.canonical_text,
                            "sparse_weights": dict(encoded.sparse_weights),
                            "model_name": encoded.model_name,
                            "max_length": encoded.max_length,
                        },
                    )
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"document embedding Qdrant upsert failed for {encoded.document_id}: {exc}") from exc

    def get_many_entities(
        self,
        documents: Sequence[StoryDocument],
        *,
        model_name: str,
        prompt_version: str,
    ) -> dict[str, EntityExtraction]:
        """Retrieve compatible successful entity results from document payloads."""
        if not documents:
            return {}
        try:
            points = self.client.retrieve(
                collection_name=self.config.document_embedding_collection,
                ids=[document_point_id(document.document_id) for document in documents],
                with_payload=True,
                with_vectors=False,
            )
            by_point_id = {str(point.id): point for point in points}
            results: dict[str, EntityExtraction] = {}
            for document in documents:
                point = by_point_id.get(document_point_id(document.document_id))
                payload = (getattr(point, "payload", {}) or {}) if point is not None else {}
                cached = decode_entity_payload(payload)
                if cached is None:
                    continue
                if cached.input_fingerprint != document_fingerprint(document):
                    continue
                if cached.model != model_name or cached.prompt_version != prompt_version:
                    continue
                results[document.document_id] = cached
            return results
        except Exception as exc:
            raise RuntimeError(f"document entity cache lookup failed: {exc}") from exc

    def upsert_entity(self, document: StoryDocument, extraction: EntityExtraction) -> None:
        """Persist one successful entity result without rewriting its vector."""
        if extraction.status != "ok":
            return
        try:
            self.client.set_payload(
                collection_name=self.config.document_embedding_collection,
                points=[document_point_id(document.document_id)],
                payload={"entity_extraction": extraction.as_dict()},
            )
        except Exception as exc:
            raise RuntimeError(f"document entity cache upsert failed for {document.document_id}: {exc}") from exc

    @staticmethod
    def _looks_missing(error: Exception) -> bool:
        """Detect a missing Qdrant collection across server response variants."""
        text = str(error).lower()
        return "404" in text or "not found" in text or "doesn't exist" in text


def document_point_id(document_id: str) -> str:
    """Create a stable Qdrant point ID for one document ID."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"headlyn:document:{document_id}"))


def document_vector_schema(info: object) -> tuple[int, str]:
    """Extract vector size and distance from Qdrant collection metadata."""
    config = getattr(info, "config", info)
    params = getattr(config, "params", config)
    vectors = getattr(params, "vectors", params)
    size = getattr(vectors, "size", None)
    distance = getattr(vectors, "distance", None)
    if isinstance(vectors, dict):
        size = vectors.get("size", size)
        distance = vectors.get("distance", distance)
    if size is None or distance is None:
        raise ValueError("unable to inspect document vector schema")
    return int(size), str(getattr(distance, "value", distance))


def decode_point(point: object) -> EncodedDocument | None:
    """Convert one Qdrant point into encoded features or reject malformed payloads."""
    payload = getattr(point, "payload", {}) or {}
    vector = getattr(point, "vector", None)
    required = {"document_id", "input_fingerprint", "canonical_text", "model_name", "max_length"}
    if vector is None or not required.issubset(payload):
        return None
    try:
        return EncodedDocument(
            document_id=str(payload["document_id"]),
            input_fingerprint=str(payload["input_fingerprint"]),
            canonical_text=str(payload["canonical_text"]),
            dense_vector=tuple(float(value) for value in vector),
            sparse_weights={str(key): float(value) for key, value in dict(payload.get("sparse_weights", {})).items()},
            model_name=str(payload["model_name"]),
            max_length=int(payload["max_length"]),
        )
    except (TypeError, ValueError):
        return None


def decode_entity_payload(payload: object) -> EntityExtraction | None:
    """Decode a cached entity payload while rejecting malformed records."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("entity_extraction")
    if not isinstance(value, dict) or value.get("status") != "ok":
        return None
    raw_entities = value.get("entities", [])
    if not isinstance(raw_entities, list):
        return None
    try:
        entities = tuple(
            ExtractedEntity(
                text=str(item["text"]),
                canonical_name=str(item["canonical_name"]),
                entity_type=str(item["type"]),
                role=str(item["role"]),
            )
            for item in raw_entities
            if isinstance(item, dict)
        )
        return EntityExtraction(
            document_id=str(value["document_id"]),
            input_fingerprint=str(value["input_fingerprint"]),
            model=str(value["model"]),
            prompt_version=str(value["prompt_version"]),
            status="ok",
            entities=entities,
        )
    except (KeyError, TypeError, ValueError):
        return None
