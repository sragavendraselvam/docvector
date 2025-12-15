"""Tests for vector database factory."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docvector.vectordb import (
    ChromaVectorDB,
    QdrantVectorDB,
    VectorDBConfigurationError,
    get_vector_db,
)


class TestVectorDBFactory:
    """Test vector database factory function."""

    def test_get_vector_db_local_mode(self):
        """Test factory returns ChromaDB for local mode."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = "./data/chroma"

            db = get_vector_db()

            assert isinstance(db, ChromaVectorDB)
            assert db.persist_directory == "./data/chroma"

    def test_get_vector_db_cloud_mode_self_hosted(self):
        """Test factory returns Qdrant for cloud mode (self-hosted)."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 6333
            mock_settings.qdrant_grpc_port = 6334
            mock_settings.qdrant_use_grpc = False

            db = get_vector_db()

            assert isinstance(db, QdrantVectorDB)
            assert db.host == "localhost"
            assert db.port == 6333

    def test_get_vector_db_cloud_mode_cloud_hosted(self):
        """Test factory returns Qdrant for cloud mode (cloud hosted)."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = "https://test.cloud.qdrant.io"
            mock_settings.qdrant_api_key = "test-key"

            db = get_vector_db()

            assert isinstance(db, QdrantVectorDB)
            assert db.url == "https://test.cloud.qdrant.io"
            assert db.api_key == "test-key"

    def test_get_vector_db_hybrid_mode(self):
        """Test factory returns Qdrant for hybrid mode."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "hybrid"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 6333
            mock_settings.qdrant_grpc_port = 6334
            mock_settings.qdrant_use_grpc = True

            db = get_vector_db()

            assert isinstance(db, QdrantVectorDB)
            assert db.use_grpc is True

    def test_get_vector_db_mode_override(self):
        """Test factory respects mode override parameter."""
        with patch("docvector.vectordb.settings") as mock_settings:
            # Settings say cloud, but we override to local
            mock_settings.mcp_mode = "cloud"
            mock_settings.chroma_persist_directory = "./data/chroma"

            db = get_vector_db(mode="local")

            assert isinstance(db, ChromaVectorDB)

    def test_get_vector_db_invalid_mode(self):
        """Test factory raises error for invalid mode."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "invalid"

            with pytest.raises(ValueError, match="Invalid vector database mode"):
                get_vector_db()

    def test_get_vector_db_invalid_mode_override(self):
        """Test factory raises error for invalid mode override."""
        with pytest.raises(ValueError, match="Invalid vector database mode"):
            get_vector_db(mode="invalid")


