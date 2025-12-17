"""Qdrant vector database implementation."""

from typing import Dict, List, Optional

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from docvector.core import get_logger, settings

from .base import BaseVectorDB, SearchResult

logger = get_logger(__name__)


class QdrantVectorDB(BaseVectorDB):
    """Qdrant implementation of vector database."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        grpc_port: Optional[int] = None,
        use_grpc: Optional[bool] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize Qdrant client.

        Args:
            host: Qdrant host (for local/docker deployment)
            port: Qdrant HTTP port
            grpc_port: Qdrant gRPC port
            use_grpc: Whether to use gRPC
            url: Qdrant Cloud URL (takes precedence over host/port)
            api_key: Qdrant Cloud API key
        """
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.grpc_port = grpc_port or settings.qdrant_grpc_port
        self.use_grpc = use_grpc if use_grpc is not None else settings.qdrant_use_grpc

        self.client: Optional[AsyncQdrantClient] = None

    async def initialize(self) -> None:
        """Initialize Qdrant client connection."""
        if self.client is not None:
            return

        # Use URL + API key for cloud, otherwise use host/port for local
        if self.url and self.api_key:
            logger.info(
                "Initializing Qdrant Cloud client",
                url=self.url[:50] + "..." if len(self.url) > 50 else self.url,
            )
            self.client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key,
            )
        elif self.use_grpc:
            logger.info(
                "Initializing Qdrant client (gRPC)",
                host=self.host,
                grpc_port=self.grpc_port,
            )
            self.client = AsyncQdrantClient(
                host=self.host,
                grpc_port=self.grpc_port,
                prefer_grpc=True,
            )
        else:
            logger.info(
                "Initializing Qdrant client (HTTP)",
                host=self.host,
                port=self.port,
            )
            self.client = AsyncQdrantClient(
                host=self.host,
                port=self.port,
            )

        logger.info("Qdrant client initialized successfully")

    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> None:
        """Create a new Qdrant collection."""
        await self.initialize()

        # Map distance names
        distance_map = {
            "Cosine": models.Distance.COSINE,
            "Euclidean": models.Distance.EUCLID,
            "Dot": models.Distance.DOT,
        }

        distance_metric = distance_map.get(distance, models.Distance.COSINE)

        logger.info(
            "Creating Qdrant collection",
            collection=collection_name,
            vector_size=vector_size,
            distance=distance,
        )

        try:
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=distance_metric,
                ),
                # Enable on-disk storage for large collections
                # Lower indexing threshold to enable HNSW for smaller collections
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=100,  # Build HNSW index after 100 vectors
                ),
                # HNSW index configuration
                hnsw_config=models.HnswConfigDiff(
                    m=16,  # Number of edges per node
                    ef_construct=100,  # Construction time/accuracy trade-off
                ),
            )
            logger.info("Collection created successfully", collection=collection_name)
        except UnexpectedResponse as e:
            # Handle collection already exists (409 Conflict)
            # Check status_code - it might be on the exception or on e.response
            status_code = getattr(e, 'status_code', None)
            if status_code is None and hasattr(e, 'response'):
                status_code = getattr(e.response, 'status_code', None)

            if status_code == 409 or "already exists" in str(e).lower():
                logger.warning("Collection already exists", collection=collection_name)
            else:
                raise

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists."""
        await self.initialize()

        try:
            await self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    async def upsert(
        self,
        collection_name: str,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict],
    ) -> None:
        """Insert or update vectors in Qdrant."""
        await self.initialize()

        if not ids or not vectors or not payloads:
            logger.warning("Empty data provided to upsert, skipping")
            return

        if len(ids) != len(vectors) != len(payloads):
            raise ValueError("ids, vectors, and payloads must have the same length")

        logger.debug(
            "Upserting vectors",
            collection=collection_name,
            count=len(ids),
        )

        # Create points
        points = [
            models.PointStruct(
                id=id_,
                vector=vector,
                payload=payload,
            )
            for id_, vector, payload in zip(ids, vectors, payloads)
        ]

        # Batch upsert
        await self.client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

        logger.debug("Upsert completed", collection=collection_name, count=len(ids))

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        filter: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """Search for similar vectors in Qdrant."""
        await self.initialize()

        logger.debug(
            "Searching vectors",
            collection=collection_name,
            limit=limit,
            has_filter=filter is not None,
        )

        # Convert filter dict to Qdrant filter
        qdrant_filter = self._build_filter(filter) if filter else None

        # Search using query_points (qdrant-client >= 1.6)
        results = await self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

        # Convert to SearchResult objects
        search_results = [
            SearchResult(
                id=str(result.id),
                score=result.score,
                payload=result.payload or {},
            )
            for result in results.points
        ]

        logger.debug(
            "Search completed",
            collection=collection_name,
            results=len(search_results),
        )

        return search_results

    async def delete(
        self,
        collection_name: str,
        ids: List[str],
    ) -> None:
        """Delete vectors by IDs."""
        await self.initialize()

        if not ids:
            logger.warning("No IDs provided to delete, skipping")
            return

        logger.debug(
            "Deleting vectors",
            collection=collection_name,
            count=len(ids),
        )

        await self.client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(
                points=ids,
            ),
            wait=True,
        )

        logger.debug("Delete completed", collection=collection_name, count=len(ids))

    async def delete_by_filter(
        self,
        collection_name: str,
        filter: Dict,
    ) -> None:
        """Delete vectors by filter."""
        await self.initialize()

        logger.debug(
            "Deleting vectors by filter",
            collection=collection_name,
            filter=filter,
        )

        qdrant_filter = self._build_filter(filter)

        await self.client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=qdrant_filter,
            ),
            wait=True,
        )

        logger.debug("Delete by filter completed", collection=collection_name)

    async def get(
        self,
        collection_name: str,
        ids: List[str],
    ) -> List[Dict]:
        """Get vectors by IDs."""
        await self.initialize()

        if not ids:
            return []

        results = await self.client.retrieve(
            collection_name=collection_name,
            ids=ids,
            with_payload=True,
            with_vectors=True,
        )

        return [
            {
                "id": str(result.id),
                "vector": result.vector,
                "payload": result.payload or {},
            }
            for result in results
        ]

    async def count(
        self,
        collection_name: str,
        filter: Optional[Dict] = None,
    ) -> int:
        """Count vectors in collection."""
        await self.initialize()

        qdrant_filter = self._build_filter(filter) if filter else None

        result = await self.client.count(
            collection_name=collection_name,
            count_filter=qdrant_filter,
        )

        return result.count

    async def close(self) -> None:
        """Close Qdrant client."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Qdrant client closed")

    def _build_filter(self, filter_dict: Dict) -> models.Filter:
        """
        Build Qdrant filter from dictionary.

        Supports:
        - {"field": "value"} - exact match
        - {"field": {"$in": [values]}} - in list
        - {"field": {"$ne": value}} - not equal
        - {"$and": [filters]} - AND condition
        - {"$or": [filters]} - OR condition
        """
        conditions = []

        for key, value in filter_dict.items():
            if key == "$and":
                # AND condition
                sub_filters = [self._build_filter(f) for f in value]
                return models.Filter(must=[f.must[0] if f.must else f for f in sub_filters])

            elif key == "$or":
                # OR condition
                sub_filters = [self._build_filter(f) for f in value]
                return models.Filter(should=[f.must[0] if f.must else f for f in sub_filters])

            elif isinstance(value, dict):
                # Operators
                if "$in" in value:
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchAny(any=value["$in"]),
                        )
                    )
                elif "$ne" in value:
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchExcept(**{"except": [value["$ne"]]}),
                        )
                    )
                else:
                    # Range operators - use if instead of elif to support multiple ranges
                    if "$gt" in value:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                range=models.Range(gt=value["$gt"]),
                            )
                        )
                    if "$gte" in value:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                range=models.Range(gte=value["$gte"]),
                            )
                        )
                    if "$lt" in value:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                range=models.Range(lt=value["$lt"]),
                            )
                        )
                    if "$lte" in value:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                range=models.Range(lte=value["$lte"]),
                            )
                        )
            else:
                # Exact match
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )

        return models.Filter(must=conditions)
