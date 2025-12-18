"""Vector database abstraction layer.

This module provides a unified interface for vector database operations,
supporting both local (ChromaDB) and cloud/hybrid (Qdrant) deployments.

The factory pattern allows seamless switching between implementations
based on configuration without changing application code.
"""

import os
from typing import Optional

from docvector.core import get_logger, settings

from .base import (
    BaseVectorDB,
    IVectorStore,
    SearchResult,
    VectorRecord,
    VectorSearchResult,
)
from .chroma_client import ChromaVectorDB
from .qdrant_client import QdrantVectorDB

logger = get_logger(__name__)


class VectorDBConfigurationError(Exception):
    """Raised when vector database configuration is invalid."""

    pass


def _validate_chroma_config() -> None:
    """Validate ChromaDB configuration.

    Raises:
        VectorDBConfigurationError: If configuration is invalid
    """
    persist_dir = settings.chroma_persist_directory

    if not persist_dir:
        raise VectorDBConfigurationError(
            "ChromaDB persist directory not configured. "
            "Set DOCVECTOR_CHROMA_PERSIST_DIRECTORY environment variable."
        )

    # Check parent directory is writable
    parent_dir = os.path.dirname(persist_dir) or "."
    if os.path.exists(parent_dir) and not os.access(parent_dir, os.W_OK):
        raise VectorDBConfigurationError(
            f"ChromaDB persist directory parent '{parent_dir}' is not writable. "
            "Check file permissions."
        )

    logger.debug(
        "ChromaDB configuration validated",
        persist_directory=persist_dir,
    )


def _validate_qdrant_config() -> None:
    """Validate Qdrant configuration.

    Raises:
        VectorDBConfigurationError: If configuration is invalid
    """
    # Check if cloud or self-hosted
    if settings.qdrant_url and settings.qdrant_api_key:
        # Cloud mode: Both URL and API key required
        logger.debug(
            "Qdrant cloud configuration detected",
            url=settings.qdrant_url[:50] + "..." if len(settings.qdrant_url) > 50 else settings.qdrant_url,
            has_api_key=bool(settings.qdrant_api_key),
        )
    elif settings.qdrant_url:
        # URL without API key
        raise VectorDBConfigurationError(
            "Qdrant URL provided but API key missing. "
            "Set DOCVECTOR_QDRANT_API_KEY for cloud deployment, "
            "or use DOCVECTOR_QDRANT_HOST for self-hosted."
        )
    elif settings.qdrant_api_key:
        # API key without URL
        raise VectorDBConfigurationError(
            "Qdrant API key provided but URL missing. "
            "Set DOCVECTOR_QDRANT_URL for cloud deployment."
        )
    else:
        # Self-hosted mode: Validate host and port
        if not settings.qdrant_host:
            raise VectorDBConfigurationError(
                "Qdrant host not configured. "
                "Set DOCVECTOR_QDRANT_HOST or DOCVECTOR_QDRANT_URL."
            )

        if not isinstance(settings.qdrant_port, int) or settings.qdrant_port <= 0:
            raise VectorDBConfigurationError(
                f"Invalid Qdrant port: {settings.qdrant_port}. "
                "Must be a positive integer."
            )

        logger.debug(
            "Qdrant self-hosted configuration detected",
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            use_grpc=settings.qdrant_use_grpc,
        )


