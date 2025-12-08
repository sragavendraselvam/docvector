"""Unit tests for CLI commands.

Tests cover:
- init command (config creation, directory setup)
- stats command (data format, error handling)
- config file loading and merging
- edge cases (missing config, invalid YAML, permissions)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from docvector.cli import app
from docvector.core import Settings


# Test fixtures
@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / ".docvector"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_local_dir(tmp_path):
    """Create a temporary local directory."""
    return tmp_path


@pytest.fixture
def sample_config():
    """Sample configuration dictionary."""
    return {
        "chunk_size": 2000,
        "chunk_overlap": 400,
        "redis_url": "redis://localhost:6380/0",
        "embedding_provider": "local",
    }


# =============================================================================
# INIT COMMAND TESTS
# =============================================================================

class TestInitCommand:
    """Tests for the init command."""
    
    def test_init_creates_global_config(self, cli_runner, temp_config_dir, monkeypatch):
        """Test that init creates global config directory and file."""
        # Mock the config path
        monkeypatch.setattr("docvector.config.get_global_config_path", lambda: temp_config_dir / "config.yaml")
        
        # Run init command
        result = cli_runner.invoke(app, ["init", "--force"])
        
        # Check command succeeded
        assert result.exit_code == 0, f"Command failed: {result.stdout}"
        
        # Check config file was created
        config_file = temp_config_dir / "config.yaml"
        assert config_file.exists(), "Config file not created"
        
        # Check file contains valid YAML
        with open(config_file) as f:
            config = yaml.safe_load(f)
            assert isinstance(config, dict), "Config is not a dict"
            assert "chunk_size" in config, "Missing chunk_size in config"
    
    def test_init_creates_local_config(self, cli_runner, temp_local_dir, monkeypatch):
        """Test that init --local creates local config file."""
        # Mock the local config path
        monkeypatch.setattr("docvector.config.get_local_config_path", lambda: temp_local_dir / "docvector.yaml")
        
        # Run init with --local flag
        result = cli_runner.invoke(app, ["init", "--local", "--force"])
        
        # Check command succeeded
        assert result.exit_code == 0
        
        # Check local config was created
        config_file = temp_local_dir / "docvector.yaml"
        assert config_file.exists(), "Local config file not created"
    
    def test_init_force_overwrites_existing(self, cli_runner, temp_config_dir, monkeypatch):
        """Test that --force overwrites existing config."""
        config_file = temp_config_dir / "config.yaml"
        
        # Create existing config
        with open(config_file, "w") as f:
            yaml.dump({"chunk_size": 500}, f)
        
        # Mock the config path
        monkeypatch.setattr("docvector.config.get_global_config_path", lambda: config_file)
        
        # Run init with --force
        result = cli_runner.invoke(app, ["init", "--force"])
        
        assert result.exit_code == 0
        
        # Check config was overwritten
        with open(config_file) as f:
            config = yaml.safe_load(f)
            # Default chunk_size is 1000, not 500
            assert config.get("chunk_size") != 500
    
    def test_init_interactive_mode(self, cli_runner, temp_config_dir, monkeypatch):
        """Test interactive mode prompts for configuration."""
        monkeypatch.setattr("docvector.config.get_global_config_path", lambda: temp_config_dir / "config.yaml")
        
        # Provide inputs for interactive prompts
        inputs = [
            "local",  # embedding_provider
            "",       # embedding_model (use default)
            "",       # database_url (use default)
            "",       # redis_url (use default)
            "",       # qdrant_host (use default)
            "",       # qdrant_port (use default)
            "",       # chunk_size (use default)
            "",       # chunk_overlap (use default)
        ]
        
        result = cli_runner.invoke(app, ["init", "--interactive", "--force"], input="\n".join(inputs))
        
        # Should succeed
        assert result.exit_code == 0


# =============================================================================
# STATS COMMAND TESTS
# =============================================================================

class TestStatsCommand:
    """Tests for the stats command."""
    
    @patch("docvector.cli.get_db_session")
    @patch("docvector.cli.QdrantVectorDB")
    def test_stats_returns_correct_format(self, mock_qdrant, mock_db_session, cli_runner):
        """Test that stats command returns data in correct format."""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session
        
        # Mock library and source services
        with patch("docvector.cli.LibraryService") as mock_lib_service, \
             patch("docvector.cli.SourceService") as mock_source_service:
            
            # Setup service mocks
            mock_lib_instance = mock_lib_service.return_value
            mock_lib_instance.list_libraries = AsyncMock(return_value=[])
            
            mock_source_instance = mock_source_service.return_value
            mock_source_instance.list_sources = AsyncMock(return_value=[])
            
            # Mock database queries
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            mock_session.execute = AsyncMock(return_value=mock_result)
            
            # Mock Qdrant
            mock_qdrant_instance = mock_qdrant.return_value
            mock_qdrant_instance.get_collection_info = AsyncMock(return_value={
                "name": "documents",
                "vectors_count": 100,
                "points_count": 100,
                "vector_size": 384,
                "distance": "COSINE",
                "status": "green"
            })
            
            # Run stats command
            result = cli_runner.invoke(app, ["stats"])
            
            # Should succeed
            assert result.exit_code == 0
            assert "Statistics" in result.stdout or "Indexed Content" in result.stdout
    
    @patch("docvector.cli.get_db_session")
    def test_stats_handles_database_error(self, mock_db_session, cli_runner):
        """Test that stats handles database connection errors gracefully."""
        # Make database session fail
        mock_db_session.side_effect = Exception("Database connection failed")
        
        # Run stats command
        result = cli_runner.invoke(app, ["stats"])
        
        # Should handle error gracefully (may exit with error code)
        assert "error" in result.stdout.lower() or result.exit_code != 0


# =============================================================================
# CONFIG LOADING TESTS
# =============================================================================

class TestConfigLoading:
    """Tests for config file loading and merging."""
    
    def test_load_yaml_config_valid_file(self, temp_config_dir, sample_config):
        """Test loading a valid YAML config file."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(sample_config, f)
        
        # Load config
        loaded = load_yaml_config(config_file)
        
        assert loaded == sample_config
        assert loaded["chunk_size"] == 2000
    
    def test_load_yaml_config_missing_file(self, temp_config_dir):
        """Test loading a non-existent config file."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "nonexistent.yaml"
        
        # Should return empty dict, not raise exception
        loaded = load_yaml_config(config_file)
        
        assert loaded == {}
    
    def test_load_yaml_config_invalid_yaml(self, temp_config_dir):
        """Test loading a file with invalid YAML syntax."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "invalid.yaml"
        with open(config_file, "w") as f:
            f.write("invalid: [yaml\nno closing bracket")
        
        # Should return empty dict and log warning
        loaded = load_yaml_config(config_file)
        
        assert loaded == {}
    
    def test_merge_config_precedence(self):
        """Test that config merging respects precedence."""
        from docvector.config import merge_config
        
        base = {"chunk_size": 1000, "redis_url": "redis://localhost:6379/0"}
        override = {"chunk_size": 2000}
        
        merged = merge_config(base, override)
        
        # Override should have precedence
        assert merged["chunk_size"] == 2000
        # Base values should remain if not overridden
        assert merged["redis_url"] == "redis://localhost:6379/0"
    
    def test_merge_config_ignores_none_values(self):
        """Test that None values in override don't overwrite base."""
        from docvector.config import merge_config
        
        base = {"chunk_size": 1000}
        override = {"chunk_size": None}
        
        merged = merge_config(base, override)
        
        # None should not overwrite
        assert merged["chunk_size"] == 1000
    
    @patch.dict(os.environ, {"DOCVECTOR_CHUNK_SIZE": "3000"})
    def test_environment_variables_take_precedence(self, monkeypatch):
        """Test that environment variables override config files."""
        from docvector.config import load_config
        
        # Load config (env var should override)
        config = load_config()
        
        # Environment variable should win
        assert config.chunk_size == 3000
    
    def test_config_merging_global_and_local(self, temp_config_dir, temp_local_dir, monkeypatch):
        """Test that local config overrides global config."""
        from docvector.config import load_config
        
        # Create global config
        global_config = temp_config_dir / "config.yaml"
        with open(global_config, "w") as f:
            yaml.dump({"chunk_size": 1000, "chunk_overlap": 200}, f)
        
        # Create local config that overrides chunk_size
        local_config = temp_local_dir / "docvector.yaml"
        with open(local_config, "w") as f:
            yaml.dump({"chunk_size": 1500}, f)
        
        # Mock paths
        monkeypatch.setattr("docvector.config.get_global_config_path", lambda: global_config)
        monkeypatch.setattr("docvector.config.get_local_config_path", lambda: local_config)
        
        # Load config
        config = load_config()
        
        # Local should override global
        assert config.chunk_size == 1500
        # Global value should remain if not overridden
        assert config.chunk_overlap == 200


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_config_with_empty_file(self, temp_config_dir):
        """Test loading an empty config file."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "empty.yaml"
        config_file.touch()  # Create empty file
        
        loaded = load_yaml_config(config_file)
        
        # Should return empty dict
        assert loaded == {}
    
    def test_config_with_only_comments(self, temp_config_dir):
        """Test loading a config file with only comments."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "comments.yaml"
        with open(config_file, "w") as f:
            f.write("# This is a comment\n# Another comment\n")
        
        loaded = load_yaml_config(config_file)
        
        assert loaded == {}
    
    def test_config_with_unicode_characters(self, temp_config_dir):
        """Test loading config with Unicode characters."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "unicode.yaml"
        config = {"name": "测试", "emoji": "🚀"}
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        
        loaded = load_yaml_config(config_file)
        
        assert loaded["name"] == "测试"
        assert loaded["emoji"] == "🚀"
    
    @pytest.mark.skipif(os.name == "nt", reason="Permission tests unreliable on Windows")
    def test_config_permission_denied(self, temp_config_dir):
        """Test handling of config file with no read permissions."""
        from docvector.config import load_yaml_config
        
        config_file = temp_config_dir / "noperm.yaml"
        with open(config_file, "w") as f:
            yaml.dump({"chunk_size": 1000}, f)
        
        # Remove read permissions
        os.chmod(config_file, 0o000)
        
        try:
            # Should return empty dict and not crash
            loaded = load_yaml_config(config_file)
            assert loaded == {}
        finally:
            # Restore permissions for cleanup
            os.chmod(config_file, 0o644)
    
    def test_get_config_creates_settings_object(self):
        """Test that get_config returns a valid Settings object."""
        from docvector.config import get_config
        
        config = get_config()
        
        assert isinstance(config, Settings)
        assert hasattr(config, "chunk_size")
        assert hasattr(config, "redis_url")
        assert hasattr(config, "database_url")
    
    def test_validate_config_detects_errors(self):
        """Test that validate_config detects configuration errors."""
        from docvector.config import validate_config
        
        # Create invalid settings
        invalid_settings = Settings(
            chunk_size=50,  # Too small
            database_url="mysql://localhost/db",  # Wrong database type
        )
        
        errors = validate_config(invalid_settings)
        
        # Should detect multiple errors
        assert len(errors) > 0
        assert any("chunk_size" in err.lower() for err in errors)
        assert any("postgresql" in err.lower() for err in errors)
    
    def test_validate_config_passes_valid_settings(self):
        """Test that validate_config passes valid settings."""
        from docvector.config import validate_config
        
        # Create valid settings
        valid_settings = Settings()  # Defaults are valid
        
        errors = validate_config(valid_settings)
        
        # Should have no errors
        assert len(errors) == 0
    
    def test_diagnose_config_returns_complete_info(self):
        """Test that diagnose_config returns all required information."""
        from docvector.config import diagnose_config
        
        diagnostics = diagnose_config()
        
        # Check structure
        assert "config_loaded" in diagnostics
        assert "global_config" in diagnostics
        assert "local_config" in diagnostics
        assert "env_vars" in diagnostics
        assert "validation" in diagnostics
        
        # Check nested structures
        assert "path" in diagnostics["global_config"]
        assert "exists" in diagnostics["global_config"]
        assert "readable" in diagnostics["global_config"]
        
        assert "valid" in diagnostics["validation"]
        assert "errors" in diagnostics["validation"]


# =============================================================================
# SOURCES COMMAND TESTS
# =============================================================================

class TestSourcesCommands:
    """Tests for sources subcommands."""
    
    @patch("docvector.cli.get_db_session")
    def test_sources_list_empty(self, mock_db_session, cli_runner):
        """Test sources list with no sources."""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session
        
        with patch("docvector.cli.SourceService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.list_sources = AsyncMock(return_value=[])
            
            result = cli_runner.invoke(app, ["sources", "list"])
            
            assert result.exit_code == 0
            assert "No sources found" in result.stdout or "0" in result.stdout
    
    @patch("docvector.cli.get_db_session")
    def test_sources_add_creates_source(self, mock_db_session, cli_runner):
        """Test adding a new source."""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session
        
        with patch("docvector.cli.SourceService") as mock_service:
            mock_instance = mock_service.return_value
            mock_instance.list_sources = AsyncMock(return_value=[])
            
            mock_source = MagicMock()
            mock_source.id = "test-id"
            mock_source.name = "Test Source"
            mock_instance.create_source = AsyncMock(return_value=mock_source)
            
            result = cli_runner.invoke(app, [
                "sources", "add",
                "Test Source",
                "https://example.com"
            ])
            
            assert result.exit_code == 0
            assert "successfully" in result.stdout.lower() or "added" in result.stdout.lower()


# =============================================================================
# SEARCH COMMAND TESTS
# =============================================================================

class TestSearchCommand:
    """Tests for search command."""
    
    @patch("docvector.cli.SearchService")
    def test_search_json_format(self, mock_search_service, cli_runner):
        """Test search command with JSON output format."""
        mock_instance = mock_search_service.return_value
        mock_instance.search = AsyncMock(return_value=[
            {
                "title": "Test Doc",
                "url": "https://example.com",
                "score": 0.95,
                "content": "Test content",
                "chunk_id": "123",
                "document_id": "456"
            }
        ])
        
        result = cli_runner.invoke(app, ["search", "test query", "--format", "json"])
        
        assert result.exit_code == 0
        # Should be valid JSON
        import json
        try:
            data = json.loads(result.stdout)
            assert "query" in data
            assert "results" in data
            assert "count" in data
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")
    
    @patch("docvector.cli.SearchService")
    def test_search_text_format(self, mock_search_service, cli_runner):
        """Test search command with text output format (default)."""
        mock_instance = mock_search_service.return_value
        mock_instance.search = AsyncMock(return_value=[
            {
                "title": "Test Doc",
                "url": "https://example.com",
                "score": 0.95,
            }
        ])
        
        result = cli_runner.invoke(app, ["search", "test query"])
        
        assert result.exit_code == 0
        assert "Test Doc" in result.stdout
