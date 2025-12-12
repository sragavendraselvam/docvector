"""Vector database abstraction layer."""

from typing import cast
from docvector.core import settings
from .base import (
    BaseVectorDB,
    IVectorStore,
    SearchResult,
    VectorRecord,
    VectorSearchResult,
)
from .chroma_client import ChromaVectorDB
from .qdrant_client import QdrantVectorDB

def get_vector_db() -> IVectorStore:
    """Get vector database instance based on configuration.

    The vector database selection depends on the MCP mode:
    - local mode: ChromaDB (fully local, no external dependencies)
    - cloud/hybrid mode: Qdrant (cloud-based or self-hosted)

    Returns:
        Configured IVectorStore implementation

    Note:
        ChromaDB is used for local mode as it's embedded and requires no
        separate server process. Qdrant is used for cloud/hybrid modes
        as it supports remote connections and scales better for production.
    """
    if settings.mcp_mode == "local":
        # Local mode: Use ChromaDB with configured persist directory
        return ChromaVectorDB(persist_directory=settings.chroma_persist_directory)
    else:
        # Cloud/Hybrid mode: Use Qdrant
        # Note: QdrantVectorDB currently uses legacy BaseVectorDB interface
        # TODO: Create QdrantVectorStore implementing IVectorStore
        return cast(IVectorStore, QdrantVectorDB())

__all__ = [
    # New interface (DOC-8)
    "IVectorStore",
    "VectorRecord",
    "VectorSearchResult",
    "get_vector_db",
    # Legacy interface (for backward compatibility)
    "BaseVectorDB",
    "SearchResult",
    # Implementations
    "ChromaVectorDB",
    "QdrantVectorDB",
]
