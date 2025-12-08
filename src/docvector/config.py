"""Configuration loader with YAML file support.

Loads configuration from multiple sources with the following precedence (highest to lowest):
1. Environment variables (DOCVECTOR_*)
2. Local project config (./docvector.yaml)
3. User-global config (~/.docvector/config.yaml)
4. Built-in defaults
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from docvector.core import Settings, get_logger

logger = get_logger(__name__)


def get_global_config_path() -> Path:
    """Get path to global config file in user's home directory."""
    return Path.home() / ".docvector" / "config.yaml"


def get_local_config_path() -> Path:
    """Get path to local config file in current directory."""
    return Path.cwd() / "docvector.yaml"


def load_yaml_config(config_path: Path) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to YAML config file

    Returns:
        Dictionary of configuration values
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"Invalid YAML syntax in {config_path}", error=str(e))
        return {}
    except Exception as e:
        logger.warning(f"Failed to load config from {config_path}", error=str(e))
        return {}


def merge_config(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two configuration dictionaries.

    Args:
        base_config: Base configuration
        override_config: Configuration that overrides base

    Returns:
        Merged configuration dictionary
    """
    merged = base_config.copy()
    for key, value in override_config.items():
        if value is not None:
            merged[key] = value
    return merged


def load_config() -> Settings:
    """
    Load configuration from all sources with proper precedence.

    Priority (highest to lowest):
    1. Environment variables (handled by pydantic-settings)
    2. Local project config (./docvector.yaml)
    3. User-global config (~/.docvector/config.yaml)
    4. Built-in defaults (in Settings class)

    Returns:
        Settings instance with merged configuration
    """
    config_dict: Dict[str, Any] = {}

    # Load global config
    global_config_path = get_global_config_path()
    if global_config_path.exists():
        logger.debug(f"Loading global config from {global_config_path}")
        global_config = load_yaml_config(global_config_path)
        config_dict = merge_config(config_dict, global_config)

    # Load local config (overrides global)
    local_config_path = get_local_config_path()
    if local_config_path.exists():
        logger.debug(f"Loading local config from {local_config_path}")
        local_config = load_yaml_config(local_config_path)
        config_dict = merge_config(config_dict, local_config)

    # Create Settings instance (environment variables will override via pydantic)
    # We need to prefix keys for pydantic-settings if they don't have the prefix
    prefixed_config = {}
    for key, value in config_dict.items():
        # If key doesn't start with DOCVECTOR_, add it for environment override
        if not key.startswith("DOCVECTOR_"):
            env_key = f"DOCVECTOR_{key.upper()}"
            # Only set if not already in environment
            if env_key not in os.environ:
                prefixed_config[key] = value
        else:
            # Remove prefix for Settings model
            clean_key = key.replace("DOCVECTOR_", "").lower()
            prefixed_config[clean_key] = value

    # Create Settings instance with config dict
    # Environment variables will still take precedence via pydantic-settings
    return Settings(**prefixed_config)


def get_config() -> Settings:
    """
    Get merged configuration from all sources.
    
    This is an alias for load_config() provided for API consistency.
    
    Priority (highest to lowest):
    1. Environment variables (DOCVECTOR_*)
    2. Local project config (./docvector.yaml)
    3. User-global config (~/.docvector/config.yaml)
    4. Built-in defaults
    
    Returns:
        Settings instance with merged configuration
        
    Examples:
        >>> config = get_config()
        >>> print(config.chunk_size)
        1000
    """
    return load_config()


def validate_config(settings: Settings) -> List[str]:
    """
    Validate configuration and return list of issues.
    
    Performs semantic validation beyond basic type checking.
    Checks for common misconfigurations and invalid value combinations.
    
    Args:
        settings: Settings instance to validate
        
    Returns:
        List of validation error messages (empty list if valid)
        
    Examples:
        >>> config = get_config()
        >>> errors = validate_config(config)
        >>> if errors:
        ...     for error in errors:
        ...         print(f"Error: {error}")
    """
    errors = []
    
    # Validate database URL format
    if not settings.database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        errors.append(
            "database_url must be a PostgreSQL connection string "
            "(starting with 'postgresql://' or 'postgresql+asyncpg://')"
        )
    
    # Validate Redis URL format
    if not settings.redis_url.startswith("redis://"):
        errors.append("redis_url must start with 'redis://'")
    
    # Validate chunk size range
    if settings.chunk_size < 100:
        errors.append("chunk_size must be at least 100 characters")
    elif settings.chunk_size > 10000:
        errors.append("chunk_size must be at most 10,000 characters")
    
    # Validate chunk overlap
    if settings.chunk_overlap < 0:
        errors.append("chunk_overlap must be non-negative")
    elif settings.chunk_overlap >= settings.chunk_size:
        errors.append("chunk_overlap must be less than chunk_size")
    
    # Validate search weights
    total_weight = settings.search_vector_weight + settings.search_keyword_weight
    if abs(total_weight - 1.0) > 0.01:  # Allow small floating point differences
        errors.append(
            f"search_vector_weight ({settings.search_vector_weight}) + "
            f"search_keyword_weight ({settings.search_keyword_weight}) must equal 1.0 "
            f"(currently {total_weight:.2f})"
        )
    
    # Validate embedding provider
    if settings.embedding_provider not in ("local", "openai"):
        errors.append(f"embedding_provider must be 'local' or 'openai' (got '{settings.embedding_provider}')")
    
    # Validate OpenAI config
    if settings.embedding_provider == "openai" and not settings.openai_api_key:
        errors.append("openai_api_key is required when embedding_provider is 'openai'")
    
    # Validate ports
    if not (1 <= settings.api_port <= 65535):
        errors.append(f"api_port must be between 1 and 65535 (got {settings.api_port})")
    if not (1 <= settings.qdrant_port <= 65535):
        errors.append(f"qdrant_port must be between 1 and 65535 (got {settings.qdrant_port})")
    
    # Validate crawler settings
    if settings.crawler_max_depth < 1:
        errors.append("crawler_max_depth must be at least 1")
    if settings.crawler_max_pages < 1:
        errors.append("crawler_max_pages must be at least 1")
    
    return errors


def diagnose_config() -> Dict[str, Any]:
    """
    Diagnose configuration issues and show loaded sources.
    
    Useful for debugging configuration problems. Shows which config files
    exist, are readable, and what environment variables are set.
    
    Returns:
        Dictionary with diagnostic information including:
        - global_config: Global config file status
        - local_config: Local config file status  
        - env_vars: DOCVECTOR_* environment variables
        - validation: Configuration validation results
        
    Examples:
        >>> from pprint import pprint
        >>> diagnostics = diagnose_config()
        >>> pprint(diagnostics)
        {
            'global_config': {
                'path': '/home/user/.docvector/config.yaml',
                'exists': True,
                'readable': True
            },
            ...
        }
    """
    global_path = get_global_config_path()
    local_path = get_local_config_path()
    
    # Get current config
    try:
        config = load_config()
        validation_errors = validate_config(config)
        config_loaded = True
    except Exception as e:
        config = None
        validation_errors = [str(e)]
        config_loaded = False
    
    return {
        "config_loaded": config_loaded,
        "global_config": {
            "path": str(global_path),
            "exists": global_path.exists(),
            "readable": global_path.exists() and os.access(global_path, os.R_OK),
        },
        "local_config": {
            "path": str(local_path),
            "exists": local_path.exists(),
            "readable": local_path.exists() and os.access(local_path, os.R_OK),
        },
        "env_vars": {
            k: v for k, v in os.environ.items() if k.startswith("DOCVECTOR_")
        },
        "validation": {
            "valid": len(validation_errors) == 0,
            "errors": validation_errors,
        },
    }


def save_config(config_path: Path, settings: Settings, template: bool = False) -> None:
    """
    Save configuration to YAML file.

    Args:
        config_path: Path where config should be saved
        settings: Settings instance to save
        template: If True, include all settings with comments
    """
    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert settings to dict, excluding unset values
    config_dict = settings.model_dump(exclude_unset=not template, exclude_none=True)

    # Remove sensitive fields that should be in .env
    sensitive_fields = ["openai_api_key"]
    for field in sensitive_fields:
        config_dict.pop(field, None)

    with open(config_path, "w", encoding="utf-8") as f:
        if template:
            # Write with comments for template
            f.write("# DocVector Configuration\n")
            f.write("# See https://github.com/docvector-hub/docvector for details\n\n")
            f.write("# Application Settings\n")

        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False, indent=2)

    logger.info(f"Configuration saved to {config_path}")
