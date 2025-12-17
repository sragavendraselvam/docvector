"""FastAPI dependencies."""

from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from docvector.db import get_db_session
from docvector.services import SearchService, SourceService


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async with get_db_session() as session:
        yield session


async def get_search_service(request: Request) -> SearchService:
    """Get search service dependency (cached singleton from app state)."""
    return request.app.state.search_service


async def get_source_service(
    session: AsyncSession = get_session,
) -> SourceService:
    """Get source service dependency."""
    return SourceService(session)
