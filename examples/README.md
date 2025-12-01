# DocVector Examples

This directory contains example configurations for integrating DocVector with various tools.

## Claude Desktop Integration

To use DocVector with Claude Desktop:

1. **Start DocVector infrastructure:**
   ```bash
   cd /path/to/docvector
   docker-compose up -d
   ```

2. **Install DocVector:**
   ```bash
   pip install -e .
   ```

3. **Initialize the database:**
   ```bash
   python init_db.py
   ```

4. **Configure Claude Desktop:**

   Copy the configuration from `claude_desktop_config.json` to your Claude Desktop config file:

   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

   Merge the `mcpServers` section with any existing configuration.

5. **Restart Claude Desktop**

## Available MCP Tools

Once configured, Claude Desktop will have access to these tools:

### `resolve_library_id`
Find the correct library ID for a library name.

```
Use: "Find the library ID for FastAPI"
```

### `get_library_docs`
Get documentation for a specific library.

```
Use: "Get FastAPI documentation about dependency injection"
```

### `search_docs`
Search across all indexed documentation.

```
Use: "Search for how to handle async errors in Python"
```

### `list_libraries`
List all available libraries in the index.

```
Use: "What documentation is available?"
```

## Indexing Documentation

Before using the MCP tools, you need to index some documentation:

```bash
# Index FastAPI docs
docvector index https://fastapi.tiangolo.com/ --library fastapi/docs

# Index Python docs
docvector index https://docs.python.org/3/ --library python/docs --depth 2

# Index any documentation site
docvector index https://your-docs-site.com/
```

## Alternative: Using the CLI Entry Point

If you installed DocVector with `pip install -e .`, you can use the CLI directly:

```json
{
  "mcpServers": {
    "docvector": {
      "command": "docvector-mcp"
    }
  }
}
```

## Troubleshooting

### "Library not found" errors
Make sure you've indexed the documentation first using `docvector index`.

### Connection errors
Ensure Docker services are running: `docker-compose ps`

### MCP server not starting
Check the logs: `docvector-mcp 2>&1 | head -50`
