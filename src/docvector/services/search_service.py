"""Search service."""

from typing import Dict, List, Optional

from docvector.core import DocVectorException, get_logger, settings
from docvector.embeddings import BaseEmbedder, LocalEmbedder, OpenAIEmbedder
from docvector.search import HybridSearch, VectorSearch
from docvector.search.reranker import MultiStageReranker
from docvector.utils.token_utils import TokenLimiter
from docvector.vectordb import BaseVectorDB, IVectorStore, get_vector_db

logger = get_logger(__name__)


class SearchService:
    """
    Search service - orchestrates search operations.
    """

    def __init__(self):
        """Initialize search service."""
        self.vectordb: Optional[BaseVectorDB] = None
        self.embedder: Optional[BaseEmbedder] = None
        self.vector_search: Optional[VectorSearch] = None
        self.hybrid_search: Optional[HybridSearch] = None
        self.reranker: MultiStageReranker = MultiStageReranker()
        self.token_limiter: TokenLimiter = TokenLimiter()

    async def initialize(self) -> None:
        """Initialize search components."""
        if self.vector_search is not None:
            return

        logger.info("Initializing search service")

        # Initialize vector database (uses factory to select based on mode)
        self.vectordb = get_vector_db()
        await self.vectordb.initialize()

        # Initialize embedder
        if settings.embedding_provider == "openai":
            self.embedder = OpenAIEmbedder()
        else:
            self.embedder = LocalEmbedder()

        await self.embedder.initialize()

        # Initialize search implementations
        self.vector_search = VectorSearch(
            vectordb=self.vectordb,
            embedder=self.embedder,
        )

        self.hybrid_search = HybridSearch(
            vector_search=self.vector_search,
        )

        logger.info("Search service initialized")

    async def search(
        self,
        query: str,
        limit: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
        use_reranking: bool = True,
        max_tokens: Optional[int] = None,
    ) -> List[Dict]:
        """
        Perform search with optional reranking and token limiting.

        Args:
            query: Search query
            limit: Maximum results
            search_type: 'vector' or 'hybrid'
            filters: Optional filters (supports 'topics' for topic filtering)
            score_threshold: Minimum score
            use_reranking: Whether to apply multi-stage reranking
            max_tokens: Maximum tokens to return (None = no limit)

        Returns:
            List of search results as dicts
        """
        await self.initialize()

        logger.info("Performing search", query=query[:50], type=search_type)

        # Extract topic filter if present
        topic_filter = None
        if filters and "topics" in filters:
            topic_filter = filters.pop("topics")

        # Choose search implementation
        # Fetch more results if we're reranking or filtering by topic
        fetch_limit = limit * 3 if (use_reranking or topic_filter) else limit

        if search_type == "vector":
            if self.vector_search is None:
                raise DocVectorException(
                    code="SERVICE_NOT_INITIALIZED",
                    message="Vector search not initialized",
                )
            results = await self.vector_search.search(
                query=query,
                limit=fetch_limit,
                filters=filters,
                score_threshold=score_threshold,
            )
        else:  # hybrid
            if self.hybrid_search is None:
                raise DocVectorException(
                    code="SERVICE_NOT_INITIALIZED",
                    message="Hybrid search not initialized",
                )
            results = await self.hybrid_search.search(
                query=query,
                limit=fetch_limit,
                filters=filters,
                score_threshold=score_threshold,
            )

        # Convert to dict
        results_dict = [
            {
                "id": r.chunk_id,
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "score": r.score,
                "content": r.content,
                "title": r.title,
                "url": r.url,
                "metadata": r.metadata or {},
            }
            for r in results
        ]

        # Apply topic filtering if specified
        if topic_filter:
            results_dict = [
                r
                for r in results_dict
                if topic_filter.lower() in [t.lower() for t in r["metadata"].get("topics", [])]
            ]

        # Apply reranking if enabled
        if use_reranking and results_dict:
            ranked_results = self.reranker.rerank(
                query=query,
                results=results_dict,
                use_stored_scores=True,
            )

            # Convert back to dict format
            results_dict = [
                {
                    "id": r.id,
                    "chunk_id": r.id,
                    "document_id": r.metadata.get("document_id", "") if r.metadata else "",
                    "score": r.final_score,
                    "vector_score": r.vector_score,
                    "relevance_score": r.relevance_score,
                    "code_quality_score": r.code_quality_score,
                    "formatting_score": r.formatting_score,
                    "metadata_score": r.metadata_score,
                    "initialization_score": r.initialization_score,
                    "content": r.content,
                    "title": r.metadata.get("title", "") if r.metadata else "",
                    "url": r.metadata.get("url", "") if r.metadata else "",
                    "metadata": r.metadata,
                }
                for r in ranked_results[:limit]
            ]

        # Apply token limiting if specified
        if max_tokens:
            results_dict = self.token_limiter.limit_results_to_tokens(
                results_dict,
                max_tokens=max_tokens,
                content_key="content",
            )

        logger.info("Search completed", results=len(results_dict))

        return results_dict

    async def close(self) -> None:
        """Close search service."""
        if self.vectordb:
            await self.vectordb.close()
        if self.embedder:
            await self.embedder.close()

        logger.info("Search service closed")
