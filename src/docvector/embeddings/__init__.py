"""Embedding generation services."""

from typing import Optional

from .base import BaseEmbedder
from .cache import EmbeddingCache
from .local_embedder import LocalEmbedder
from .openai_embedder import OpenAIEmbedder
from .registry import (
    DEFAULT_MODEL,
    EMBEDDING_MODELS,
    EmbeddingModelInfo,
    ModelQuality,
    ModelSpeed,
    get_model_dimension,
    get_model_info,
    get_recommended_model,
    list_models,
    validate_model,
)


def create_embedder(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    device: Optional[str] = None,
    batch_size: Optional[int] = None,
) -> BaseEmbedder:
    """
    Factory function to create appropriate embedder based on settings.

    Args:
        provider: "local" or "openai" (defaults to auto-detect from model, then settings)
        model: Model name (defaults to settings.embedding_model)
        device: Device for local embedder (defaults to settings.embedding_device)
        batch_size: Batch size (defaults to settings.embedding_batch_size)

    Returns:
        Configured embedder instance (LocalEmbedder or OpenAIEmbedder)

    Raises:
        ValueError: If provider and model are incompatible

    Examples:
        # Use settings
        embedder = create_embedder()

        # Force local provider
        embedder = create_embedder(provider="local")

        # Specific model (auto-detects provider)
        embedder = create_embedder(model="BAAI/bge-base-en-v1.5")

        # OpenAI embeddings
        embedder = create_embedder(provider="openai", model="text-embedding-3-small")
    """
    from docvector.core import settings

    effective_model = model or settings.embedding_model or DEFAULT_MODEL

    # Get model info from registry to determine provider
    model_info = get_model_info(effective_model)

    # Determine model's expected provider
    model_provider = None
    if model_info:
        model_provider = "openai" if model_info.provider == "openai" else "local"
    elif effective_model.startswith("text-embedding-"):
        # OpenAI model pattern not in registry
        model_provider = "openai"

    # Determine effective provider
    if provider:
        effective_provider = provider
    elif model_provider:
        # Auto-detect from model
        effective_provider = model_provider
    else:
        # Fall back to settings
        effective_provider = settings.embedding_provider

    # Validate provider-model compatibility
    if model_provider and provider and model_provider != provider:
        if model_provider == "openai":
            raise ValueError(
                f"Model '{effective_model}' is an OpenAI model but provider='local' was specified. "
                f"Use provider='openai' or omit provider to auto-detect."
            )
        else:
            raise ValueError(
                f"Model '{effective_model}' is a local model but provider='openai' was specified. "
                f"Use provider='local' or omit provider to auto-detect."
            )

    if effective_provider == "openai":
        return OpenAIEmbedder(model=effective_model)
    else:
        return LocalEmbedder(
            model_name=effective_model,
            device=device,
            batch_size=batch_size,
        )


def get_embedder_info() -> dict:
    """
    Get information about the currently configured embedder.

    Returns:
        Dict with provider, model, dimension, and other metadata
    """
    from docvector.core import settings

    model = settings.embedding_model or DEFAULT_MODEL
    model_info = get_model_info(model)

    return {
        "provider": settings.embedding_provider,
        "model": model,
        "dimension": get_model_dimension(model),
        "device": settings.embedding_device,
        "batch_size": settings.embedding_batch_size,
        "is_registered": model_info is not None,
        "model_info": (
            {
                "name": model_info.name,
                "quality": model_info.quality.value,
                "speed": model_info.speed.value,
                "memory_mb": model_info.memory_mb,
                "description": model_info.description,
            }
            if model_info
            else None
        ),
    }


__all__ = [
    # Base classes
    "BaseEmbedder",
    "LocalEmbedder",
    "OpenAIEmbedder",
    "EmbeddingCache",
    # Factory
    "create_embedder",
    "get_embedder_info",
    # Registry
    "EMBEDDING_MODELS",
    "DEFAULT_MODEL",
    "EmbeddingModelInfo",
    "ModelSpeed",
    "ModelQuality",
    "get_model_info",
    "get_model_dimension",
    "validate_model",
    "list_models",
    "get_recommended_model",
]
