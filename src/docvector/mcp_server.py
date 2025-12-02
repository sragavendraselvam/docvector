"""Model Context Protocol (MCP) server for DocVector.

This server implements the MCP standard for integration with AI code editors
like Cursor, Claude Code, Windsurf, etc.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from docvector.core import get_logger
from docvector.db import get_db_session as get_db
from docvector.services.library_service import LibraryService
from docvector.services.search_service import SearchService
from docvector.utils.token_utils import TokenLimiter

logger = get_logger(__name__)


class MCPServer:
    """MCP Server for DocVector."""

    def __init__(self):
        """Initialize the MCP server."""
        self.token_limiter = TokenLimiter()
        self.tools = [
            {
                "name": "resolve-library-id",
                "description": (
                    "Resolves a general library name into a DocVector-compatible library ID. "
                    "Use this to find the correct library ID before calling get-library-docs."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "libraryName": {
                            "type": "string",
                            "description": "The name of the library to search for (e.g., 'mongodb', 'react', 'next.js')",
                        }
                    },
                    "required": ["libraryName"],
                },
            },
            {
                "name": "get-library-docs",
                "description": (
                    "Fetches up-to-date documentation for a specific library using its "
                    "DocVector-compatible ID. Returns relevant documentation chunks."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "libraryId": {
                            "type": "string",
                            "description": (
                                "Exact DocVector-compatible library ID (e.g., '/mongodb/docs', '/vercel/next.js'). "
                                "Obtain this from resolve-library-id."
                            ),
                        },
                        "topic": {
                            "type": "string",
                            "description": (
                                "Optional. Focus the docs on a specific topic "
                                "(e.g., 'routing', 'authentication', 'hooks')."
                            ),
                        },
                        "version": {
                            "type": "string",
                            "description": "Optional. Specific version of the library (e.g., '18.2.0', '3.11').",
                        },
                        "tokens": {
                            "type": "integer",
                            "description": "Optional. Max number of tokens to return (default: 5000).",
                            "default": 5000,
                        },
                    },
                    "required": ["libraryId"],
                },
            },
            {
                "name": "search-docs",
                "description": (
                    "Search documentation using semantic search. "
                    "Returns relevant chunks from all or filtered documentation sources."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text",
                        },
                        "libraryId": {
                            "type": "string",
                            "description": "Optional. Filter results to a specific library.",
                        },
                        "version": {
                            "type": "string",
                            "description": "Optional. Filter results to a specific version.",
                        },
                        "topic": {
                            "type": "string",
                            "description": "Optional. Filter results to a specific topic.",
                        },
                        "tokens": {
                            "type": "integer",
                            "description": "Optional. Max number of tokens to return (default: 5000).",
                            "default": 5000,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Optional. Max number of results (default: 10).",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an MCP request.

        Args:
            request: MCP request object

        Returns:
            MCP response object
        """
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method == "tools/list":
                return {"tools": self.tools}

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_params = params.get("arguments", {})

                if tool_name == "resolve-library-id":
                    result = await self._resolve_library_id(tool_params)
                elif tool_name == "get-library-docs":
                    result = await self._get_library_docs(tool_params)
                elif tool_name == "search-docs":
                    result = await self._search_docs(tool_params)
                else:
                    return {
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}",
                        }
                    }

                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            else:
                return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return {"error": {"code": -32603, "message": str(e)}}

    async def _resolve_library_id(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve a library name to its ID.

        Args:
            params: Request parameters with 'libraryName'

        Returns:
            Response with library ID or error
        """
        library_name = params.get("libraryName")

        if not library_name:
            return {"error": "libraryName is required"}

        async with get_db() as db:
            library_service = LibraryService(db)
            library_id = await library_service.resolve_library_id(library_name)

            if library_id:
                library = await library_service.get_library_by_id(library_id)
                return {
                    "libraryId": library_id,
                    "name": library.name,
                    "description": library.description,
                }
            else:
                # Try to search for similar libraries
                similar = await library_service.search_libraries(library_name, limit=5)

                return {
                    "error": f"Library not found: {library_name}",
                    "suggestions": [
                        {"libraryId": lib.library_id, "name": lib.name} for lib in similar
                    ],
                }

    async def _get_library_docs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get documentation for a specific library.

        Args:
            params: Request parameters with 'libraryId', optional 'topic', 'version', 'tokens'

        Returns:
            Response with documentation chunks
        """
        library_id = params.get("libraryId")
        topic = params.get("topic")
        version = params.get("version")
        max_tokens = params.get("tokens", 5000)

        if not library_id:
            return {"error": "libraryId is required"}

        # Build search query
        query_parts = []

        if topic:
            query_parts.append(topic)
        else:
            # Generic query for overview/getting started
            query_parts.append("documentation overview getting started")

        query = " ".join(query_parts)

        # Build filters - use 'library' field which is the string name in Qdrant
        filters = {"library": library_id}

        if version:
            filters["version"] = version

        # Get search service (standalone mode without DB session)
        search_service = SearchService()
        await search_service.initialize()

        try:
            # Perform search
            results = await search_service.search(
                query=query,
                limit=20,
                search_type="hybrid",
                filters=filters,
            )

            # Limit by tokens - results are dicts from search service
            limited_results = self.token_limiter.limit_results_to_tokens(
                [
                    {
                        "content": r.get("content", ""),
                        "metadata": {k: v for k, v in r.items() if k not in ["content", "score"]},
                        "score": r.get("score", 0),
                    }
                    for r in results
                ],
                max_tokens=max_tokens,
            )

            return {
                "libraryId": library_id,
                "version": version,
                "topic": topic,
                "chunks": limited_results,
                "totalChunks": len(results),
                "returnedChunks": len(limited_results),
            }
        finally:
            await search_service.close()

    async def _search_docs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search documentation.

        Args:
            params: Request parameters with 'query', optional filters

        Returns:
            Response with search results
        """
        query = params.get("query")
        library_id = params.get("libraryId")
        version = params.get("version")
        topic = params.get("topic")
        max_tokens = params.get("tokens", 5000)
        limit = params.get("limit", 10)

        if not query:
            return {"error": "query is required"}

        # Build filters - use 'library' field which is the string name in Qdrant
        filters = {}

        if library_id:
            filters["library"] = library_id

        if version:
            filters["version"] = version

        # Get search service (standalone mode without DB session)
        search_service = SearchService()
        await search_service.initialize()

        try:
            results = await search_service.search(
                query=query,
                limit=limit * 2,  # Get more results for token limiting
                search_type="hybrid",
                filters=filters,
            )

            # Limit by tokens - results are dicts from search service
            limited_results = self.token_limiter.limit_results_to_tokens(
                [
                    {
                        "content": r.get("content", ""),
                        "metadata": {k: v for k, v in r.items() if k not in ["content", "score"]},
                        "score": r.get("score", 0),
                    }
                    for r in results
                ],
                max_tokens=max_tokens,
            )

            return {
                "query": query,
                "filters": filters,
                "chunks": limited_results,
                "totalChunks": len(results),
                "returnedChunks": len(limited_results),
            }
        finally:
            await search_service.close()


async def run_stdio_server():
    """Run the MCP server over stdio (for MCP clients)."""
    import sys

    server = MCPServer()

    # Read requests from stdin, write responses to stdout
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line)
            response = await server.handle_request(request)

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"Error in stdio server: {e}")
            error_response = {"error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


async def run_http_server(host: str = "0.0.0.0", port: int = 8001):
    """
    Run the MCP server over HTTP.

    Args:
        host: Host to bind to
        port: Port to bind to
    """
    from aiohttp import web

    server = MCPServer()

    async def handle_mcp(request: web.Request) -> web.Response:
        """Handle MCP HTTP requests."""
        try:
            body = await request.json()
            response = await server.handle_request(body)
            return web.json_response(response)
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return web.json_response(
                {"error": {"code": -32603, "message": str(e)}},
                status=500,
            )

    app = web.Application()
    app.router.add_post("/mcp", handle_mcp)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"MCP server running on http://{host}:{port}/mcp")

    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "stdio":
        asyncio.run(run_stdio_server())
    else:
        asyncio.run(run_http_server())
