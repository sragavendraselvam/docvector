"""Tests for LocalEmbedder with registry integration."""

import pytest

from docvector.embeddings.local_embedder import LocalEmbedder
from docvector.embeddings.registry import DEFAULT_MODEL, EMBEDDING_MODELS


class TestLocalEmbedderInit:
    """Tests for LocalEmbedder initialization."""

    def test_registered_model_init(self):
        """Registered model should initialize with model info."""
        embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        assert embedder._model_info is not None
        assert embedder._model_info.dimension == 384

    def test_default_model_init(self):
        """Should use DEFAULT_MODEL when no model specified."""
        embedder = LocalEmbedder()
        assert embedder.model_name == DEFAULT_MODEL

    def test_custom_model_init(self):
        """Custom HuggingFace model should work without model info."""
        embedder = LocalEmbedder(model_name="custom-org/custom-model")
        assert embedder._model_info is None
        # Should not raise

    def test_invalid_model_raises_error(self):
        """Invalid model name should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown model"):
            LocalEmbedder(model_name="not-valid")

    def test_invalid_model_single_word(self):
        """Single word model name should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown model"):
            LocalEmbedder(model_name="invalidmodel")

    def test_all_registered_models_can_init(self):
        """All registered models should initialize without error."""
        for model_name, expected_info in EMBEDDING_MODELS.items():
            # Skip OpenAI models for local embedder
            if expected_info.provider == "openai":
                continue

            embedder = LocalEmbedder(model_name=model_name)
            assert embedder._model_info is not None
            assert embedder._model_info.dimension == expected_info.dimension


class TestGetDimensionBeforeLoad:
    """Tests for get_dimension() before model is loaded."""

    def test_registered_model_dimension_before_load(self):
        """Should return registry dimension before model load."""
        embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        # Model not loaded yet
        assert embedder.model is None
        # Should still return dimension from registry
        assert embedder.get_dimension() == 384

    def test_bge_base_dimension_before_load(self):
        """Should return correct dimension for BGE base."""
        embedder = LocalEmbedder(model_name="BAAI/bge-base-en-v1.5")
        assert embedder.model is None
        assert embedder.get_dimension() == 768

    def test_custom_model_dimension_fallback(self):
        """Custom model should use fallback dimension."""
        embedder = LocalEmbedder(model_name="custom-org/custom-model")
        assert embedder.model is None
        # Should return fallback dimension (384)
        assert embedder.get_dimension() == 384


class TestGetModelInfo:
    """Tests for get_model_info() accessor."""

    def test_registered_model_info(self):
        """Should return model info for registered models."""
        embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        info = embedder.get_model_info()
        assert info is not None
        assert info.name == "all-MiniLM-L6-v2"
        assert info.dimension == 384

    def test_custom_model_no_info(self):
        """Should return None for custom models."""
        embedder = LocalEmbedder(model_name="custom-org/custom-model")
        assert embedder.get_model_info() is None


class TestDeviceAndBatchSize:
    """Tests for device and batch_size configuration."""

    def test_custom_device(self):
        """Should accept custom device."""
        embedder = LocalEmbedder(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            device="cuda",
        )
        assert embedder.device == "cuda"

    def test_custom_batch_size(self):
        """Should accept custom batch size."""
        embedder = LocalEmbedder(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            batch_size=64,
        )
        assert embedder.batch_size == 64


class TestModelNotLoaded:
    """Tests for behavior before model loading."""

    def test_model_is_none_before_init(self):
        """Model should be None before initialize() is called."""
        embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        assert embedder.model is None

    def test_internal_dimension_none_before_load(self):
        """Internal _dimension should be None before load."""
        embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        assert embedder._dimension is None


class TestOpenAIModelValidation:
    """Tests for OpenAI model rejection in LocalEmbedder."""

    def test_openai_registered_model_rejected(self):
        """OpenAI models from registry should be rejected."""
        with pytest.raises(ValueError, match="OpenAI model"):
            LocalEmbedder(model_name="text-embedding-ada-002")

    def test_openai_model_3_small_rejected(self):
        """text-embedding-3-small should be rejected."""
        with pytest.raises(ValueError, match="OpenAI model"):
            LocalEmbedder(model_name="text-embedding-3-small")

    def test_openai_model_3_large_rejected(self):
        """text-embedding-3-large should be rejected."""
        with pytest.raises(ValueError, match="OpenAI model"):
            LocalEmbedder(model_name="text-embedding-3-large")

    def test_openai_pattern_unregistered_rejected(self):
        """Unregistered text-embedding-* patterns should be rejected."""
        with pytest.raises(ValueError, match="appears to be an OpenAI model"):
            LocalEmbedder(model_name="text-embedding-future-model")

    def test_error_message_suggests_alternatives(self):
        """Error message should suggest using OpenAIEmbedder or create_embedder."""
        with pytest.raises(ValueError, match="OpenAIEmbedder"):
            LocalEmbedder(model_name="text-embedding-3-small")

        with pytest.raises(ValueError, match="create_embedder"):
            LocalEmbedder(model_name="text-embedding-3-small")


class TestMultipleModels:
    """Tests for dimension accuracy across multiple models."""

    @pytest.mark.parametrize(
        "model_name,expected_dim",
        [
            ("sentence-transformers/all-MiniLM-L6-v2", 384),
            ("sentence-transformers/all-mpnet-base-v2", 768),
            ("BAAI/bge-small-en-v1.5", 384),
            ("BAAI/bge-base-en-v1.5", 768),
            ("BAAI/bge-large-en-v1.5", 1024),
        ],
    )
    def test_model_dimensions(self, model_name, expected_dim):
        """Parametrized test for model dimensions."""
        embedder = LocalEmbedder(model_name=model_name)
        assert embedder.get_dimension() == expected_dim
