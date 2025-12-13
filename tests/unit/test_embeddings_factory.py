"""Tests for embeddings factory and module exports."""

import pytest


class TestModuleExports:
    """Tests for module exports."""

    def test_import_create_embedder(self):
        """create_embedder should be importable from embeddings module."""
        from docvector.embeddings import create_embedder

        assert callable(create_embedder)

    def test_import_get_embedder_info(self):
        """get_embedder_info should be importable from embeddings module."""
        from docvector.embeddings import get_embedder_info

        assert callable(get_embedder_info)

    def test_import_get_model_dimension(self):
        """get_model_dimension should be importable from embeddings module."""
        from docvector.embeddings import get_model_dimension

        assert callable(get_model_dimension)

    def test_import_registry_types(self):
        """Registry types should be importable."""
        from docvector.embeddings import (
            DEFAULT_MODEL,
            EMBEDDING_MODELS,
            EmbeddingModelInfo,
            ModelQuality,
            ModelSpeed,
        )

        assert DEFAULT_MODEL is not None
        assert len(EMBEDDING_MODELS) >= 8
        assert EmbeddingModelInfo is not None
        assert ModelQuality is not None
        assert ModelSpeed is not None

    def test_import_registry_functions(self):
        """Registry functions should be importable."""
        from docvector.embeddings import (
            get_model_info,
            get_recommended_model,
            list_models,
            validate_model,
        )

        assert callable(get_model_info)
        assert callable(get_recommended_model)
        assert callable(list_models)
        assert callable(validate_model)

    def test_backward_compatible_imports(self):
        """Existing imports should still work."""
        from docvector.embeddings import (
            BaseEmbedder,
            EmbeddingCache,
            LocalEmbedder,
            OpenAIEmbedder,
        )

        assert BaseEmbedder is not None
        assert LocalEmbedder is not None
        assert OpenAIEmbedder is not None
        assert EmbeddingCache is not None


class TestCreateEmbedder:
    """Tests for create_embedder factory function."""

    def test_create_embedder_default(self):
        """Default should return LocalEmbedder."""
        from docvector.embeddings import LocalEmbedder, create_embedder

        embedder = create_embedder()
        assert isinstance(embedder, LocalEmbedder)

    def test_create_embedder_local_provider(self):
        """provider='local' should return LocalEmbedder."""
        from docvector.embeddings import LocalEmbedder, create_embedder

        embedder = create_embedder(provider="local")
        assert isinstance(embedder, LocalEmbedder)

    def test_create_embedder_openai_provider(self):
        """provider='openai' should return OpenAIEmbedder.

        Note: OpenAI embedder requires API key at init time.
        We test the class type directly to avoid API key requirement.
        """
        from docvector.embeddings import OpenAIEmbedder

        # Create directly with a fake key to test the type
        embedder = OpenAIEmbedder(api_key="test-key-for-testing")
        assert isinstance(embedder, OpenAIEmbedder)

    def test_create_embedder_specific_model(self):
        """Should accept specific model parameter."""
        from docvector.embeddings import create_embedder

        embedder = create_embedder(model="BAAI/bge-small-en-v1.5")
        assert embedder.model_name == "BAAI/bge-small-en-v1.5"

    def test_create_embedder_with_device(self):
        """Should accept device parameter."""
        from docvector.embeddings import create_embedder

        embedder = create_embedder(device="cuda")
        assert embedder.device == "cuda"

    def test_create_embedder_with_batch_size(self):
        """Should accept batch_size parameter."""
        from docvector.embeddings import create_embedder

        embedder = create_embedder(batch_size=64)
        assert embedder.batch_size == 64

    def test_create_embedder_with_all_params(self):
        """Should accept all parameters together."""
        from docvector.embeddings import LocalEmbedder, create_embedder

        embedder = create_embedder(
            provider="local",
            model="BAAI/bge-base-en-v1.5",
            device="cpu",
            batch_size=16,
        )
        assert isinstance(embedder, LocalEmbedder)
        assert embedder.model_name == "BAAI/bge-base-en-v1.5"
        assert embedder.device == "cpu"
        assert embedder.batch_size == 16

    def test_create_embedder_invalid_model(self):
        """Should raise ValueError for invalid model."""
        from docvector.embeddings import create_embedder

        with pytest.raises(ValueError, match="Unknown model"):
            create_embedder(model="invalid-model-name")


class TestGetEmbedderInfo:
    """Tests for get_embedder_info function."""

    def test_get_embedder_info_returns_dict(self):
        """Should return a dictionary."""
        from docvector.embeddings import get_embedder_info

        info = get_embedder_info()
        assert isinstance(info, dict)

    def test_get_embedder_info_has_required_keys(self):
        """Should contain required keys."""
        from docvector.embeddings import get_embedder_info

        info = get_embedder_info()
        assert "provider" in info
        assert "model" in info
        assert "dimension" in info
        assert "device" in info
        assert "batch_size" in info
        assert "is_registered" in info
        assert "model_info" in info

    def test_get_embedder_info_default_model(self):
        """Should return info for default model."""
        from docvector.embeddings import DEFAULT_MODEL, get_embedder_info

        info = get_embedder_info()
        # Default model should be registered
        assert info["is_registered"] is True
        assert info["dimension"] == 384  # MiniLM dimension

    def test_get_embedder_info_model_info_structure(self):
        """model_info should have correct structure."""
        from docvector.embeddings import get_embedder_info

        info = get_embedder_info()
        model_info = info["model_info"]
        assert model_info is not None
        assert "name" in model_info
        assert "quality" in model_info
        assert "speed" in model_info
        assert "memory_mb" in model_info
        assert "description" in model_info


class TestRegistryFunctionsFromModule:
    """Tests for registry functions exported from module."""

    def test_get_model_dimension(self):
        """get_model_dimension should work correctly."""
        from docvector.embeddings import get_model_dimension

        assert get_model_dimension("sentence-transformers/all-MiniLM-L6-v2") == 384
        assert get_model_dimension("BAAI/bge-base-en-v1.5") == 768

    def test_get_model_info(self):
        """get_model_info should work correctly."""
        from docvector.embeddings import get_model_info

        info = get_model_info("sentence-transformers/all-MiniLM-L6-v2")
        assert info is not None
        assert info.dimension == 384

    def test_validate_model(self):
        """validate_model should work correctly."""
        from docvector.embeddings import validate_model

        is_valid, _ = validate_model("sentence-transformers/all-MiniLM-L6-v2")
        assert is_valid is True

        is_valid, _ = validate_model("invalid")
        assert is_valid is False

    def test_list_models(self):
        """list_models should work correctly."""
        from docvector.embeddings import list_models

        models = list_models()
        assert len(models) >= 8

    def test_get_recommended_model(self):
        """get_recommended_model should work correctly."""
        from docvector.embeddings import get_recommended_model

        model = get_recommended_model("general")
        assert model is not None
