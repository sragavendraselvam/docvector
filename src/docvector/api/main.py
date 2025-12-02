"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from docvector.core import DocVectorException, get_logger, settings, setup_logging
from docvector.db import close_db

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "Starting DocVector API",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Initialize and cache search service at startup
    from docvector.services import SearchService

    search_service = SearchService()
    await search_service.initialize()
    app.state.search_service = search_service
    logger.info("Search service initialized and cached")

    yield

    # Shutdown
    logger.info("Shutting down DocVector API")
    await search_service.close()
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="DocVector API",
    description="Self-hostable documentation vector search system",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Import routers after app creation
from .routes import auth, billing, ingestion, issues, libraries, qa, search, sources  # noqa: E402

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=6,
)


# Exception handlers
@app.exception_handler(DocVectorException)
async def docvector_exception_handler(request, exc: DocVectorException):
    """Handle DocVector exceptions."""
    logger.error(
        "DocVector exception",
        error_code=exc.code,
        error_message=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=400 if exc.code == "VALIDATION_ERROR" else 500,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Handle general exceptions."""
    logger.exception("Unhandled exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal error occurred",
                "details": {} if settings.is_production else {"error": str(exc)},
            },
        },
    )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "DocVector API",
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


# Health check endpoint
@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """
    Health check endpoint.

    Returns system health status and dependency checks.
    """
    from datetime import datetime

    # TODO: Add actual dependency health checks
    # - PostgreSQL connection test
    # - Redis connection test
    # - Qdrant connection test

    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "postgres": {"status": "unknown"},
            "redis": {"status": "unknown"},
            "qdrant": {"status": "unknown"},
        },
    }


# Include routers
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(sources.router, prefix="/api/v1/sources", tags=["sources"])
app.include_router(ingestion.router, prefix="/api/v1", tags=["ingestion"])
app.include_router(libraries.router, prefix="/api/v1/libraries", tags=["libraries"])
app.include_router(qa.router, prefix="/api/v1/qa", tags=["qa"])
app.include_router(issues.router, prefix="/api/v1/issues", tags=["issues"])
app.include_router(billing.router, prefix="/api/v1", tags=["billing"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "docvector.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
