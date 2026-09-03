from __future__ import annotations

import uuid
from typing import Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    PayloadSchemaType,
    VectorParams,
)

from .config import StoryIndexConfig
from .models import StoryCandidate, StoryRepresentation


class QdrantStoryStore:
    """Qdrant-backed dense vector store for searchable story centroids."""

    def __init__(self, config: StoryIndexConfig) -> None:
        self.config = config
        self.client = QdrantClient(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            timeout=config.qdrant_timeout_seconds,
        )

    def ensure_collection(self, vector_size: int) -> None:
        """Create the collection once or validate its existing vector schema."""
        try:
            try:
                info = self.client.get_collection(self.config.qdrant_collection)
            except Exception as exc:
                if not self._looks_missing(exc):
                    raise
                self.client.create_collection(
                    collection_name=self.config.qdrant_collection,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
                self._ensure_status_index()
                return
            existing_size, existing_distance = collection_vector_schema(info)
            if existing_size != vector_size or existing_distance.upper() != "COSINE":
                raise ValueError(
                    f"collection {self.config.qdrant_collection} has vector schema "
                    f"size={existing_size}, distance={existing_distance}; expected size={vector_size}, distance=COSINE"
                )
            self._ensure_status_index()
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"unable to initialize Qdrant collection: {exc}") from exc

    def _ensure_status_index(self) -> None:
        """Ensure Qdrant can filter story points by their active/closed status."""
        try:
            self.client.create_payload_index(
                collection_name=self.config.qdrant_collection,
                field_name="status",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:
            # Qdrant may report an existing index as a duplicate on repeated runs.
            message = str(exc).lower()
            if "already exists" not in message and "duplicate" not in message:
                raise

    def health_check(self) -> None:
        """Verify that the configured Qdrant collection can be read."""
        try:
            self.client.get_collection(self.config.qdrant_collection)
        except Exception as exc:
            raise RuntimeError(f"Qdrant health check failed: {exc}") from exc

    def upsert(self, story: StoryRepresentation) -> None:
        """Upsert one normalized story centroid and its searchable payload."""
        try:
            self.client.upsert(
                collection_name=self.config.qdrant_collection,
                points=[
                    PointStruct(
                        id=point_id(story.story_id),
                        vector=list(story.dense_vector),
                        payload=story.payload(),
                    )
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant upsert failed for {story.story_id}: {exc}") from exc

    def search_active(self, vector: Sequence[float], *, limit: int) -> list[StoryCandidate]:
        """Search active story centroids using the installed Qdrant client API."""
        try:
            query_filter = Filter(
                must=[FieldCondition(key="status", match=MatchValue(value="active"))]
            )
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.config.qdrant_collection,
                    query=list(vector),
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                points = response.points
            else:
                points = self.client.search(
                    collection_name=self.config.qdrant_collection,
                    query_vector=list(vector),
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
            candidates: list[StoryCandidate] = []
            for rank, point in enumerate(points, start=1):
                payload = getattr(point, "payload", {}) or {}
                story_id = payload.get("story_id")
                if story_id:
                    candidates.append(
                        StoryCandidate(
                            story_id=str(story_id),
                            score=float(getattr(point, "score", 0.0)),
                            rank=rank,
                            source="dense",
                        )
                    )
            return candidates
        except Exception as exc:
            raise RuntimeError(f"Qdrant search failed: {exc}") from exc

    def mark_status(self, story_id: str, status: str) -> None:
        """Update a story's active/closed payload status."""
        try:
            self.client.set_payload(
                collection_name=self.config.qdrant_collection,
                payload={"status": status},
                points=[point_id(story_id)],
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant status update failed for {story_id}: {exc}") from exc

    def delete(self, story_id: str) -> None:
        """Delete a story point from Qdrant."""
        try:
            self.client.delete(
                collection_name=self.config.qdrant_collection,
                points_selector=[point_id(story_id)],
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant delete failed for {story_id}: {exc}") from exc

    @staticmethod
    def _looks_missing(error: Exception) -> bool:
        """Detect the common Qdrant not-found response without coupling to one SDK type."""
        text = str(error).lower()
        return "404" in text or "not found" in text or "doesn't exist" in text


def point_id(story_id: str) -> str:
    """Create a deterministic UUID accepted by Qdrant for a story ID."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"headlyn:story:{story_id}"))


def collection_vector_schema(info: object) -> tuple[int, str]:
    """Extract vector size and distance from Qdrant SDK response variants."""
    config = getattr(info, "config", info)
    params = getattr(config, "params", config)
    vectors = getattr(params, "vectors", params)
    size = getattr(vectors, "size", None)
    distance = getattr(vectors, "distance", None)
    if isinstance(vectors, dict):
        size = vectors.get("size", size)
        distance = vectors.get("distance", distance)
    if size is None or distance is None:
        raise ValueError("unable to inspect Qdrant vector schema")
    return int(size), str(getattr(distance, "value", distance))
