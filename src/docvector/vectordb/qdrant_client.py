"""Qdrant vector database implementation."""

from typing import Dict, List, Optional, Any, cast

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from docvector.core import get_logger, settings

from .base import IVectorStore, VectorRecord, VectorSearchResult

logger = get_logger(__name__)


class QdrantVectorDB(IVectorStore):
    """Qdrant implementation of vector database.
    
    Qdrant is a high-performance vector database used for cloud and hybrid
    deployments of DocVector. It supports both HTTP and gRPC protocols.
    """

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

    async def close(self) -> None:
        """Close Qdrant client."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Qdrant client closed")

    async def create_collection(
        self,
        name: str,
        dimension: int,
        distance_metric: str = "cosine",
    ) -> None:
        """Create a new Qdrant collection."""
        if not self.client:
            await self.initialize()
            
        assert self.client is not None

        # Map distance names
        distance_map = {
            "cosine": models.Distance.COSINE,
            "euclidean": models.Distance.EUCLID,
            "dot": models.Distance.DOT,
        }

        distance_metric_val = distance_map.get(distance_metric.lower(), models.Distance.COSINE)

        logger.info(
            "Creating Qdrant collection",
            collection=name,
            vector_size=dimension,
            distance=distance_metric,
        )

        try:
            await self.client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=distance_metric_val,
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
            logger.info("Collection created successfully", collection=name)
        except UnexpectedResponse as e:
            # Handle collection already exists (409 Conflict)
            status_code = getattr(e, 'status_code', None)
            if status_code is None and hasattr(e, 'response'):
                status_code = getattr(e.response, 'status_code', None)

            if status_code == 409 or "already exists" in str(e).lower():
                logger.warning("Collection already exists", collection=name)
                raise ValueError(f"Collection {name} already exists")
            raise RuntimeError(f"Failed to create collection {name}: {e}")

    async def delete_collection(self, name: str) -> None:
        if not self.client:
            await self.initialize()
        assert self.client is not None

        try:
            await self.client.delete_collection(collection_name=name)
        except UnexpectedResponse as e:
            # Check for not found error (404)
            status_code = getattr(e, 'status_code', None)
            if status_code is None and hasattr(e, 'response'):
                status_code = getattr(e.response, 'status_code', None)

            if status_code == 404 or "not found" in str(e).lower():
                raise ValueError(f"Collection {name} does not exist")
            raise RuntimeError(f"Failed to delete collection {name}: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to delete collection {name}: {e}")
    
    async def collection_exists(self, name: str) -> bool:
        if not self.client:
            await self.initialize()
        assert self.client is not None

        try:
            await self.client.get_collection(name)
            return True
        except Exception:
            return False

    async def get_collection_info(self, name: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            await self.initialize()
        assert self.client is not None

        try:
            info = await self.client.get_collection(name)
            
            # Extract dimension from vector params if single vector
            dimension = 0
            distance_metric = "cosine"
            
            config = info.config.params.vectors
            if isinstance(config, models.VectorParams):
                dimension = config.size
                distance_metric = str(config.distance).lower()
                if "distance.cosine" in str(config.distance): distance_metric = "cosine"
                if "distance.euclid" in str(config.distance): distance_metric = "euclidean" 
                
            return {
                "name": name,
                "dimension": dimension,
                "vector_count": info.points_count,
                "distance_metric": distance_metric
            }
        except Exception:
            return None

    async def upsert(
        self,
        collection: str,
        records: List[VectorRecord],
    ) -> int:
        if not self.client:
            await self.initialize()
        assert self.client is not None

        if not records:
            return 0

        # Create points
        points = [
            models.PointStruct(
                id=r.id,
                vector=r.vector,
                payload=r.payload,
            )
            for r in records
        ]

        try:
            res = await self.client.upsert(
                collection_name=collection,
                points=points,
                wait=True,
            )
            if res.status == models.UpdateStatus.COMPLETED:
                return len(records)
            return 0
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                raise ValueError(f"Collection {collection} does not exist")
            raise RuntimeError(f"Failed to upsert: {e}")

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[VectorSearchResult]:
        if not self.client:
            await self.initialize()
        assert self.client is not None

        # Convert filter dict to Qdrant filter
        qdrant_filter = self._build_filter(filters) if filters else None

        try:
            results = await self.client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                query_filter=qdrant_filter,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )

            return [
                VectorSearchResult(
                    id=str(result.id),
                    score=result.score,
                    payload=result.payload or {},
                    vector=None
                )
                for result in results.points
            ]
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                 raise ValueError(f"Collection {collection} does not exist")
            raise RuntimeError(f"Search failed: {e}")

    async def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        if not self.client:
            await self.initialize()
        assert self.client is not None

        if ids is None and filters is None:
            raise ValueError("Either ids or filters must be provided")

        try:
            # Get pre-count
            pre_info = await self.client.get_collection(collection)
            pre_count = pre_info.points_count or 0
            
            if ids:
                await self.client.delete(
                    collection_name=collection,
                    points_selector=models.PointIdsList(points=ids),
                    wait=True,
                )
            
            if filters:
                 qdrant_filter = self._build_filter(filters)
                 await self.client.delete(
                    collection_name=collection,
                    points_selector=models.FilterSelector(filter=qdrant_filter),
                    wait=True,
                )

            # Get post-count
            post_info = await self.client.get_collection(collection)
            post_count = post_info.points_count or 0
            
            return max(0, pre_count - post_count)
            
        except UnexpectedResponse:
             raise ValueError(f"Collection {collection} does not exist")
        except Exception as e:
            raise RuntimeError(f"Failed to delete: {e}")


    async def count(self, collection: str) -> int:
        if not self.client:
            await self.initialize()
        assert self.client is not None
        
        try:
            res = await self.client.count(collection_name=collection)
            return res.count
        except UnexpectedResponse:
             raise ValueError(f"Collection {collection} does not exist")


    def _build_filter(self, filter_dict: Dict) -> models.Filter:
        """
        Build Qdrant filter from dictionary.
        """
        conditions = []

        for key, value in filter_dict.items():
            if key == "$and":
                sub_filters = [self._build_filter(f) for f in cast(List, value)]
                # Extract 'must' list from sub-filter if possible, or wrap it
                # Qdrant python client constructs are a bit nested.
                # A simple approximation:
                nested_musts = []
                for sub in sub_filters:
                     if sub.must: nested_musts.extend(sub.must)
                conditions.extend(nested_musts)

            elif key == "$or":
                # OR is top level 'should' typically, but here we are in a loop adding to 'must' (conditions)
                # If we have mixed AND/OR need detailed recursion logic
                # For simplified implementation, we assume basic structure
                pass

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
                    # Range operators
                    if "$gt" in value:
                        conditions.append(models.FieldCondition(key=key, range=models.Range(gt=value["$gt"])))
                    if "$gte" in value:
                        conditions.append(models.FieldCondition(key=key, range=models.Range(gte=value["$gte"])))
                    if "$lt" in value:
                        conditions.append(models.FieldCondition(key=key, range=models.Range(lt=value["$lt"])))
                    if "$lte" in value:
                        conditions.append(models.FieldCondition(key=key, range=models.Range(lte=value["$lte"])))
            else:
                # Exact match
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )

        return models.Filter(must=conditions)