def get_vector_db(mode: Optional[str] = None) -> IVectorStore:
    """Get vector database instance based on configuration.

    This factory function returns the appropriate vector database implementation
    based on the configured mode (local, cloud, or hybrid). It validates the
    configuration before creating instances and provides helpful error messages.

    The vector database selection depends on the MCP mode:
    - **local**: ChromaDB - Fully local, embedded, zero external dependencies.
                 Perfect for development, privacy-focused, and air-gapped deployments.
    - **cloud**: Qdrant - Cloud-based managed service with high scalability.
                 Best for production deployments with millions of vectors.
    - **hybrid**: Qdrant - Self-hosted or cloud, with local docs + cloud Q&A.
                  Recommended for most production use cases.

    Args:
        mode: Override the configured mode. If None, uses settings.mcp_mode.
              Valid values: "local", "cloud", "hybrid"

    Returns:
        IVectorStore: Configured vector database instance (ChromaVectorDB or QdrantVectorDB)

    Raises:
        VectorDBConfigurationError: If configuration is invalid or required settings are missing
        ValueError: If mode is not "local", "cloud", or "hybrid"

    Examples:
        >>> # Use configured mode (from environment or defaults)
        >>> db = get_vector_db()
        >>> await db.initialize()

        >>> # Override mode explicitly
        >>> db = get_vector_db(mode="local")
        >>> await db.initialize()

        >>> # Get cloud instance with explicit configuration
        >>> import os
        >>> os.environ["DOCVECTOR_MCP_MODE"] = "cloud"
        >>> os.environ["DOCVECTOR_QDRANT_URL"] = "https://xxx.cloud.qdrant.io"
        >>> os.environ["DOCVECTOR_QDRANT_API_KEY"] = "your-key"
        >>> db = get_vector_db()

    Note:
        The returned instance is not initialized. You must call `await db.initialize()`
        before using it. This allows for proper async initialization and error handling.

        Configuration is validated before instance creation. Any configuration
        errors will raise VectorDBConfigurationError with helpful error messages.

    Integration:
        This function is used throughout DocVector:
        - MCP server: `db = get_vector_db()` at startup
        - Search service: Uses factory to get appropriate backend
        - Ingestion service: Stores embeddings using returned instance
        - CLI commands: `docvector init` creates necessary directories
    """
    # Determine which mode to use
    effective_mode = mode or settings.mcp_mode

    # Validate mode
    valid_modes = ["local", "cloud", "hybrid"]
    if effective_mode not in valid_modes:
        raise ValueError(
            f"Invalid vector database mode: '{effective_mode}'. "
            f"Must be one of: {', '.join(valid_modes)}"
        )

    logger.info(
        "Initializing vector database",
        mode=effective_mode,
        source="override" if mode else "settings",
    )

    try:
        if effective_mode == "local":
            # Local mode: Use ChromaDB with configured persist directory
            logger.info(
                "Using ChromaDB for local mode",
                features="embedded, offline, zero-dependency",
            )

            # Validate configuration
            _validate_chroma_config()

            # Create instance
            instance = ChromaVectorDB(persist_directory=settings.chroma_persist_directory)

            logger.info(
                "ChromaDB instance created",
                persist_directory=settings.chroma_persist_directory,
            )

            return instance

        else:
            # Cloud/Hybrid mode: Use Qdrant
            logger.info(
                "Using Qdrant for cloud/hybrid mode",
                features="scalable, distributed, production-ready",
            )

            # Validate configuration
            _validate_qdrant_config()

            # Create instance with configuration
            if settings.qdrant_url and settings.qdrant_api_key:
                # Cloud deployment
                instance = QdrantVectorDB(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key,
                )
                logger.info(
                    "Qdrant cloud instance created",
                    deployment="cloud",
                    url=settings.qdrant_url[:50] + "..." if len(settings.qdrant_url) > 50 else settings.qdrant_url,
                )
            else:
                # Self-hosted deployment
                instance = QdrantVectorDB(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    grpc_port=settings.qdrant_grpc_port if settings.qdrant_use_grpc else None,
                    use_grpc=settings.qdrant_use_grpc,
                )
                logger.info(
                    "Qdrant self-hosted instance created",
                    deployment="self-hosted",
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    protocol="grpc" if settings.qdrant_use_grpc else "http",
                )

            return instance

    except VectorDBConfigurationError:
        # Re-raise configuration errors as-is
        raise
    except Exception as e:
        # Wrap unexpected errors
        logger.error(
            "Failed to create vector database instance",
            mode=effective_mode,
            error=str(e),
        )
        raise VectorDBConfigurationError(
            f"Failed to create vector database for mode '{effective_mode}': {e}"
        ) from e

__all__ = [
    # New interface (DOC-8)
    "IVectorStore",
    "VectorRecord",
    "VectorSearchResult",
    "get_vector_db",
    "VectorDBConfigurationError",
    # Legacy interface (for backward compatibility)
    "BaseVectorDB",
    "SearchResult",
    # Implementations
    "ChromaVectorDB",
    "QdrantVectorDB",
]
