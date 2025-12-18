"""Tests for core.py Settings class."""

import pytest


def create_settings(**env_overrides):
    """Create Settings instance with environment overrides.

    Pydantic-settings reads from environment at instantiation time,
    so we need to manipulate the environment before creating Settings.
    """
    # Import here to avoid caching issues
    from docvector.core import Settings

    # Create with explicit values to avoid environment pollution
    return Settings(**env_overrides)


class TestSettingsDefaults:
    """Tests for default Settings values."""

    def test_default_mode_is_local(self):
        """Default mode should be 'local'."""
        settings = create_settings()
        assert settings.docvector_mode == "local"

    def test_default_local_data_dir(self):
        """Default local data directory should be './docvector_data'."""
        settings = create_settings()
        assert settings.local_data_dir == "./docvector_data"

    def test_default_vector_collection(self):
        """Default vector collection should be 'documents'."""
        settings = create_settings()
        assert settings.vector_collection == "documents"


class TestModeProperties:
    """Tests for mode-related properties."""

    def test_is_local_mode_true(self):
        """is_local_mode should be True when mode is 'local'."""
        settings = create_settings(docvector_mode="local")
        assert settings.is_local_mode is True
        assert settings.is_cloud_mode is False
        assert settings.is_hybrid_mode is False

    def test_is_cloud_mode_true(self):
        """is_cloud_mode should be True when mode is 'cloud'."""
        settings = create_settings(docvector_mode="cloud")
        assert settings.is_local_mode is False
        assert settings.is_cloud_mode is True
        assert settings.is_hybrid_mode is False

    def test_is_hybrid_mode_true(self):
        """is_hybrid_mode should be True when mode is 'hybrid'."""
        settings = create_settings(docvector_mode="hybrid")
        assert settings.is_local_mode is False
        assert settings.is_cloud_mode is False
        assert settings.is_hybrid_mode is True

    def test_default_is_local_mode(self):
        """Default mode should result in is_local_mode True."""
        settings = create_settings()
        assert settings.is_local_mode is True


class TestEffectiveDatabaseUrl:
    """Tests for effective_database_url property."""

    def test_local_mode_uses_sqlite(self, tmp_path):
        """Local mode should use SQLite database URL."""
        settings = create_settings(
            docvector_mode="local",
            local_data_dir=str(tmp_path),
        )

        assert "sqlite+aiosqlite" in settings.effective_database_url
        assert str(tmp_path) in settings.effective_database_url
        assert "docvector.db" in settings.effective_database_url

    def test_cloud_mode_uses_configured_url(self):
        """Cloud mode should use the configured database URL."""
        settings = create_settings(
            docvector_mode="cloud",
            database_url="postgresql+asyncpg://localhost/testdb",
        )

        assert settings.effective_database_url == "postgresql+asyncpg://localhost/testdb"

    def test_hybrid_mode_uses_configured_url(self):
        """Hybrid mode should use the configured database URL."""
        settings = create_settings(
            docvector_mode="hybrid",
            database_url="postgresql+asyncpg://localhost/hybriddb",
        )

        assert (
            settings.effective_database_url == "postgresql+asyncpg://localhost/hybriddb"
        )


class TestEffectiveVectorStoreType:
    """Tests for effective_vector_store_type property."""

    def test_local_mode_uses_chroma(self):
        """Local mode should use ChromaDB."""
        settings = create_settings(docvector_mode="local")

        assert settings.effective_vector_store_type == "chroma"

    def test_cloud_mode_uses_qdrant(self):
        """Cloud mode should use Qdrant."""
        settings = create_settings(docvector_mode="cloud")

        assert settings.effective_vector_store_type == "qdrant"

    def test_hybrid_mode_uses_qdrant(self):
        """Hybrid mode should use Qdrant."""
        settings = create_settings(docvector_mode="hybrid")

        assert settings.effective_vector_store_type == "qdrant"


