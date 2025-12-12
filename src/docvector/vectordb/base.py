"""Base interface for vector databases."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class VectorSearchResult:
    """Result from vector similarity search.

    Attributes:
        id: Unique identifier for the vector
        score: Similarity score (0-1 range for cosine similarity, higher is more similar)
        payload: Metadata dictionary stored with the vector
        vector: Optional actual vector embedding (not always returned for performance)
    """

    id: str
    score: float
    payload: Dict[str, Any]
    vector: Optional[List[float]] = None


@dataclass
class VectorRecord:
    """Record to store in vector database.

    Attributes:
        id: Unique identifier for the vector
        vector: Vector embedding (list of floats)
        payload: Metadata dictionary to store with the vector
    """

    id: str
    vector: List[float]
    payload: Dict[str, Any]


class IVectorStore(ABC):
    """Abstract interface for vector database operations.

    This interface enables swapping between different vector database implementations
    (ChromaDB for local mode, Qdrant for cloud mode) without changing application code.

    All methods are async to support both sync and async implementations.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize connection and setup.

        This method should:
        - Establish database connection
        - Verify database is accessible
        - Perform any necessary setup or configuration

        Raises:
            ConnectionError: If connection cannot be established
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection and cleanup resources.

        This method should:
        - Close all open connections
        - Release any held resources
        - Cleanup temporary files if any

        Should be idempotent (safe to call multiple times).
        """
        pass

    @abstractmethod
    async def create_collection(
        self,
        name: str,
        dimension: int,
        distance_metric: str = "cosine",
    ) -> None:
        """Create a new collection/index.

        Args:
            name: Collection name (must be unique)
            dimension: Vector dimension (must match embedding model output)
            distance_metric: Distance function - "cosine", "euclidean", or "dot"

        Raises:
            ValueError: If collection already exists or invalid parameters
            RuntimeError: If collection creation fails

        Note:
            - Cosine: Best for normalized embeddings (range 0-1)
            - Euclidean (L2): Best for absolute distance
            - Dot product: Best for non-normalized embeddings
        """
        pass

    @abstractmethod
    async def delete_collection(self, name: str) -> None:
        """Delete a collection and all its vectors.

        Args:
            name: Collection name to delete

        Raises:
            ValueError: If collection does not exist

        Warning:
            This operation is irreversible!
        """
        pass

    @abstractmethod
    async def collection_exists(self, name: str) -> bool:
        """Check if a collection exists.

        Args:
            name: Collection name to check

        Returns:
            True if collection exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_collection_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get collection metadata.

        Args:
            name: Collection name

        Returns:
            Dictionary with collection info including:
            - dimension: Vector dimension
            - vector_count: Number of vectors
            - distance_metric: Distance function used
            Returns None if collection doesn't exist

        Example:
            {
                "name": "documents",
                "dimension": 384,
                "vector_count": 1523,
                "distance_metric": "cosine"
            }
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        collection: str,
        records: List[VectorRecord],
    ) -> int:
        """Insert or update vectors.

        If a record with the same ID exists, it will be updated.
        Otherwise, a new record will be inserted.

        Args:
            collection: Collection name
            records: List of VectorRecord objects to upsert

        Returns:
            Count of records successfully upserted

        Raises:
            ValueError: If collection doesn't exist or invalid data
            RuntimeError: If upsert operation fails

        Note:
            - All vectors in a batch must have the same dimension
            - Large batches may be split internally for performance
        """
        pass

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[VectorSearchResult]:
        """Search for similar vectors.

        Args:
            collection: Collection to search
            query_vector: Query embedding to find similar vectors for
            limit: Maximum number of results to return (default: 10)
            filters: Optional metadata filters (e.g., {"source": "react", "type": "docs"})
            score_threshold: Minimum similarity score (0-1 range for cosine)

        Returns:
            List of VectorSearchResult ordered by similarity (highest first)

        Raises:
            ValueError: If collection doesn't exist or invalid parameters

        Filter format example:
            {
                "source": "react",           # Exact match
                "version": {"$gte": "18.0"}  # Greater than or equal
            }

        Note:
            Filter syntax may vary between implementations. Use simple
            equality filters for maximum portability.
        """
        pass

    @abstractmethod
    async def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete vectors by ID or filter.

        Either ids or filters must be provided (or both).

        Args:
            collection: Collection name
            ids: Optional list of vector IDs to delete
            filters: Optional metadata filters for deletion

        Returns:
            Count of vectors deleted

        Raises:
            ValueError: If neither ids nor filters provided, or collection doesn't exist

        Example:
            # Delete by IDs
            await store.delete(collection="docs", ids=["vec1", "vec2"])

            # Delete by filter
            await store.delete(collection="docs", filters={"outdated": True})

            # Delete by both
            await store.delete(
                collection="docs",
                ids=["vec1"],
                filters={"source": "deprecated"}
            )
        """
        pass

    @abstractmethod
    async def count(self, collection: str) -> int:
        """Count vectors in collection.

        Args:
            collection: Collection name

        Returns:
            Total number of vectors in the collection

        Raises:
            ValueError: If collection doesn't exist
        """
        pass


# Legacy interface for backward compatibility
class SearchResult:
    """Search result from vector database (legacy class)."""

    def __init__(
        self,
        id: str,
        score: float,
        payload: Dict,
        vector: Optional[List[float]] = None,
    ):
        self.id = id
        self.score = score
        self.payload = payload
        self.vector = vector

    def __repr__(self) -> str:
        return f"<SearchResult(id={self.id}, score={self.score:.4f})>"


class BaseVectorDB(ABC):
    """Abstract base class for vector database implementations (legacy class)."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the vector database connection and create collections if needed."""
        pass

    @abstractmethod
    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> None:
        """
        Create a new collection.

        Args:
            collection_name: Name of the collection
            vector_size: Dimension of vectors
            distance: Distance metric (Cosine, Euclidean, Dot)
        """
        pass

    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        pass

    @abstractmethod
    async def upsert(
        self,
        collection_name: str,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict],
    ) -> None:
        """
        Insert or update vectors.

        Args:
            collection_name: Name of the collection
            ids: List of point IDs
            vectors: List of vector embeddings
            payloads: List of metadata payloads
        """
        pass

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        filter: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """
        Search for similar vectors.

        Args:
            collection_name: Name of the collection
            query_vector: Query vector embedding
            limit: Maximum number of results
            filter: Filter conditions
            score_threshold: Minimum similarity score

        Returns:
            List of search results
        """
        pass

    @abstractmethod
    async def delete(
        self,
        collection_name: str,
        ids: List[str],
    ) -> None:
        """
        Delete vectors by IDs.

        Args:
            collection_name: Name of the collection
            ids: List of point IDs to delete
        """
        pass

    @abstractmethod
    async def delete_by_filter(
        self,
        collection_name: str,
        filter: Dict,
    ) -> None:
        """
        Delete vectors by filter.

        Args:
            collection_name: Name of the collection
            filter: Filter conditions
        """
        pass

    @abstractmethod
    async def get(
        self,
        collection_name: str,
        ids: List[str],
    ) -> List[Dict]:
        """
        Get vectors by IDs.

        Args:
            collection_name: Name of the collection
            ids: List of point IDs

        Returns:
            List of points with vectors and payloads
        """
        pass

    @abstractmethod
    async def count(
        self,
        collection_name: str,
        filter: Optional[Dict] = None,
    ) -> int:
        """
        Count vectors in collection.

        Args:
            collection_name: Name of the collection
            filter: Optional filter conditions

        Returns:
            Number of vectors
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection."""
        pass
