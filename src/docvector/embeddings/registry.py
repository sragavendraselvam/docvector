"""Embedding model registry with metadata and validation."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ModelSpeed(Enum):
    """Model inference speed category."""

    FAST = "fast"  # < 100ms per batch of 32
    MEDIUM = "medium"  # 100-500ms per batch
    SLOW = "slow"  # > 500ms per batch


class ModelQuality(Enum):
    """Model output quality category."""

    BASIC = "basic"  # Good for simple use cases
    GOOD = "good"  # Recommended for most uses
    EXCELLENT = "excellent"  # Best quality, higher resource usage


@dataclass
class EmbeddingModelInfo:
    """Information about an embedding model."""

    name: str  # Display name
    dimension: int  # Output vector dimension
    speed: ModelSpeed  # Speed category
    quality: ModelQuality  # Quality category
    memory_mb: int  # Approximate memory usage in MB
    description: str  # Human-readable description
    provider: str  # "sentence-transformers", "openai", "huggingface"
    use_cases: List[str]  # Recommended use cases
    max_tokens: int = 512  # Maximum input tokens


# Registry of supported models
EMBEDDING_MODELS: Dict[str, EmbeddingModelInfo] = {
    # ============================================================
    # FAST MODELS (< 100ms per batch)
    # ============================================================
    "sentence-transformers/all-MiniLM-L6-v2": EmbeddingModelInfo(
        name="all-MiniLM-L6-v2",
        dimension=384,
        speed=ModelSpeed.FAST,
        quality=ModelQuality.GOOD,
        memory_mb=90,
        description="Fast, lightweight model. Great balance of speed and quality.",
        provider="sentence-transformers",
        use_cases=["general", "documentation", "quick-search"],
    ),
    "BAAI/bge-small-en-v1.5": EmbeddingModelInfo(
        name="bge-small-en-v1.5",
        dimension=384,
        speed=ModelSpeed.FAST,
        quality=ModelQuality.EXCELLENT,
        memory_mb=130,
        description="Excellent quality for its size. Great for technical docs.",
        provider="sentence-transformers",
        use_cases=["technical", "code", "documentation"],
    ),
    # ============================================================
    # MEDIUM MODELS (100-500ms per batch)
    # ============================================================
    "sentence-transformers/all-mpnet-base-v2": EmbeddingModelInfo(
        name="all-mpnet-base-v2",
        dimension=768,
        speed=ModelSpeed.MEDIUM,
        quality=ModelQuality.EXCELLENT,
        memory_mb=420,
        description="High quality general-purpose model.",
        provider="sentence-transformers",
        use_cases=["general", "semantic-search", "qa"],
    ),
    "BAAI/bge-base-en-v1.5": EmbeddingModelInfo(
        name="bge-base-en-v1.5",
        dimension=768,
        speed=ModelSpeed.MEDIUM,
        quality=ModelQuality.EXCELLENT,
        memory_mb=440,
        description="State-of-the-art for retrieval tasks.",
        provider="sentence-transformers",
        use_cases=["retrieval", "technical", "code"],
    ),
    "thenlper/gte-base": EmbeddingModelInfo(
        name="gte-base",
        dimension=768,
        speed=ModelSpeed.MEDIUM,
        quality=ModelQuality.EXCELLENT,
        memory_mb=440,
        description="Excellent for long documents and technical content.",
        provider="sentence-transformers",
        use_cases=["long-documents", "technical", "academic"],
    ),
    # ============================================================
    # SLOW MODELS (> 500ms per batch)
    # ============================================================
    "BAAI/bge-large-en-v1.5": EmbeddingModelInfo(
        name="bge-large-en-v1.5",
        dimension=1024,
        speed=ModelSpeed.SLOW,
        quality=ModelQuality.EXCELLENT,
        memory_mb=1340,
        description="Highest quality BGE model. Requires more resources.",
        provider="sentence-transformers",
        use_cases=["high-precision", "academic", "legal"],
    ),
    # ============================================================
    # OPENAI MODELS (API-based)
    # ============================================================
    "text-embedding-3-small": EmbeddingModelInfo(
        name="text-embedding-3-small",
        dimension=1536,
        speed=ModelSpeed.FAST,
        quality=ModelQuality.EXCELLENT,
        memory_mb=0,
        description="OpenAI's efficient embedding model. Requires API key.",
        provider="openai",
        use_cases=["cloud", "production", "multilingual"],
    ),
    "text-embedding-3-large": EmbeddingModelInfo(
        name="text-embedding-3-large",
        dimension=3072,
        speed=ModelSpeed.MEDIUM,
        quality=ModelQuality.EXCELLENT,
        memory_mb=0,
        description="OpenAI's highest quality model. Requires API key.",
        provider="openai",
        use_cases=["high-precision", "production", "multilingual"],
    ),
    "text-embedding-ada-002": EmbeddingModelInfo(
        name="text-embedding-ada-002",
        dimension=1536,
        speed=ModelSpeed.FAST,
        quality=ModelQuality.GOOD,
        memory_mb=0,
        description="OpenAI's legacy embedding model. Consider using text-embedding-3-small instead.",
        provider="openai",
        use_cases=["legacy", "compatibility"],
    ),
}

# Default model
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def get_model_info(model_name: str) -> Optional[EmbeddingModelInfo]:
    """
    Get information about a registered model.

    Args:
        model_name: Full model name (e.g., "sentence-transformers/all-MiniLM-L6-v2")

    Returns:
        Model info if registered, None otherwise
    """
    return EMBEDDING_MODELS.get(model_name)


def get_model_dimension(model_name: str) -> int:
    """
    Get the embedding dimension for a model.

    Returns known dimension for registered models, or 384 as fallback
    for unknown models.

    Args:
        model_name: Full model name

    Returns:
        Embedding dimension
    """
    info = get_model_info(model_name)
    if info:
        return info.dimension

    # Default fallback for unknown models
    return 384


def validate_model(model_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate model name.

    Args:
        model_name: Model name to validate

    Returns:
        Tuple of (is_valid, message):
        - is_valid: True if model can be used
        - message: None for registered models, warning for custom models,
                   error message for invalid models
    """
    # Registered model
    if model_name in EMBEDDING_MODELS:
        return True, None

    # Custom HuggingFace model (org/model-name format)
    if "/" in model_name and len(model_name.split("/")) == 2:
        org, name = model_name.split("/")
        if org and name:
            return (
                True,
                f"Using custom model '{model_name}'. "
                "Dimension will be auto-detected at load time.",
            )

    # OpenAI model patterns
    if model_name.startswith("text-embedding-"):
        return True, None

    return (
        False,
        f"Unknown model: '{model_name}'. "
        "Use a registered model or HuggingFace format (org/model-name).",
    )