class TestEnsureLocalDirectories:
    """Tests for ensure_local_directories method."""

    def test_creates_directories_in_local_mode(self, tmp_path):
        """Should create directory structure in local mode."""
        settings = create_settings(
            docvector_mode="local",
            local_data_dir=str(tmp_path / "data"),
        )

        settings.ensure_local_directories()

        base = tmp_path / "data"
        assert (base / "db").exists()
        assert (base / "vectors" / "chroma").exists()
        assert (base / "cache").exists()
        assert (base / "logs").exists()

    def test_does_nothing_in_cloud_mode(self, tmp_path):
        """Should not create directories in cloud mode."""
        settings = create_settings(
            docvector_mode="cloud",
            local_data_dir=str(tmp_path / "data"),
        )

        settings.ensure_local_directories()

        base = tmp_path / "data"
        assert not base.exists()

    def test_does_nothing_in_hybrid_mode(self, tmp_path):
        """Should not create directories in hybrid mode."""
        settings = create_settings(
            docvector_mode="hybrid",
            local_data_dir=str(tmp_path / "data"),
        )

        settings.ensure_local_directories()

        base = tmp_path / "data"
        assert not base.exists()

    def test_idempotent_directory_creation(self, tmp_path):
        """Calling ensure_local_directories multiple times should be safe."""
        settings = create_settings(
            docvector_mode="local",
            local_data_dir=str(tmp_path / "data"),
        )

        # Call multiple times
        settings.ensure_local_directories()
        settings.ensure_local_directories()
        settings.ensure_local_directories()

        # Directories should still exist
        base = tmp_path / "data"
        assert (base / "db").exists()


class TestValidateMode:
    """Tests for validate_mode method."""

    def test_valid_local_mode(self):
        """Local mode should pass validation."""
        settings = create_settings(docvector_mode="local")

        # Should not raise
        settings.validate_mode()

    def test_valid_cloud_mode_with_postgresql(self):
        """Cloud mode with PostgreSQL URL should pass validation."""
        settings = create_settings(
            docvector_mode="cloud",
            database_url="postgresql+asyncpg://localhost/db",
        )

        # Should not raise
        settings.validate_mode()

    def test_valid_hybrid_mode(self):
        """Hybrid mode should pass validation."""
        settings = create_settings(docvector_mode="hybrid")

        # Should not raise
        settings.validate_mode()

    def test_invalid_mode_raises_error(self):
        """Invalid mode should raise ValueError."""
        settings = create_settings(docvector_mode="invalid")

        with pytest.raises(ValueError) as exc_info:
            settings.validate_mode()

        assert "Invalid DOCVECTOR_MODE" in str(exc_info.value)
        assert "invalid" in str(exc_info.value)

    def test_cloud_mode_with_sqlite_raises_error(self):
        """Cloud mode with SQLite URL should raise ValueError."""
        settings = create_settings(
            docvector_mode="cloud",
            database_url="sqlite+aiosqlite:///test.db",
        )

        with pytest.raises(ValueError) as exc_info:
            settings.validate_mode()

        assert "Cloud mode requires a PostgreSQL database URL" in str(exc_info.value)


class TestEnvironmentVariables:
    """Tests for environment variable configuration.

    Note: pydantic-settings reads environment at Settings() instantiation.
    These tests verify that the Settings class correctly defines env var names.
    """

    def test_settings_uses_docvector_prefix(self):
        """Settings should use DOCVECTOR_ prefix for environment variables."""
        from docvector.core import Settings

        assert Settings.model_config.get("env_prefix") == "DOCVECTOR_"

    def test_mode_field_exists(self):
        """docvector_mode field should exist and have correct default."""
        from docvector.core import Settings

        # Verify field exists via model_fields
        assert "docvector_mode" in Settings.model_fields
        assert Settings.model_fields["docvector_mode"].default == "local"

    def test_local_data_dir_field_exists(self):
        """local_data_dir field should exist and have correct default."""
        from docvector.core import Settings

        assert "local_data_dir" in Settings.model_fields
        assert Settings.model_fields["local_data_dir"].default == "./docvector_data"

    def test_vector_collection_field_exists(self):
        """vector_collection field should exist and have correct default."""
        from docvector.core import Settings

        assert "vector_collection" in Settings.model_fields
        assert Settings.model_fields["vector_collection"].default == "documents"


class TestBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_database_url_still_configurable(self):
        """Original database_url should still be configurable."""
        settings = create_settings(
            database_url="postgresql+asyncpg://custom/db",
        )
        assert settings.database_url == "postgresql+asyncpg://custom/db"

    def test_qdrant_settings_still_work(self):
        """Qdrant settings should still work."""
        settings = create_settings(
            qdrant_host="qdrant.example.com",
            qdrant_port=6334,
        )
        assert settings.qdrant_host == "qdrant.example.com"
        assert settings.qdrant_port == 6334

    def test_embedding_settings_still_work(self):
        """Embedding settings should still work."""
        settings = create_settings(
            embedding_model="BAAI/bge-small-en-v1.5",
        )
        assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
