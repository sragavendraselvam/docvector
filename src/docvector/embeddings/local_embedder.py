"""Local embedding generation using sentence-transformers."""

import asyncio
from functools import partial
from typing import List, Optional

from sentence_transformers import SentenceTransformer

from docvector.core import get_logger, settings

from .base import BaseEmbedder
from .registry import (
    DEFAULT_MODEL,
    EmbeddingModelInfo,
    get_model_dimension,
    get_model_info,
    validate_model,
)

logger = get_logger(__name__)


class LocalEmbedder(BaseEmbedder):
    """Local embedding generator using sentence-transformers."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        """
        Initialize local embedder.

        Args:
            model_name: Model name (HuggingFace format: org/model-name)
            device: Device to use (cpu, cuda, mps)
            batch_size: Batch size for encoding

        Raises:
            ValueError: If model_name is invalid
        """
        self.model_name = model_name or settings.embedding_model or DEFAULT_MODEL
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        self.model: Optional[SentenceTransformer] = None
        self._dimension: Optional[int] = None
        self._model_info: Optional[EmbeddingModelInfo] = None

        # Validate model at initialization
        self._validate_and_setup()

    def _validate_and_setup(self) -> None:
        """Validate model and setup expected dimension."""
        is_valid, message = validate_model(self.model_name)

        if not is_valid:
            raise ValueError(message)

        if message:  # Warning for custom models
            logger.warning(message)

        # Get model info if registered
        self._model_info = get_model_info(self.model_name)

        # Reject OpenAI models - they require OpenAIEmbedder
        if self._model_info and self._model_info.provider == "openai":
            raise ValueError(
                f"Model '{self.model_name}' is an OpenAI model and cannot be used with LocalEmbedder. "
                f"Use OpenAIEmbedder instead, or use create_embedder() which auto-detects the provider."
            )

        # Also reject models matching OpenAI naming pattern (not in registry)
        if self.model_name.startswith("text-embedding-"):
            raise ValueError(
                f"Model '{self.model_name}' appears to be an OpenAI model and cannot be used with LocalEmbedder. "
                f"Use OpenAIEmbedder instead, or use create_embedder() which auto-detects the provider."
            )

        if self._model_info:
            logger.info(
                "Using registered model",
                model=self.model_name,
                dimension=self._model_info.dimension,
                quality=self._model_info.quality.value,
                memory_mb=self._model_info.memory_mb,
            )
        else:
            logger.info(
                "Using custom model",
                model=self.model_name,
                note="Dimension will be detected at load time",
            )

    async def initialize(self) -> None:
        """Load the sentence-transformers model."""
        if self.model is not None:
            return

        expected_dim = self._model_info.dimension if self._model_info else None
        expected_mem = self._model_info.memory_mb if self._model_info else "unknown"

        logger.info(
            "Loading embedding model",
            model=self.model_name,
            device=self.device,
            expected_dimension=expected_dim or "auto-detect",
            expected_memory_mb=expected_mem,
        )

        # Load model in executor to avoid blocking
        loop = asyncio.get_event_loop()

        def load_model():
            # Load model without device parameter first to avoid meta tensor issues
            model = SentenceTransformer(self.model_name)
            # Then move to device if needed
            if self.device and self.device != "cpu":
                model = model.to(self.device)
            return model

        self.model = await loop.run_in_executor(None, load_model)

        # Get embedding dimension
        self._dimension = self.model.get_sentence_embedding_dimension()

        # Verify dimension matches registry
        if expected_dim and expected_dim != self._dimension:
            logger.warning(
                "Model dimension mismatch with registry",
                expected=expected_dim,
                actual=self._dimension,
                note="This may indicate a registry bug or model update",
            )

        logger.info(
            "Model loaded successfully",
            model=self.model_name,
            dimension=self._dimension,
        )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        await self.initialize()

        if not texts:
            return []

        logger.debug("Generating embeddings", count=len(texts))

        # Encode in executor to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            partial(
                self.model.encode,
                texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,  # Normalize for cosine similarity
            ),
        )

        # Convert to list of lists
        result = embeddings.tolist()

        logger.debug("Embeddings generated", count=len(result))

        return result

    async def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text."""
        result = await self.embed([text])
        return result[0] if result else []

    def get_dimension(self) -> int:
        """
        Get embedding dimension.

        Returns known dimension from registry before model is loaded,
        or actual dimension after loading.

        Returns:
            Embedding dimension
        """
        if self._dimension is not None:
            return self._dimension

        if self._model_info:
            return self._model_info.dimension

        # Fallback for unloaded custom models
        return get_model_dimension(self.model_name)

    def get_model_info(self) -> Optional[EmbeddingModelInfo]:
        """
        Get registry info for this model, if available.

        Returns:
            Model info from registry, or None for custom models
        """
        return self._model_info

    async def close(self) -> None:
        """Cleanup resources."""
        self.model = None
        logger.info("Local embedder closed")