def list_models(
    provider: Optional[str] = None,
    speed: Optional[ModelSpeed] = None,
    min_quality: Optional[ModelQuality] = None,
) -> List[str]:
    """
    List models matching criteria.

    Args:
        provider: Filter by provider ("sentence-transformers", "openai")
        speed: Filter by speed category
        min_quality: Minimum quality level

    Returns:
        List of model names matching criteria
    """
    quality_order = [ModelQuality.BASIC, ModelQuality.GOOD, ModelQuality.EXCELLENT]

    results = []
    for name, info in EMBEDDING_MODELS.items():
        if provider and info.provider != provider:
            continue
        if speed and info.speed != speed:
            continue
        if min_quality:
            if quality_order.index(info.quality) < quality_order.index(min_quality):
                continue
        results.append(name)

    return results


def get_recommended_model(use_case: str = "general") -> str:
    """
    Get recommended model for a use case.

    Args:
        use_case: Use case identifier (general, technical, code,
                  documentation, production, high-precision)

    Returns:
        Recommended model name
    """
    recommendations = {
        "general": "sentence-transformers/all-MiniLM-L6-v2",
        "technical": "BAAI/bge-base-en-v1.5",
        "code": "BAAI/bge-small-en-v1.5",
        "documentation": "sentence-transformers/all-MiniLM-L6-v2",
        "production": "text-embedding-3-small",
        "high-precision": "BAAI/bge-large-en-v1.5",
    }
    return recommendations.get(use_case, DEFAULT_MODEL)