class TestChromaDBConfigValidation:
    """Test ChromaDB configuration validation."""

    def test_validate_chroma_missing_directory(self):
        """Test validation fails when persist directory not configured."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = None

            with pytest.raises(VectorDBConfigurationError, match="persist directory not configured"):
                get_vector_db()

    def test_validate_chroma_unwritable_parent(self, tmp_path):
        """Test validation fails when parent directory not writable."""
        import os
        import stat

        # Create read-only parent directory
        readonly_parent = tmp_path / "readonly"
        readonly_parent.mkdir()
        os.chmod(readonly_parent, stat.S_IRUSR | stat.S_IXUSR)  # r-x------

        persist_dir = str(readonly_parent / "chroma")

        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = persist_dir

            try:
                with pytest.raises(VectorDBConfigurationError, match="not writable"):
                    get_vector_db()
            finally:
                # Restore permissions for cleanup
                os.chmod(readonly_parent, stat.S_IRWXU)

    def test_validate_chroma_valid_config(self, tmp_path):
        """Test validation passes with valid configuration."""
        persist_dir = str(tmp_path / "chroma")

        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = persist_dir

            db = get_vector_db()

            assert isinstance(db, ChromaVectorDB)
            assert db.persist_directory == persist_dir


class TestQdrantConfigValidation:
    """Test Qdrant configuration validation."""

    def test_validate_qdrant_url_without_api_key(self):
        """Test validation fails when URL provided without API key."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = "https://test.cloud.qdrant.io"
            mock_settings.qdrant_api_key = None

            with pytest.raises(VectorDBConfigurationError, match="URL provided but API key missing"):
                get_vector_db()

    def test_validate_qdrant_api_key_without_url(self):
        """Test validation fails when API key provided without URL."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = "test-key"

            with pytest.raises(VectorDBConfigurationError, match="API key provided but URL missing"):
                get_vector_db()

    def test_validate_qdrant_missing_host(self):
        """Test validation fails when host not configured for self-hosted."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = None

            with pytest.raises(VectorDBConfigurationError, match="host not configured"):
                get_vector_db()

    def test_validate_qdrant_invalid_port(self):
        """Test validation fails with invalid port."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = -1

            with pytest.raises(VectorDBConfigurationError, match="Invalid Qdrant port"):
                get_vector_db()

    def test_validate_qdrant_zero_port(self):
        """Test validation fails with zero port."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 0

            with pytest.raises(VectorDBConfigurationError, match="Invalid Qdrant port"):
                get_vector_db()

    def test_validate_qdrant_cloud_valid_config(self):
        """Test validation passes with valid cloud configuration."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = "https://test.cloud.qdrant.io"
            mock_settings.qdrant_api_key = "test-key"

            db = get_vector_db()

            assert isinstance(db, QdrantVectorDB)
            assert db.url == "https://test.cloud.qdrant.io"
            assert db.api_key == "test-key"

    def test_validate_qdrant_self_hosted_valid_config(self):
        """Test validation passes with valid self-hosted configuration."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 6333
            mock_settings.qdrant_grpc_port = 6334
            mock_settings.qdrant_use_grpc = False

            db = get_vector_db()

            assert isinstance(db, QdrantVectorDB)
            assert db.host == "localhost"
            assert db.port == 6333


class TestFactoryErrorHandling:
    """Test factory error handling."""

    def test_factory_wraps_unexpected_errors(self):
        """Test factory wraps unexpected errors in VectorDBConfigurationError."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = "./data/chroma"

            with patch("docvector.vectordb.ChromaVectorDB") as mock_chroma:
                mock_chroma.side_effect = RuntimeError("Unexpected error")

                with pytest.raises(VectorDBConfigurationError, match="Failed to create vector database"):
                    get_vector_db()

    def test_factory_reraises_configuration_errors(self):
        """Test factory re-raises VectorDBConfigurationError as-is."""
        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = None

            with pytest.raises(VectorDBConfigurationError, match="persist directory not configured"):
                get_vector_db()


class TestFactoryLogging:
    """Test factory logging behavior."""

    def test_factory_logs_initialization(self, caplog):
        """Test factory logs initialization."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = "./data/chroma"

            get_vector_db()

            # Check that we logged the mode selection
            log_messages = [record.message for record in caplog.records]
            assert any("Initializing vector database" in msg for msg in log_messages)

    def test_factory_logs_chroma_creation(self, caplog):
        """Test factory logs ChromaDB instance creation."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "local"
            mock_settings.chroma_persist_directory = "./data/chroma"

            get_vector_db()

            # Check that we logged ChromaDB usage
            log_messages = [record.message for record in caplog.records]
            assert any("Using ChromaDB" in msg for msg in log_messages)
            assert any("ChromaDB instance created" in msg for msg in log_messages)

    def test_factory_logs_qdrant_creation(self, caplog):
        """Test factory logs Qdrant instance creation."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("docvector.vectordb.settings") as mock_settings:
            mock_settings.mcp_mode = "cloud"
            mock_settings.qdrant_url = None
            mock_settings.qdrant_api_key = None
            mock_settings.qdrant_host = "localhost"
            mock_settings.qdrant_port = 6333
            mock_settings.qdrant_grpc_port = 6334
            mock_settings.qdrant_use_grpc = False

            get_vector_db()

            # Check that we logged Qdrant usage
            log_messages = [record.message for record in caplog.records]
            assert any("Using Qdrant" in msg for msg in log_messages)
            assert any("Qdrant self-hosted instance created" in msg for msg in log_messages)
