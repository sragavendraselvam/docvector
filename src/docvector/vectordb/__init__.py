"""Vector database abstraction layer."""

from .base import (
    BaseVectorDB,
    IVectorStore,
    SearchResult,
    VectorRecord,
    VectorSearchResult,
)
from .qdrant_client import QdrantVectorDB

__all__ = [
    # New interface (DOC-8)
    "IVectorStore",
    "VectorRecord",
    "VectorSearchResult",
    # Legacy interface (for backward compatibility)
    "BaseVectorDB",
    "SearchResult",
    # Implementations
    "QdrantVectorDB",
]
