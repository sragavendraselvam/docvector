"""Tests for embedding model registry."""

import pytest

from docvector.embeddings.registry import (
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


class TestModelRegistry:
    """Tests for EMBEDDING_MODELS registry."""

    def test_registry_not_empty(self):
        """Registry should contain at least 8 models."""
        assert len(EMBEDDING_MODELS) >= 8

    def test_default_model_in_registry(self):
        """Default model should be registered."""
        assert DEFAULT_MODEL in EMBEDDING_MODELS

    def test_all_models_have_required_fields(self):
        """All models should have valid required fields."""
        for name, info in EMBEDDING_MODELS.items():
            assert info.name, f"Model {name} missing name"
            assert info.dimension > 0, f"Model {name} has invalid dimension"
            assert info.provider, f"Model {name} missing provider"
            assert isinstance(info.speed, ModelSpeed), f"Model {name} has invalid speed"
            assert isinstance(
                info.quality, ModelQuality
            ), f"Model {name} has invalid quality"
            assert info.memory_mb >= 0, f"Model {name} has invalid memory_mb"
            assert info.description, f"Model {name} missing description"
            assert len(info.use_cases) > 0, f"Model {name} has no use cases"

    def test_model_dimensions_are_accurate(self):
        """Known model dimensions should be correct."""
        known_dims = {
            "sentence-transformers/all-MiniLM-L6-v2": 384,
            "sentence-transformers/all-mpnet-base-v2": 768,
            "BAAI/bge-base-en-v1.5": 768,
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-large-en-v1.5": 1024,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }
        for model, expected_dim in known_dims.items():
            info = get_model_info(model)
            assert info is not None, f"Model {model} not in registry"
            assert (
                info.dimension == expected_dim
            ), f"Model {model} dimension mismatch: expected {expected_dim}, got {info.dimension}"

    def test_registry_has_local_and_openai_models(self):
        """Registry should contain both local and OpenAI models."""
        providers = {info.provider for info in EMBEDDING_MODELS.values()}
        assert "sentence-transformers" in providers
        assert "openai" in providers

    def test_registry_has_models_of_each_speed(self):
        """Registry should have models for each speed category."""
        speeds = {info.speed for info in EMBEDDING_MODELS.values()}
        assert ModelSpeed.FAST in speeds
        assert ModelSpeed.MEDIUM in speeds
        assert ModelSpeed.SLOW in speeds


class TestGetModelInfo:
    """Tests for get_model_info function."""

    def test_registered_model(self):
        """Should return info for registered models."""
        info = get_model_info("sentence-transformers/all-MiniLM-L6-v2")
        assert info is not None
        assert info.dimension == 384
        assert info.provider == "sentence-transformers"

    def test_unregistered_model(self):
        """Should return None for unregistered models."""
        info = get_model_info("unknown/model")
        assert info is None

    def test_empty_model_name(self):
        """Should return None for empty string."""
        info = get_model_info("")
        assert info is None

    def test_returns_correct_model_info_type(self):
        """Should return EmbeddingModelInfo instance."""
        info = get_model_info(DEFAULT_MODEL)
        assert isinstance(info, EmbeddingModelInfo)


class TestGetModelDimension:
    """Tests for get_model_dimension function."""

    def test_registered_model(self):
        """Should return correct dimension for registered models."""
        assert get_model_dimension("sentence-transformers/all-MiniLM-L6-v2") == 384

    def test_bge_base_model(self):
        """Should return correct dimension for BGE base."""
        assert get_model_dimension("BAAI/bge-base-en-v1.5") == 768

    def test_openai_model(self):
        """Should return correct dimension for OpenAI models."""
        assert get_model_dimension("text-embedding-3-small") == 1536
        assert get_model_dimension("text-embedding-3-large") == 3072

    def test_legacy_openai_model(self):
        """Should return correct dimension for legacy ada model."""
        assert get_model_dimension("text-embedding-ada-002") == 1536

    def test_unknown_model_returns_default(self):
        """Should return default dimension (384) for unknown models."""
        assert get_model_dimension("unknown/model") == 384

    def test_empty_model_returns_default(self):
        """Should return default dimension for empty string."""
        assert get_model_dimension("") == 384


class TestValidateModel:
    """Tests for validate_model function."""

    def test_registered_model_valid(self):
        """Registered models should be valid with no warning."""
        is_valid, message = validate_model("sentence-transformers/all-MiniLM-L6-v2")
        assert is_valid is True
        assert message is None

    def test_all_registered_models_valid(self):
        """All registered models should validate successfully."""
        for model_name in EMBEDDING_MODELS.keys():
            is_valid, message = validate_model(model_name)
            assert is_valid is True, f"Model {model_name} should be valid"
            assert message is None, f"Model {model_name} should have no warning"

    def test_custom_huggingface_model(self):
        """Custom HuggingFace models should be valid with warning."""
        is_valid, message = validate_model("custom-org/my-model")
        assert is_valid is True
        assert message is not None
        assert "custom model" in message.lower()
        assert "auto-detect" in message.lower()

    def test_custom_model_various_formats(self):
        """Various valid HuggingFace formats should work."""
        valid_customs = [
            "organization/model-name",
            "user/embedding-v1",
            "BAAI/new-model",
            "intfloat/multilingual-e5-base",
        ]
        for model in valid_customs:
            is_valid, _ = validate_model(model)
            assert is_valid is True, f"Model {model} should be valid"

    def test_openai_pattern_model(self):
        """OpenAI-style models should be valid."""
        is_valid, message = validate_model("text-embedding-ada-002")
        assert is_valid is True
        assert message is None

    def test_invalid_model_no_slash(self):
        """Models without proper format should be invalid."""
        is_valid, message = validate_model("not-a-valid-model")
        assert is_valid is False
        assert message is not None
        assert "Unknown model" in message

    def test_invalid_model_empty_parts(self):
        """Models with empty org or name should be invalid."""
        is_valid, message = validate_model("/just-name")
        assert is_valid is False

        is_valid, message = validate_model("just-org/")
        assert is_valid is False

    def test_invalid_model_too_many_slashes(self):
        """Models with too many slashes should be invalid."""
        is_valid, message = validate_model("org/sub/model")
        assert is_valid is False

    def test_empty_model_invalid(self):
        """Empty string should be invalid."""
        is_valid, message = validate_model("")
        assert is_valid is False


class TestListModels:
    """Tests for list_models function."""

    def test_list_all_models(self):
        """Should return all models when no filters."""
        models = list_models()
        assert len(models) == len(EMBEDDING_MODELS)

    def test_filter_by_provider_sentence_transformers(self):
        """Should filter by sentence-transformers provider."""
        models = list_models(provider="sentence-transformers")
        assert len(models) > 0
        for model in models:
            info = get_model_info(model)
            assert info.provider == "sentence-transformers"

    def test_filter_by_provider_openai(self):
        """Should filter by OpenAI provider."""
        models = list_models(provider="openai")
        assert len(models) >= 2  # At least 2 OpenAI models
        for model in models:
            info = get_model_info(model)
            assert info.provider == "openai"

    def test_filter_by_speed_fast(self):
        """Should filter by FAST speed."""
        models = list_models(speed=ModelSpeed.FAST)
        assert len(models) > 0
        for model in models:
            info = get_model_info(model)
            assert info.speed == ModelSpeed.FAST

    def test_filter_by_speed_medium(self):
        """Should filter by MEDIUM speed."""
        models = list_models(speed=ModelSpeed.MEDIUM)
        assert len(models) > 0
        for model in models:
            info = get_model_info(model)
            assert info.speed == ModelSpeed.MEDIUM

    def test_filter_by_min_quality_excellent(self):
        """Should filter by minimum EXCELLENT quality."""
        models = list_models(min_quality=ModelQuality.EXCELLENT)
        assert len(models) > 0
        for model in models:
            info = get_model_info(model)
            assert info.quality == ModelQuality.EXCELLENT

    def test_filter_by_min_quality_good(self):
        """Should include GOOD and EXCELLENT quality models."""
        models = list_models(min_quality=ModelQuality.GOOD)
        for model in models:
            info = get_model_info(model)
            assert info.quality in [ModelQuality.GOOD, ModelQuality.EXCELLENT]

    def test_combined_filters(self):
        """Should support combined filters."""
        models = list_models(
            provider="sentence-transformers",
            speed=ModelSpeed.FAST,
        )
        for model in models:
            info = get_model_info(model)
            assert info.provider == "sentence-transformers"
            assert info.speed == ModelSpeed.FAST

    def test_no_matches_returns_empty_list(self):
        """Should return empty list if no models match."""
        models = list_models(provider="nonexistent-provider")
        assert models == []


class TestGetRecommendedModel:
    """Tests for get_recommended_model function."""

    def test_general_use_case(self):
        """Should return default model for general use case."""
        model = get_recommended_model("general")
        assert model == "sentence-transformers/all-MiniLM-L6-v2"

    def test_technical_use_case(self):
        """Should return BGE base for technical use case."""
        model = get_recommended_model("technical")
        assert model == "BAAI/bge-base-en-v1.5"

    def test_code_use_case(self):
        """Should return BGE small for code use case."""
        model = get_recommended_model("code")
        assert model == "BAAI/bge-small-en-v1.5"

    def test_documentation_use_case(self):
        """Should return MiniLM for documentation use case."""
        model = get_recommended_model("documentation")
        assert model == "sentence-transformers/all-MiniLM-L6-v2"

    def test_production_use_case(self):
        """Should return OpenAI model for production use case."""
        model = get_recommended_model("production")
        assert model == "text-embedding-3-small"

    def test_high_precision_use_case(self):
        """Should return BGE large for high-precision use case."""
        model = get_recommended_model("high-precision")
        assert model == "BAAI/bge-large-en-v1.5"

    def test_unknown_use_case_returns_default(self):
        """Should return default model for unknown use case."""
        model = get_recommended_model("unknown-use-case")
        assert model == DEFAULT_MODEL

    def test_default_argument(self):
        """Should default to general use case."""
        model = get_recommended_model()
        assert model == get_recommended_model("general")

    def test_all_recommended_models_are_registered(self):
        """All recommended models should be in registry."""
        use_cases = [
            "general",
            "technical",
            "code",
            "documentation",
            "production",
            "high-precision",
        ]
        for use_case in use_cases:
            model = get_recommended_model(use_case)
            assert model in EMBEDDING_MODELS, f"Recommended model {model} not registered"


class TestEnums:
    """Tests for ModelSpeed and ModelQuality enums."""

    def test_model_speed_values(self):
        """ModelSpeed enum should have correct values."""
        assert ModelSpeed.FAST.value == "fast"
        assert ModelSpeed.MEDIUM.value == "medium"
        assert ModelSpeed.SLOW.value == "slow"

    def test_model_quality_values(self):
        """ModelQuality enum should have correct values."""
        assert ModelQuality.BASIC.value == "basic"
        assert ModelQuality.GOOD.value == "good"
        assert ModelQuality.EXCELLENT.value == "excellent"

    def test_speed_ordering(self):
        """Speed enum should support comparison for ordering."""
        speeds = list(ModelSpeed)
        assert len(speeds) == 3

    def test_quality_ordering(self):
        """Quality enum should support comparison for ordering."""
        qualities = list(ModelQuality)
        assert len(qualities) == 3


class TestEmbeddingModelInfo:
    """Tests for EmbeddingModelInfo dataclass."""

    def test_create_model_info(self):
        """Should create model info with all fields."""
        info = EmbeddingModelInfo(
            name="test-model",
            dimension=512,
            speed=ModelSpeed.FAST,
            quality=ModelQuality.GOOD,
            memory_mb=200,
            description="A test model",
            provider="test",
            use_cases=["testing"],
        )
        assert info.name == "test-model"
        assert info.dimension == 512
        assert info.max_tokens == 512  # default value

    def test_custom_max_tokens(self):
        """Should allow custom max_tokens."""
        info = EmbeddingModelInfo(
            name="test",
            dimension=384,
            speed=ModelSpeed.FAST,
            quality=ModelQuality.GOOD,
            memory_mb=100,
            description="Test",
            provider="test",
            use_cases=["test"],
            max_tokens=1024,
        )
        assert info.max_tokens == 1024
