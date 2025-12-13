"""Tests for CLI models commands."""

import pytest
from typer.testing import CliRunner

from docvector.cli import app

runner = CliRunner()


class TestModelsListCommand:
    """Tests for 'docvector models list' command."""

    def test_models_list_shows_all_models(self):
        """Should list all available models."""
        result = runner.invoke(app, ["models", "list"])
        assert result.exit_code == 0
        assert "all-MiniLM-L6-v2" in result.output
        assert "DEFAULT" in result.output

    def test_models_list_shows_model_details(self):
        """Should show dimension, memory, and quality for each model."""
        result = runner.invoke(app, ["models", "list"])
        assert result.exit_code == 0
        assert "Dimension:" in result.output
        assert "Memory:" in result.output
        assert "Quality:" in result.output

    def test_models_list_groups_by_speed(self):
        """Should group models by speed category."""
        result = runner.invoke(app, ["models", "list"])
        assert result.exit_code == 0
        assert "FAST MODELS" in result.output
        assert "MEDIUM MODELS" in result.output

    def test_models_list_filter_by_provider(self):
        """Should filter by provider."""
        result = runner.invoke(app, ["models", "list", "--provider", "openai"])
        assert result.exit_code == 0
        assert "text-embedding" in result.output
        # Should not include local models
        assert "all-MiniLM" not in result.output

    def test_models_list_filter_by_speed(self):
        """Should filter by speed."""
        result = runner.invoke(app, ["models", "list", "--speed", "fast"])
        assert result.exit_code == 0
        assert "FAST MODELS" in result.output
        # Should not include medium or slow models
        assert "MEDIUM MODELS" not in result.output
        assert "LARGE MODELS" not in result.output

    def test_models_list_no_matches(self):
        """Should show message when no models match filters."""
        result = runner.invoke(
            app, ["models", "list", "--provider", "nonexistent"]
        )
        assert result.exit_code == 0
        assert "No models match" in result.output


class TestModelsInfoCommand:
    """Tests for 'docvector models info' command."""

    def test_models_info_registered_model(self):
        """Should show info for registered model."""
        result = runner.invoke(
            app, ["models", "info", "sentence-transformers/all-MiniLM-L6-v2"]
        )
        assert result.exit_code == 0
        assert "384" in result.output  # dimension
        assert "sentence-transformers" in result.output  # provider
        assert "fast" in result.output  # speed

    def test_models_info_shows_all_fields(self):
        """Should display all metadata fields."""
        result = runner.invoke(
            app, ["models", "info", "BAAI/bge-base-en-v1.5"]
        )
        assert result.exit_code == 0
        assert "Provider" in result.output
        assert "Dimension" in result.output
        assert "Speed" in result.output
        assert "Quality" in result.output
        assert "Memory" in result.output
        assert "Max Tokens" in result.output

    def test_models_info_shows_use_cases(self):
        """Should display recommended use cases."""
        result = runner.invoke(
            app, ["models", "info", "sentence-transformers/all-MiniLM-L6-v2"]
        )
        assert result.exit_code == 0
        assert "Recommended For" in result.output

    def test_models_info_shows_config(self):
        """Should display configuration snippet."""
        result = runner.invoke(
            app, ["models", "info", "sentence-transformers/all-MiniLM-L6-v2"]
        )
        assert result.exit_code == 0
        assert "DOCVECTOR_EMBEDDING_MODEL" in result.output

    def test_models_info_unknown_model(self):
        """Should show error for unknown model."""
        result = runner.invoke(app, ["models", "info", "unknown-model"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_models_info_suggests_list_command(self):
        """Should suggest list command for unknown model."""
        result = runner.invoke(app, ["models", "info", "unknown-model"])
        assert result.exit_code == 1
        assert "docvector models list" in result.output


class TestModelsRecommendCommand:
    """Tests for 'docvector models recommend' command."""

    def test_recommend_default(self):
        """Should return recommendation for general use case."""
        result = runner.invoke(app, ["models", "recommend"])
        assert result.exit_code == 0
        assert "general" in result.output
        assert "all-MiniLM" in result.output

    def test_recommend_technical(self):
        """Should return BGE model for technical use case."""
        result = runner.invoke(
            app, ["models", "recommend", "--use-case", "technical"]
        )
        assert result.exit_code == 0
        assert "bge" in result.output.lower()

    def test_recommend_code(self):
        """Should return appropriate model for code use case."""
        result = runner.invoke(
            app, ["models", "recommend", "--use-case", "code"]
        )
        assert result.exit_code == 0
        assert "Model:" in result.output

    def test_recommend_shows_why(self):
        """Should explain why the model is recommended."""
        result = runner.invoke(
            app, ["models", "recommend", "--use-case", "technical"]
        )
        assert result.exit_code == 0
        assert "Why this model" in result.output
        assert "Quality:" in result.output
        assert "Speed:" in result.output

    def test_recommend_shows_config(self):
        """Should show configuration instructions."""
        result = runner.invoke(app, ["models", "recommend"])
        assert result.exit_code == 0
        assert "DOCVECTOR_EMBEDDING_MODEL" in result.output

    def test_recommend_production(self):
        """Should return OpenAI model for production use case."""
        result = runner.invoke(
            app, ["models", "recommend", "--use-case", "production"]
        )
        assert result.exit_code == 0
        assert "text-embedding" in result.output
