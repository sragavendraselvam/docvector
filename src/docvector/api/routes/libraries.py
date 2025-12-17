"""Library API routes for Context7-style library management."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from docvector.core import get_logger
from docvector.api.dependencies import get_session
from docvector.services.library_service import LibraryService

logger = get_logger(__name__)

router = APIRouter()


# Schemas
class LibraryCreate(BaseModel):
    """Create library request."""

    library_id: str = Field(..., description="Unique library ID (e.g., 'mongodb/docs')")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    repository_url: Optional[str] = None
    aliases: Optional[List[str]] = None


class LibraryUpdate(BaseModel):
    """Update library request."""

    name: Optional[str] = None
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    repository_url: Optional[str] = None
    aliases: Optional[List[str]] = None


class LibraryResponse(BaseModel):
    """Library response."""

    id: UUID
    library_id: str
    name: str
    description: Optional[str]
    homepage_url: Optional[str]
    repository_url: Optional[str]
    aliases: List[str]

    class Config:
        from_attributes = True


class ResolveLibraryRequest(BaseModel):
    """Resolve library request (Context7-style)."""

    library_name: str = Field(
        ..., description="Library name to resolve (e.g., 'mongodb', 'next.js')"
    )


class ResolveLibraryResponse(BaseModel):
    """Resolve library response."""

    library_id: Optional[str]
    name: Optional[str]
    description: Optional[str]
    suggestions: Optional[List[dict]] = None


# Routes


@router.post("/resolve", response_model=ResolveLibraryResponse)
async def resolve_library_id(
    request: ResolveLibraryRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Resolve a library name to its Context7-compatible library ID.

    Similar to Context7's resolve-library-id tool.
    """
    try:
        service = LibraryService(db)
        library_id = await service.resolve_library_id(request.library_name)

        if library_id:
            library = await service.get_library_by_id(library_id)
            return ResolveLibraryResponse(
                library_id=library_id,
                name=library.name if library else None,
                description=library.description if library else None,
            )
        else:
            # Provide suggestions
            similar = await service.search_libraries(request.library_name, limit=5)
            return ResolveLibraryResponse(
                library_id=None,
                name=None,
                description=None,
                suggestions=[
                    {"library_id": lib.library_id, "name": lib.name} for lib in similar
                ],
            )

    except Exception as e:
        logger.error("Library resolution failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("", response_model=List[LibraryResponse])
async def list_libraries(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_session),
):
    """List all libraries."""
    try:
        service = LibraryService(db)
        libraries = await service.list_libraries(skip=skip, limit=limit)
        return libraries

    except Exception as e:
        logger.error("Failed to list libraries", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search", response_model=List[LibraryResponse])
async def search_libraries(
    q: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_session),
):
    """Search libraries by name or description."""
    try:
        service = LibraryService(db)
        libraries = await service.search_libraries(q, limit=limit)
        return libraries

    except Exception as e:
        logger.error("Library search failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("", response_model=LibraryResponse, status_code=201)
async def create_library(
    request: LibraryCreate,
    db: AsyncSession = Depends(get_session),
):
    """Create a new library."""
    try:
        service = LibraryService(db)

        # Check if library ID already exists
        existing = await service.get_library_by_id(request.library_id)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Library with ID '{request.library_id}' already exists",
            )

        library = await service.create_library(
            library_id=request.library_id,
            name=request.name,
            description=request.description,
            homepage_url=request.homepage_url,
            repository_url=request.repository_url,
            aliases=request.aliases,
        )

        return library

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create library", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{library_id}", response_model=LibraryResponse)
async def get_library(
    library_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Get a library by ID."""
    try:
        service = LibraryService(db)
        library = await service.get_library_by_id(library_id)

        if not library:
            raise HTTPException(status_code=404, detail="Library not found")

        return library

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get library", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{library_id}", response_model=LibraryResponse)
async def update_library(
    library_id: str,
    request: LibraryUpdate,
    db: AsyncSession = Depends(get_session),
):
    """Update a library."""
    try:
        service = LibraryService(db)

        # Build updates dict
        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.homepage_url is not None:
            updates["homepage_url"] = request.homepage_url
        if request.repository_url is not None:
            updates["repository_url"] = request.repository_url
        if request.aliases is not None:
            updates["aliases"] = request.aliases

        library = await service.update_library(library_id, **updates)

        if not library:
            raise HTTPException(status_code=404, detail="Library not found")

        return library

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update library", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{library_id}", status_code=204)
async def delete_library(
    library_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Delete a library."""
    try:
        service = LibraryService(db)
        deleted = await service.delete_library(library_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Library not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete library", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
