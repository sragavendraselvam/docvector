"""MCP (Model Context Protocol) server for DocVector.

This module provides MCP server integration for AI code editors
like Claude Desktop, Cursor, Windsurf, etc.
"""

from docvector.mcp.server import mcp, main

__all__ = ["mcp", "main"]
