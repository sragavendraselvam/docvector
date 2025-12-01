"""MCP Server for DocVector using the official mcp package.

This server provides documentation search capabilities to AI code editors
through the Model Context Protocol (MCP).

Tools:
- resolve-library-id: Find the correct library ID for a library name
- get-library-docs: Get documentation for a specific library
- search-docs: Search across all indexed documentation

Usage:
    # Run with stdio transport (for Claude Desktop, Cursor, etc.)
    python -m docvector.mcp.server

    # Or use the CLI entry point
    docvector-mcp
"""

import asyncio
from typing import Optional

from mcp.server.fastmcp import FastMCP

from docvector.core import get_logger, settings
from docvector.db import get_db_session
from docvector.services.library_service import LibraryService
from docvector.services.search_service import SearchService
from docvector.utils.token_utils import TokenLimiter

logger = get_logger(__name__)

# Initialize the MCP server
mcp = FastMCP(
    name="docvector",
    instructions="DocVector provides documentation search capabilities. Use resolve_library_id to find library IDs, get_library_docs to fetch docs for a specific library, and search_docs to search across all documentation.",
)

# Token limiter instance
token_limiter = TokenLimiter()

# Search service (initialized on first use)
_search_service: Optional[SearchService] = None


async def get_search_service() -> SearchService:
    """Get or initialize the search service."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
        await _search_service.initialize()
    return _search_service


@mcp.tool()
async def resolve_library_id(library_name: str) -> dict:
    """Resolve a library name to its DocVector library ID.

    Use this tool first to find the correct library ID before calling
    get_library_docs or filtering search_docs results.

    Args:
        library_name: The name of the library to search for (e.g., 'fastapi', 'react', 'mongodb')

    Returns:
        A dictionary containing:
        - libraryId: The DocVector library ID (if found)
        - name: Human-readable library name
        - description: Library description
        - suggestions: Similar libraries if exact match not found
    """
    if not library_name:
        return {"error": "library_name is required"}

    async with get_db_session() as db:
        library_service = LibraryService(db)
        library_id = await library_service.resolve_library_id(library_name)

        if library_id:
            library = await library_service.get_library_by_id(library_id)
            return {
                "libraryId": library_id,
                "name": library.name,
                "description": library.description,
                "version": library.metadata_.get("version") if library.metadata_ else None,
            }
        else:
            # Try to search for similar libraries
            similar = await library_service.search_libraries(library_name, limit=5)

            return {
                "error": f"Library not found: {library_name}",
                "suggestions": [
                    {"libraryId": lib.library_id, "name": lib.name}
                    for lib in similar
                ],
                "hint": "Use one of the suggested library IDs, or try a different search term.",
            }


@mcp.tool()
async def get_library_docs(
    library_id: str,
    topic: Optional[str] = None,
    version: Optional[str] = None,
    tokens: int = 5000,
) -> dict:
    """Get documentation for a specific library.

    Fetches relevant documentation chunks for the given library,
    optionally filtered by topic and version.

    Args:
        library_id: The DocVector library ID (e.g., '/fastapi/docs', '/vercel/next.js').
                   Use resolve_library_id first to find the correct ID.
        topic: Optional topic to focus on (e.g., 'routing', 'authentication', 'hooks')
        version: Optional library version (e.g., '0.100.0', '3.11')
        tokens: Maximum number of tokens to return (default: 5000)

    Returns:
        A dictionary containing:
        - libraryId: The requested library ID
        - chunks: List of documentation chunks with content and metadata
        - totalChunks: Total number of matching chunks
        - returnedChunks: Number of chunks returned (after token limiting)
    """
    if not library_id:
        return {"error": "library_id is required"}

    # Build search query
    if topic:
        query = topic
    else:
        query = "documentation overview getting started introduction"

    async with get_db_session() as db:
        # Get library
        library_service = LibraryService(db)
        library = await library_service.get_library_by_id(library_id)

        if not library:
            return {
                "error": f"Library not found: {library_id}",
                "hint": "Use resolve_library_id to find the correct library ID.",
            }

        # Build filters
        filters = {"library_id": str(library.id)}

        if version:
            filters["version"] = version

        if topic:
            filters["topics"] = topic

        # Get search service
        search_service = await get_search_service()

        # Perform search
        results = await search_service.search(
            query=query,
            limit=20,
            search_type="hybrid",
            filters=filters,
        )

        # Format and limit results by tokens
        formatted_results = [
            {
                "content": r.get("content", ""),
                "metadata": {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "topics": r.get("metadata", {}).get("topics", []),
                },
                "score": r.get("score", 0),
            }
            for r in results
        ]

        limited_results = token_limiter.limit_results_to_tokens(
            formatted_results,
            max_tokens=tokens,
        )

        return {
            "libraryId": library_id,
            "libraryName": library.name,
            "version": version,
            "topic": topic,
            "chunks": limited_results,
            "totalChunks": len(results),
            "returnedChunks": len(limited_results),
        }


@mcp.tool()
async def search_docs(
    query: str,
    library_id: Optional[str] = None,
    version: Optional[str] = None,
    topic: Optional[str] = None,
    tokens: int = 5000,
    limit: int = 10,
) -> dict:
    """Search documentation using semantic search.

    Searches across all indexed documentation or filters by library/version/topic.
    Uses hybrid search (vector embeddings + keyword matching) for best results.

    Args:
        query: The search query text (e.g., 'how to handle async errors', 'authentication with JWT')
        library_id: Optional library ID to filter results (use resolve_library_id to find IDs)
        version: Optional version filter
        topic: Optional topic filter (e.g., 'routing', 'database', 'testing')
        tokens: Maximum number of tokens to return (default: 5000)
        limit: Maximum number of results before token limiting (default: 10)

    Returns:
        A dictionary containing:
        - query: The original search query
        - chunks: List of matching documentation chunks with content, metadata, and scores
        - totalChunks: Total number of matching chunks
        - returnedChunks: Number of chunks returned (after token limiting)
    """
    if not query:
        return {"error": "query is required"}

    # Build filters
    filters = {}

    if library_id:
        async with get_db_session() as db:
            library_service = LibraryService(db)
            library = await library_service.get_library_by_id(library_id)
            if library:
                filters["library_id"] = str(library.id)

    if version:
        filters["version"] = version

    if topic:
        filters["topics"] = topic

    # Perform search
    search_service = await get_search_service()

    results = await search_service.search(
        query=query,
        limit=limit * 2,  # Get more results for token limiting
        search_type="hybrid",
        filters=filters,
    )

    # Format results
    formatted_results = [
        {
            "content": r.get("content", ""),
            "metadata": {
                "title": r.get("title"),
                "url": r.get("url"),
                "libraryId": r.get("metadata", {}).get("library_id"),
                "topics": r.get("metadata", {}).get("topics", []),
            },
            "score": r.get("score", 0),
        }
        for r in results
    ]

    # Limit by tokens
    limited_results = token_limiter.limit_results_to_tokens(
        formatted_results,
        max_tokens=tokens,
    )

    return {
        "query": query,
        "filters": {
            "libraryId": library_id,
            "version": version,
            "topic": topic,
        },
        "chunks": limited_results,
        "totalChunks": len(results),
        "returnedChunks": len(limited_results),
    }


@mcp.tool()
async def list_libraries(
    query: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """List available libraries in the DocVector index.

    Use this to discover what documentation is available before searching.

    Args:
        query: Optional search query to filter libraries by name
        limit: Maximum number of libraries to return (default: 20)

    Returns:
        A dictionary containing:
        - libraries: List of available libraries with their IDs and descriptions
        - total: Total number of matching libraries
    """
    async with get_db_session() as db:
        library_service = LibraryService(db)

        if query:
            libraries = await library_service.search_libraries(query, limit=limit)
        else:
            libraries = await library_service.list_libraries(skip=0, limit=limit)

        return {
            "libraries": [
                {
                    "libraryId": lib.library_id,
                    "name": lib.name,
                    "description": lib.description,
                    "homepageUrl": lib.homepage_url,
                }
                for lib in libraries
            ],
            "total": len(libraries),
        }


def main():
    """Run the MCP server with stdio transport."""
    import sys

    # Determine transport mode
    transport = "stdio"

    if len(sys.argv) > 1:
        if sys.argv[1] == "--http":
            transport = "streamable-http"
        elif sys.argv[1] == "--sse":
            transport = "sse"

    logger.info(f"Starting DocVector MCP server with {transport} transport")

    # Run the server
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
