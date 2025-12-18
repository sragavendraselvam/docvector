"""ChromaDB vector database implementation for local mode."""

import asyncio
import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings

from docvector.core import get_logger, settings

from .base import IVectorStore, VectorRecord, VectorSearchResult

logger = get_logger(__name__)


class ChromaVectorDB(IVectorStore):
    """ChromaDB implementation of IVectorStore for local mode.

    ChromaDB is a lightweight, embedded vector database perfect for local deployments
    and air-gapped environments. It provides persistent storage with no external
    dependencies beyond the filesystem.

    Features:
    - Fully local and private (no cloud connectivity required)
    - Automatic persistence to disk
    - Support for cosine, L2, and inner product distance metrics
    - Metadata filtering with where clauses
    - Efficient HNSW index for fast similarity search

    Note:
        ChromaDB returns distances, not similarity scores. This implementation
        converts distances to scores in the 0-1 range where higher is better:
        - Cosine: score = 1 - distance (distance in [0,2] for normalized vectors)
        - L2: score = 1 / (1 + distance) (asymptotic normalization)
        - IP: score = max(0, distance) (assumes positive inner products)
    """

    def __init__(self, persist_directory: Optional[str] = None):
        """Initialize ChromaDB client.

        Args:
            persist_directory: Directory for persistent storage. If None, uses
                settings.chroma_persist_directory (default: ./data/chroma)
        """
        self.persist_directory = persist_directory or settings.chroma_persist_directory
        self._client: Optional[ClientAPI] = None
        
    async def initialize(self) -> None:
        """Initialize ChromaDB client connection and setup.

        Creates the persist directory if it doesn't exist and initializes
        the ChromaDB PersistentClient with appropriate settings.

        Raises:
            ConnectionError: If ChromaDB initialization fails

        Note:
            This method is idempotent and can be safely called multiple times.
            Telemetry is disabled for privacy.
        """
        try:
            await asyncio.to_thread(self._init_sync)
            logger.info(
                "ChromaDB initialized successfully",
                persist_directory=self.persist_directory,
            )
        except Exception as e:
            logger.error("Failed to initialize ChromaDB", error=str(e))
            raise ConnectionError(f"Failed to initialize ChromaDB: {e}")

    def _init_sync(self) -> None:
        """Synchronous initialization helper.

        Creates the persistent storage directory and initializes the ChromaDB
        client with privacy-preserving settings.

        Note:
            This is an internal method called by initialize() via asyncio.to_thread().
        """
        os.makedirs(self.persist_directory, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(
                anonymized_telemetry=False,  # Disable telemetry for privacy
                allow_reset=True,  # Allow database reset for testing
            ),
        )

    async def close(self) -> None:
        """Close ChromaDB connection and cleanup resources.

        This method releases the ChromaDB client reference. The persistent
        data remains on disk and can be reloaded on next initialization.

        Note:
            This method is idempotent (safe to call multiple times).
            ChromaDB PersistentClient doesn't have an explicit close method,
            so we simply clear the reference to allow garbage collection.
        """
        if self._client:
            logger.info("Closing ChromaDB connection")
        self._client = None
        
    async def create_collection(
        self,
        name: str,
        dimension: int,
        distance_metric: str = "cosine",
    ) -> None:
        """Create a new ChromaDB collection.

        Args:
            name: Collection name (must be unique)
            dimension: Vector dimension (stored in metadata for reference)
            distance_metric: Distance function - "cosine", "euclidean", or "dot"

        Raises:
            ValueError: If collection already exists
            RuntimeError: If collection creation fails

        Note:
            ChromaDB uses "hnsw:space" metadata to specify distance metric:
            - "cosine": Cosine distance (1 - cosine similarity)
            - "l2": Euclidean/L2 distance
            - "ip": Inner product (negative dot product)
        """
        if not self._client:
            await self.initialize()

        try:
            # Map our standard metric names to ChromaDB's HNSW space names
            metric_map = {
                "cosine": "cosine",
                "euclidean": "l2",
                "dot": "ip",
            }
            mapped_metric = metric_map.get(distance_metric.lower(), "cosine")

            logger.info(
                "Creating ChromaDB collection",
                collection=name,
                dimension=dimension,
                distance_metric=distance_metric,
                chroma_space=mapped_metric,
            )

            # Store dimension in metadata for get_collection_info
            await asyncio.to_thread(
                self._client.create_collection,
                name=name,
                metadata={
                    "hnsw:space": mapped_metric,
                    "dimension": dimension,
                },
            )

            logger.info("ChromaDB collection created successfully", collection=name)

        except ValueError as e:
            # ChromaDB raises ValueError if collection exists
            if "Collection" in str(e) and "already exists" in str(e):
                logger.warning("Collection already exists", collection=name)
                raise ValueError(f"Collection {name} already exists")
            raise RuntimeError(f"Failed to create collection {name}: {e}")
        except Exception as e:
            logger.error("Failed to create collection", collection=name, error=str(e))
            raise RuntimeError(f"Failed to create collection {name}: {e}")

    async def delete_collection(self, name: str) -> None:
        """Delete a collection and all its vectors.

        Args:
            name: Collection name to delete

        Raises:
            ValueError: If collection does not exist
            RuntimeError: If deletion fails

        Warning:
            This operation is irreversible! All vectors and metadata will be permanently deleted.
        """
        if not self._client:
            await self.initialize()

        try:
            logger.info("Deleting ChromaDB collection", collection=name)
            await asyncio.to_thread(self._client.delete_collection, name=name)
            logger.info("Collection deleted successfully", collection=name)
        except ValueError:
            raise ValueError(f"Collection {name} does not exist")
        except Exception as e:
            logger.error("Failed to delete collection", collection=name, error=str(e))
            raise RuntimeError(f"Failed to delete collection {name}: {e}")

    async def collection_exists(self, name: str) -> bool:
        """Check if a collection exists.

        Args:
            name: Collection name to check

        Returns:
            True if collection exists, False otherwise
        """
        if not self._client:
            await self.initialize()

        try:
            # ChromaDB doesn't have explicit exists method, use list_collections
            collections = await asyncio.to_thread(self._client.list_collections)
            # list_collections returns list of Collection objects in newer versions
            return any(c.name == name for c in collections)
        except Exception:
            return False

    async def get_collection_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get collection metadata and statistics.

        Args:
            name: Collection name

        Returns:
            Dictionary with collection info or None if collection doesn't exist
        """
        if not self._client:
            await self.initialize()

        try:
            collection = await asyncio.to_thread(self._client.get_collection, name=name)
            if not collection:
                return None

            count = await asyncio.to_thread(collection.count)

            # Try to get dimension from metadata (set during create_collection)
            dimension = collection.metadata.get("dimension")

            # If not in metadata, peek at first vector
            if dimension is None and count > 0:
                result = await asyncio.to_thread(collection.peek, limit=1)
                if result and result.get("embeddings") and len(result["embeddings"]) > 0:
                    dimension = len(result["embeddings"][0])

            # Map ChromaDB space back to standard metric names
            chroma_space = collection.metadata.get("hnsw:space", "cosine")
            metric_reverse_map = {
                "cosine": "cosine",
                "l2": "euclidean",
                "ip": "dot",
            }
            distance_metric = metric_reverse_map.get(chroma_space, chroma_space)

            return {
                "name": name,
                "dimension": dimension or 0,
                "vector_count": count,
                "distance_metric": distance_metric,
            }
        except ValueError:
            return None
        except Exception as e:
            logger.error("Error getting collection info", collection=name, error=str(e))
            return None

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
            All vectors in a batch must have the same dimension as the collection.
        """
        if not self._client:
            await self.initialize()

        try:
            coll = await asyncio.to_thread(self._client.get_collection, name=collection)

            ids = [r.id for r in records]
            embeddings = [r.vector for r in records]
            metadatas = [r.payload for r in records]

            logger.debug(
                "Upserting records to ChromaDB",
                collection=collection,
                count=len(records),
            )

            await asyncio.to_thread(
                coll.upsert, ids=ids, embeddings=embeddings, metadatas=metadatas
            )

            logger.debug("Upsert completed", collection=collection, count=len(records))
            return len(records)
        except ValueError:
            raise ValueError(f"Collection {collection} does not exist")
        except Exception as e:
            logger.error("Failed to upsert records", collection=collection, error=str(e))
            raise RuntimeError(f"Failed to upsert records: {e}")

    def _distance_to_score(self, distance: float, metric: str) -> float:
        """Convert distance to similarity score (0-1 range, higher is better).

        Args:
            distance: Distance value from ChromaDB
            metric: Distance metric used ("cosine", "l2", or "ip")

        Returns:
            Similarity score in 0-1 range

        Note:
            - Cosine: distance is in [0, 2] for normalized vectors, score = 1 - distance/2
            - L2: distance is in [0, inf), score = 1 / (1 + distance)
            - IP: distance is negative dot product, score = max(0, min(1, -distance))
        """
        if metric == "cosine":
            # Cosine distance is 1 - cosine_similarity
            # For normalized vectors, distance is in [0, 2]
            # Score should be 1 when distance is 0, and 0 when distance is 2
            return max(0.0, min(1.0, 1.0 - (distance / 2.0)))
        elif metric == "l2":
            # L2 distance can be arbitrarily large
            # Use 1/(1+d) to map to [0,1] range
            return 1.0 / (1.0 + distance)
        elif metric == "ip":
            # Inner product space: ChromaDB returns negative dot product
            # For normalized vectors with positive components, this should be negative
            # Score = -distance (to get back the dot product)
            # Clamp to [0, 1] range
            return max(0.0, min(1.0, -distance))
        else:
            # Unknown metric, assume cosine-like behavior
            return max(0.0, min(1.0, 1.0 - distance))

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
            query_vector: Query embedding
            limit: Maximum number of results
            filters: Optional metadata filters (ChromaDB where clause)
            score_threshold: Minimum similarity score (0-1 range)

        Returns:
            List of VectorSearchResult ordered by similarity (highest first)

        Note:
            ChromaDB returns distances which are converted to similarity scores.
            Filtering is applied after conversion, so score_threshold works
            correctly regardless of the underlying distance metric.
        """
        if not self._client:
            await self.initialize()

        try:
            coll = await asyncio.to_thread(self._client.get_collection, name=collection)

            # Get the distance metric for proper distance-to-score conversion
            chroma_space = coll.metadata.get("hnsw:space", "cosine")

            # ChromaDB expects where clause for metadata filtering
            where = filters if filters else None

            logger.debug(
                "Searching ChromaDB collection",
                collection=collection,
                limit=limit,
                has_filters=filters is not None,
                metric=chroma_space,
            )

            results = await asyncio.to_thread(
                coll.query,
                query_embeddings=[query_vector],
                n_results=limit,
                where=where,
                include=["metadatas", "distances"],  # Don't include embeddings by default for performance
            )

            # ChromaDB returns batch results (list of lists)
            if not results["ids"] or len(results["ids"]) == 0:
                return []

            ids = results["ids"][0]
            distances = results["distances"][0] if results.get("distances") else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []

            search_results = []
            for i, id_ in enumerate(ids):
                # Convert distance to similarity score
                distance = distances[i] if i < len(distances) else 0.0
                score = self._distance_to_score(distance, chroma_space)

                # Apply score threshold
                if score_threshold is not None and score < score_threshold:
                    continue

                search_results.append(
                    VectorSearchResult(
                        id=id_,
                        score=score,
                        payload=metadatas[i] if i < len(metadatas) else {},
                        vector=None,  # Don't return vectors by default for performance
                    )
                )

            logger.debug(
                "Search completed",
                collection=collection,
                results=len(search_results),
            )

            return search_results

        except ValueError:
            raise ValueError(f"Collection {collection} does not exist")
        except Exception as e:
            logger.error("Search failed", collection=collection, error=str(e))
            raise RuntimeError(f"Search failed: {e}")

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
            filters: Optional metadata filters for deletion (ChromaDB where clause)

        Returns:
            Count of vectors deleted

        Raises:
            ValueError: If neither ids nor filters provided, or collection doesn't exist
            RuntimeError: If deletion fails

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
        if not self._client:
            await self.initialize()

        if ids is None and filters is None:
            raise ValueError("Either ids or filters must be provided")

        try:
            coll = await asyncio.to_thread(self._client.get_collection, name=collection)

            # ChromaDB delete doesn't return count, so we calculate it manually
            pre_count = await asyncio.to_thread(coll.count)

            logger.debug(
                "Deleting vectors from ChromaDB",
                collection=collection,
                has_ids=ids is not None,
                has_filters=filters is not None,
            )

            await asyncio.to_thread(coll.delete, ids=ids, where=filters)

            post_count = await asyncio.to_thread(coll.count)
            deleted_count = pre_count - post_count

            logger.debug("Delete completed", collection=collection, deleted=deleted_count)
            return deleted_count

        except ValueError:
            raise ValueError(f"Collection {collection} does not exist")
        except Exception as e:
            logger.error("Failed to delete", collection=collection, error=str(e))
            raise RuntimeError(f"Failed to delete: {e}")

    async def count(self, collection: str) -> int:
        """Count vectors in collection.

        Args:
            collection: Collection name

        Returns:
            Total number of vectors in the collection

        Raises:
            ValueError: If collection doesn't exist
            RuntimeError: If count operation fails
        """
        if not self._client:
            await self.initialize()

        try:
            coll = await asyncio.to_thread(self._client.get_collection, name=collection)
            count = await asyncio.to_thread(coll.count)
            return count
        except ValueError:
            raise ValueError(f"Collection {collection} does not exist")
        except Exception as e:
            logger.error("Failed to count", collection=collection, error=str(e))
            raise RuntimeError(f"Failed to count: {e}")
