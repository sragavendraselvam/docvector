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

    # ===========================================
    # MODE SELECTION
    # ===========================================
    docvector_mode: str = Field(
        default="local",
        description="Operating mode: 'local' (embedded DBs), 'cloud' (external DBs), or 'hybrid'",
    )

    # ===========================================
    # LOCAL DATA DIRECTORY
    # ===========================================
    local_data_dir: str = Field(
        default="./docvector_data",
        description="Directory for local data storage (SQLite, ChromaDB, cache)",
    )

    # ===========================================
    # VECTOR COLLECTION
    # ===========================================
    vector_collection: str = Field(
        default="documents",
        description="Name of the default vector collection",
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_local_mode(self) -> bool:
        """Check if running in local mode (embedded databases)."""
        return self.docvector_mode == "local"

    @property
    def is_cloud_mode(self) -> bool:
        """Check if running in cloud mode (external databases)."""
        return self.docvector_mode == "cloud"

    @property
    def is_hybrid_mode(self) -> bool:
        """Check if running in hybrid mode."""
        return self.docvector_mode == "hybrid"

    @property
    def effective_database_url(self) -> str:
        """
        Get the appropriate database URL based on mode.

        In local mode, uses SQLite in the local data directory.
        In cloud/hybrid mode, uses the configured database_url.
        """
        if self.is_local_mode:
            from pathlib import Path

            db_path = Path(self.local_data_dir) / "db" / "docvector.db"
            return f"sqlite+aiosqlite:///{db_path}"
        return self.database_url

    @property
    def effective_vector_store_type(self) -> str:
        """Get the vector store type based on mode."""
        if self.is_local_mode:
            return "chroma"
        return "qdrant"

    def ensure_local_directories(self) -> None:
        """
        Create local data directories if they don't exist.

        Only operates in local mode.
        """
        if not self.is_local_mode:
            return

        from pathlib import Path

        base = Path(self.local_data_dir)
        directories = [
            base / "db",
            base / "vectors" / "chroma",
            base / "cache",
            base / "logs",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def validate_mode(self) -> None:
        """
        Validate mode configuration.

        Raises:
            ValueError: If mode is invalid or required settings are missing
        """
        valid_modes = {"local", "cloud", "hybrid"}
        if self.docvector_mode not in valid_modes:
            raise ValueError(
                f"Invalid DOCVECTOR_MODE: '{self.docvector_mode}'. "
                f"Must be one of: {', '.join(sorted(valid_modes))}"
            )

        # Cloud mode requires a non-SQLite database URL
        if self.is_cloud_mode and "sqlite" in self.database_url:
            raise ValueError(
                "Cloud mode requires a PostgreSQL database URL. "
                "Set DOCVECTOR_DATABASE_URL or use local mode."
            )

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


# Global settings instance
settings = Settings()


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
