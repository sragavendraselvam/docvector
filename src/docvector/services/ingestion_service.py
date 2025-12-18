"""Ingestion service - orchestrates document ingestion."""

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from docvector.core import DocVectorException, get_logger, settings
from docvector.db.repositories import ChunkRepository, DocumentRepository
from docvector.embeddings import BaseEmbedder, EmbeddingCache, LocalEmbedder, OpenAIEmbedder
from docvector.ingestion import Crawl4AICrawler
from docvector.models import Chunk, Document, Source
from docvector.processing import ProcessingPipeline
from docvector.utils import compute_text_hash
from docvector.vectordb import get_vector_db, IVectorStore, VectorRecord

logger = get_logger(__name__)


class IngestionService:
    """
    Ingestion service - orchestrates the complete document ingestion pipeline.

    Flow:
    1. Fetch documents from source (web, git, etc.)
    2. Process documents (parse, chunk)
    3. Generate embeddings
    4. Store in vector DB and PostgreSQL
    """

    def __init__(self, session: AsyncSession):
        """Initialize ingestion service."""
        self.session = session
        self.document_repo = DocumentRepository(session)
        self.chunk_repo = ChunkRepository(session)

        # Initialize components (lazy)
        self.crawler: Optional[Crawl4AICrawler] = None
        self.pipeline: Optional[ProcessingPipeline] = None
        self.embedder: Optional[BaseEmbedder] = None
        self.embedding_cache: Optional[EmbeddingCache] = None
        self.vectordb: Optional[IVectorStore] = None

    async def initialize(self) -> None:
        """Initialize components."""
        if self.embedder is not None:
            return

        logger.info("Initializing ingestion service")

        # Initialize crawler (using Crawl4AI for fast, AI-optimized fetching)
        self.crawler = Crawl4AICrawler()

        # Initialize processing pipeline
        self.pipeline = ProcessingPipeline()

        # Initialize embedder
        if settings.embedding_provider == "openai":
            self.embedder = OpenAIEmbedder()
        else:
            self.embedder = LocalEmbedder()

        await self.embedder.initialize()

        # Initialize embedding cache
        if settings.embedding_cache_enabled:
            self.embedding_cache = EmbeddingCache()
            await self.embedding_cache.initialize()

        # Initialize vector DB (uses factory to select based on mode)
        self.vectordb = get_vector_db()
        await self.vectordb.initialize()

        # Ensure collection exists
        collection_name = settings.vector_collection
        collection_exists = await self.vectordb.collection_exists(collection_name)
        if not collection_exists:
            logger.info("Creating vector collection", collection=collection_name)
            await self.vectordb.create_collection(
                name=collection_name,
                dimension=self.embedder.get_dimension(),
            )

        logger.info("Ingestion service initialized")

    async def ingest_source(
        self,
        source: Source,
        access_level: str = "private",
    ) -> Dict:
        """
        Ingest all documents from a source.

        Args:
            source: Source to ingest
            access_level: 'public' or 'private'

        Returns:
            Ingestion statistics
        """
        await self.initialize()

        logger.info(
            "Starting source ingestion",
            source_id=str(source.id),
            source_name=source.name,
            source_type=source.type,
            access_level=access_level,
        )

        stats = {
            "fetched": 0,
            "processed": 0,
            "chunks_created": 0,
            "errors": 0,
        }

        try:
            # Fetch documents based on source type
            if source.type == "web":
                if self.crawler is None:
                    raise DocVectorException(
                        code="SERVICE_NOT_INITIALIZED",
                        message="Crawler not initialized",
                    )
                fetched_docs = await self.crawler.fetch(source.config)
            else:
                raise DocVectorException(
                    code="UNSUPPORTED_SOURCE_TYPE",
                    message=f"Source type '{source.type}' not yet implemented",
                )

            stats["fetched"] = len(fetched_docs)

            # Process each document
            for fetched_doc in fetched_docs:
                try:
                    await self._process_document(
                        source=source,
                        fetched_doc=fetched_doc,
                        access_level=access_level,
                    )
                    stats["processed"] += 1
                except Exception as e:
                    logger.error(
                        "Failed to process document",
                        url=fetched_doc.url,
                        error=str(e),
                    )
                    stats["errors"] += 1

            # Update source sync time
            source.last_synced_at = datetime.utcnow()
            await self.session.commit()

            logger.info("Source ingestion completed", stats=stats)

            return stats

        except Exception as e:
            logger.error("Source ingestion failed", error=str(e))
            raise

    async def ingest_url(
        self,
        source: Source,
        url: str,
        access_level: str = "private",
    ) -> Document:
        """
        Ingest a single URL.

        Args:
            source: Source the URL belongs to
            url: URL to ingest
            access_level: 'public' or 'private'

        Returns:
            Created document
        """
        await self.initialize()

        logger.info(
            "Ingesting single URL",
            source_id=str(source.id),
            url=url,
            access_level=access_level,
        )

        # Fetch document
        if self.crawler is None:
            raise DocVectorException(
                code="SERVICE_NOT_INITIALIZED",
                message="Crawler not initialized",
            )
        fetched_doc = await self.crawler.fetch_single(url)

        # Process document
        document = await self._process_document(
            source=source,
            fetched_doc=fetched_doc,
            access_level=access_level,
        )

        # Update source sync time
        source.last_synced_at = datetime.utcnow()
        await self.session.commit()

        logger.info("URL ingestion completed", document_id=str(document.id))

        return document

    async def _process_document(
        self,
        source: Source,
        fetched_doc,
        access_level: str,
    ) -> Document:
        """Process a fetched document through the pipeline."""
        # Check if document already exists
        content_hash = compute_text_hash(fetched_doc.content.decode("utf-8", errors="ignore"))
        existing = await self.document_repo.get_by_content_hash(source.id, content_hash)

        if existing and existing.status == "completed":
            logger.debug("Document already exists", url=fetched_doc.url)
            return existing

        # Create or update document record
        if existing:
            document = existing
        else:
            document = Document(
                source_id=source.id,
                url=fetched_doc.url,
                content_hash=content_hash,
                status="processing",
                fetched_at=datetime.utcnow(),
            )
            document = await self.document_repo.create(document)
            await self.session.flush()

        try:
            # Process document (parse and chunk)
            if self.pipeline is None:
                raise DocVectorException(
                    code="SERVICE_NOT_INITIALIZED",
                    message="Pipeline not initialized",
                )
            parsed, chunks = await self.pipeline.process(
                content=fetched_doc.content,
                mime_type=fetched_doc.mime_type,
                url=fetched_doc.url,
                metadata={
                    "access_level": access_level,  # Add access level to metadata
                    "source_id": str(source.id),
                    "source_name": source.name,
                },
            )

            # Update document with parsed info
            document.title = parsed.title or fetched_doc.title
            document.content = parsed.content
            document.content_length = len(parsed.content)
            document.metadata = parsed.metadata
            document.language = parsed.language
            document.chunk_count = len(chunks)
            document.processed_at = datetime.utcnow()

            await self.session.flush()

            # Generate embeddings and store chunks
            await self._process_chunks(document, chunks, access_level)

            # Update document status
            document.status = "completed"
            await self.session.flush()

            logger.info(
                "Document processed",
                document_id=str(document.id),
                chunks=len(chunks),
            )

            return document

        except Exception as e:
            document.status = "failed"
            document.error_message = str(e)
            await self.session.flush()
            raise

    async def _process_chunks(
        self,
        document: Document,
        text_chunks,
        access_level: str,
    ) -> None:
        """Generate embeddings and store chunks."""
        if not text_chunks:
            return

        # Prepare chunk texts for embedding
        chunk_texts = [chunk.content for chunk in text_chunks]

        # Check cache for embeddings
        cached_embeddings = {}
        if self.embedding_cache:
            cached_embeddings = await self.embedding_cache.get_many(
                texts=chunk_texts,
                model=settings.embedding_model,
            )

        # Generate embeddings for uncached chunks
        texts_to_embed = [text for text in chunk_texts if text not in cached_embeddings]

        if texts_to_embed:
            logger.debug("Generating embeddings", count=len(texts_to_embed))
            if self.embedder is None:
                raise DocVectorException(
                    code="SERVICE_NOT_INITIALIZED",
                    message="Embedder not initialized",
                )
            new_embeddings_list = await self.embedder.embed(texts_to_embed)

            # Create embedding map
            new_embeddings = dict(zip(texts_to_embed, new_embeddings_list))

            # Cache new embeddings
            if self.embedding_cache:
                await self.embedding_cache.set_many(
                    texts=texts_to_embed,
                    model=settings.embedding_model,
                    embeddings=new_embeddings_list,
                )
        else:
            new_embeddings = {}

        # Combine cached and new embeddings
        all_embeddings = {**cached_embeddings, **new_embeddings}

        # Create chunk records and store in vector DB
        chunk_models = []
        vector_ids = []
        vectors = []
        payloads = []

        for _i, text_chunk in enumerate(text_chunks):
            # Create chunk record
            chunk = Chunk(
                document_id=document.id,
                index=text_chunk.index,
                content=text_chunk.content,
                content_length=text_chunk.length,
                start_char=text_chunk.start_char,
                end_char=text_chunk.end_char,
                metadata=text_chunk.metadata,
                embedding_model=settings.embedding_model,
                embedded_at=datetime.utcnow(),
            )
            chunk_models.append(chunk)

        # Save chunks to database
        chunks = await self.chunk_repo.create_many(chunk_models)
        await self.session.flush()

        # Prepare vector DB data
        for chunk in chunks:
            embedding = all_embeddings.get(chunk.content)
            if not embedding:
                logger.warning("Missing embedding for chunk", chunk_id=str(chunk.id))
                continue

            # Store embedding ID in chunk
            chunk.embedding_id = str(chunk.id)

            vector_ids.append(str(chunk.id))
            vectors.append(embedding)
            payloads.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(document.id),
                    "source_id": str(document.source_id),
                    "content": chunk.content,
                    "title": document.title,
                    "url": document.url,
                    "access_level": access_level,  # Store access level for filtering
                    "metadata": chunk.metadata,
                }
            )

        # Store in vector database
        if vector_ids:
            if self.vectordb is None:
                raise DocVectorException(
                    code="SERVICE_NOT_INITIALIZED",
                    message="Vector DB not initialized",
                )
            # Create VectorRecord objects for the new interface
            records = [
                VectorRecord(id=vid, vector=vec, payload=payload)
                for vid, vec, payload in zip(vector_ids, vectors, payloads)
            ]
            await self.vectordb.upsert(
                collection=settings.vector_collection,
                records=records,
            )

            logger.debug(
                "Chunks stored in vector DB",
                count=len(vector_ids),
                document_id=str(document.id),
            )

    async def close(self) -> None:
        """Close connections."""
        if self.embedder:
            await self.embedder.close()
        if self.embedding_cache:
            await self.embedding_cache.close()
        if self.vectordb:
            await self.vectordb.close()
