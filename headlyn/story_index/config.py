from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class StoryIndexConfig:
    """Connection and schema settings for the persistent story index."""

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "headlyn-stories"
    qdrant_timeout_seconds: int = 10
    sqlite_path: Path = Path("data/story_index.sqlite")
    vector_size: int = 1024
    document_embedding_collection: str = "headlyn-document-embeddings"
    document_embedding_vector_size: int = 1024
    dense_limit: int = 20
    lexical_limit: int = 20

    @classmethod
    def from_env(cls) -> "StoryIndexConfig":
        """Load Qdrant and SQLite settings from the default dotenv search path."""
        load_dotenv()
        return cls(
            qdrant_url=os.environ.get("HEADLYN_QDRANT_URL", cls.qdrant_url),
            qdrant_api_key=os.environ.get("HEADLYN_QDRANT_API_KEY"),
            qdrant_collection=os.environ.get("HEADLYN_QDRANT_COLLECTION", cls.qdrant_collection),
            qdrant_timeout_seconds=int(os.environ.get("HEADLYN_QDRANT_TIMEOUT_SECONDS", cls.qdrant_timeout_seconds)),
            sqlite_path=Path(os.environ.get("HEADLYN_STORY_INDEX_DB", str(cls.sqlite_path))),
            vector_size=int(os.environ.get("HEADLYN_STORY_VECTOR_SIZE", cls.vector_size)),
            document_embedding_collection=os.environ.get(
                "HEADLYN_DOCUMENT_EMBEDDING_COLLECTION",
                cls.document_embedding_collection,
            ),
            document_embedding_vector_size=int(
                os.environ.get(
                    "HEADLYN_DOCUMENT_EMBEDDING_VECTOR_SIZE",
                    cls.document_embedding_vector_size,
                )
            ),
            dense_limit=int(os.environ.get("HEADLYN_DENSE_LIMIT", cls.dense_limit)),
            lexical_limit=int(os.environ.get("HEADLYN_LEXICAL_LIMIT", cls.lexical_limit)),
        )

    def validate(self) -> None:
        """Validate connection, schema, and retrieval settings."""
        if not self.qdrant_url.strip():
            raise ValueError("qdrant_url is required")
        if not self.qdrant_collection.strip():
            raise ValueError("qdrant_collection is required")
        if self.qdrant_timeout_seconds < 1 or self.vector_size < 1 or self.document_embedding_vector_size < 1:
            raise ValueError("timeout and vector_size must be positive")
        if not self.document_embedding_collection.strip():
            raise ValueError("document_embedding_collection is required")
        if self.dense_limit < 1 or self.lexical_limit < 1:
            raise ValueError("retrieval limits must be positive")
