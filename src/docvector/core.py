"""Core configuration, logging, and exceptions."""

import logging
import sys
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DocVectorException(Exception):
    """Base exception for DocVector."""

    def __init__(
        self,
        code: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        """
        Initialize DocVectorException.

        Args:
            code: Error code
            message: Error message
            details: Additional error details
        """
        self.code = code
        self.message = message or "An error occurred"
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert exception to dictionary format."""
        return {
            "error": self.code or "UNKNOWN_ERROR",
            "message": self.message,
            "details": self.details,
        }


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DOCVECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default=["*"])

    # API Server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    # Database
    database_url: str = Field(default="postgresql+asyncpg://localhost/docvector")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = Field(default=10)

    # Qdrant
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_grpc_port: int = Field(default=6334)
    qdrant_use_grpc: bool = Field(default=False)
    qdrant_collection: str = Field(default="documents")

    # Embeddings
    embedding_provider: str = Field(default="local")  # "local" or "openai"
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_device: str = Field(default="cpu")  # "cpu" or "cuda"
    embedding_batch_size: int = Field(default=32)
    embedding_cache_enabled: bool = Field(default=True)
    openai_api_key: Optional[str] = Field(default=None)

    # Search
    search_min_score: float = Field(default=0.1)  # Semantic similarity threshold (lowered for MiniLM-L6-v2)
    search_vector_weight: float = Field(default=0.7)  # Weight for vector similarity
    search_keyword_weight: float = Field(default=0.3)  # Weight for keyword matching

    # Chunking
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=200)
    chunking_strategy: str = Field(default="fixed")  # "fixed" or "semantic"

    # Crawler
    crawler_max_depth: int = Field(default=3)
    crawler_max_pages: int = Field(default=100)
    crawler_concurrent_requests: int = Field(default=5)
    crawler_user_agent: str = Field(
        default="DocVector/0.1.0 (https://github.com/docvector/docvector)"
    )

    def to_dict(self, exclude_sensitive: bool = True) -> dict:
        """
        Export settings to dictionary.

        Args:
            exclude_sensitive: If True, exclude sensitive fields like API keys

        Returns:
            Dictionary of settings
        """
        config_dict = self.model_dump(exclude_none=True)
        
        if exclude_sensitive:
            sensitive_fields = ["openai_api_key"]
            for field in sensitive_fields:
                config_dict.pop(field, None)
        
        return config_dict

    def to_yaml(self, exclude_sensitive: bool = True) -> str:
        """
        Export settings to YAML string.

        Args:
            exclude_sensitive: If True, exclude sensitive fields like API keys

        Returns:
            YAML formatted string
        """
        import yaml
        
        config_dict = self.to_dict(exclude_sensitive=exclude_sensitive)
        return yaml.dump(config_dict, default_flow_style=False, sort_keys=False, indent=2)



def _load_global_settings() -> "Settings":
    """
    Load global settings from config files with proper precedence.
    
    Config loading order (highest to lowest priority):
    1. Environment variables (DOCVECTOR_*)
    2. Local project config (./docvector.yaml)
    3. User-global config (~/.docvector/config.yaml)
    4. Built-in defaults (Settings class)
    
    Returns:
        Settings instance with merged configuration from all sources
    """
    try:
        # Import here to avoid circular dependency at module load time
        from docvector.config import load_config
        return load_config()
    except Exception as e:
        # Fallback to defaults if config loading fails
        # This ensures the app still works even if there's a config error
        import warnings
        warnings.warn(f"Failed to load config, using defaults: {e}")
        return Settings()


# Global settings instance - automatically loads from config files
settings = _load_global_settings()


def setup_logging(level: Optional[str] = None) -> None:
    """
    Setup logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level = level or settings.log_level

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


class StructuredLogger:
    """Logger wrapper that supports structured logging with keyword arguments."""

    def __init__(self, logger: logging.Logger):
        """
        Initialize StructuredLogger.

        Args:
            logger: Underlying Python logger
        """
        self._logger = logger

    def _format_message(self, msg: str, **kwargs) -> str:
        """
        Format message with keyword arguments.

        Args:
            msg: Base message
            **kwargs: Additional context to include in log

        Returns:
            Formatted message string
        """
        if kwargs:
            context = " ".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{msg} | {context}"
        return msg

    def debug(self, msg: str, **kwargs) -> None:
        """Log debug message with structured data."""
        self._logger.debug(self._format_message(msg, **kwargs))

    def info(self, msg: str, **kwargs) -> None:
        """Log info message with structured data."""
        self._logger.info(self._format_message(msg, **kwargs))

    def warning(self, msg: str, **kwargs) -> None:
        """Log warning message with structured data."""
        self._logger.warning(self._format_message(msg, **kwargs))

    def error(self, msg: str, **kwargs) -> None:
        """Log error message with structured data."""
        self._logger.error(self._format_message(msg, **kwargs))

    def critical(self, msg: str, **kwargs) -> None:
        """Log critical message with structured data."""
        self._logger.critical(self._format_message(msg, **kwargs))

    def exception(self, msg: str, **kwargs) -> None:
        """Log exception message with structured data."""
        self._logger.exception(self._format_message(msg, **kwargs))


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(logging.getLogger(name))
