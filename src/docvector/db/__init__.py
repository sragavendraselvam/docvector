"""Database connection and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from docvector.core import get_logger, settings

logger = get_logger(__name__)

# Global engine instance
_engine: Optional[AsyncEngine] = None


def get_engine() -> AsyncEngine:
    """
    Get or create the database engine.

    Returns:
        AsyncEngine instance
    """
    global _engine

    if _engine is None:
        # Check if using SQLite
        is_sqlite = settings.database_url.startswith("sqlite")
        
        if is_sqlite:
            # Parse path from URL (sqlite+aiosqlite:///path/to/db)
            # Basic parsing, might need to be more robust
            try:
                import os
                path_part = settings.database_url.split(":///")[-1]
                db_dir = os.path.dirname(path_part)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
            except Exception as e:
                logger.warning(f"Failed to create SQLite directory: {e}")

        connect_args = {}
        if is_sqlite:
            # SQLite specific args
            connect_args = {"check_same_thread": False}
        
        # pooling args
        kwargs = {}
        if not is_sqlite:
            # PostgreSQL/others support pooling
            kwargs = {
                "pool_size": 10,
                "max_overflow": 20,
            }
            
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.environment == "development",
            connect_args=connect_args,
            pool_pre_ping=True,
            **kwargs
        )
        logger.info("Database engine created", url=settings.database_url)

    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session.

    Yields:
        AsyncSession instance
    """
    engine = get_engine()

    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Close the database connection."""
    global _engine

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection closed")


# Alias for backwards compatibility
get_db_session = get_session
