"""DocVector CLI - Command-line interface for documentation search.

Usage:
    docvector index <url>              Index documentation from URL
    docvector search <query>           Search indexed documentation
    docvector serve                    Start the API server
    docvector mcp                      Start the MCP server
    docvector libraries list           List indexed libraries
    docvector sources list             List configured sources
"""

import asyncio
from typing import Optional
from pathlib import Path
import os

import typer
from rich.console import Console
from rich.table import Table

from docvector.core import get_logger, settings

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="docvector",
    help="DocVector - Self-hosted documentation search",
    add_completion=False,
)


def run_async(coro):
    """Run an async function in the event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# INIT COMMAND
# =============================================================================

@app.command()
def init(
    mode: str = typer.Option("local", "--mode", "-m", help="Operating mode: local, cloud, hybrid"),
    data_dir: str = typer.Option("./data", "--data-dir", "-d", help="Data directory"),
):
    """Initialize DocVector configuration and directories.
    
    Creates necessary directories and configuration files for the selected mode.
    
    Examples:
        docvector init
        docvector init --mode hybrid
    """
    
    console.print(f"[bold blue]Initializing DocVector in {mode} mode...[/]")
    
    # Resolve absolute path
    data_path = Path(data_dir).resolve()
    
    try:
        data_path.mkdir(parents=True, exist_ok=True)
        console.print(f"  Created data directory: {data_path}")
        
        if mode == "local":
            # Create subdirs
            sqlite_dir = data_path / "sqlite"
            chroma_dir = data_path / "chroma"

            sqlite_dir.mkdir(exist_ok=True)
            chroma_dir.mkdir(exist_ok=True)

            console.print(f"  Created SQLite directory: {sqlite_dir}")
            console.print(f"  Created ChromaDB directory: {chroma_dir}")

            # Determine DB URL
            # SQLAlchemy accepts forward slashes on all platforms (Windows, Linux, macOS)
            db_path = sqlite_dir / "docvector.db"
            db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

            # Write .env if not exists
            env_path = Path(".env")
            if not env_path.exists():
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f"DOCVECTOR_MCP_MODE={mode}\n")
                    f.write(f"DOCVECTOR_DATABASE_URL={db_url}\n")
                    f.write(f"DOCVECTOR_CHROMA_PERSIST_DIRECTORY={chroma_dir.as_posix()}\n")
                    f.write(f"DOCVECTOR_EMBEDDING_PROVIDER=local\n")
                    f.write(f"# Add other settings as needed\n")

                console.print(f"[green]✓ Created .env configuration[/]")
            else:
                console.print(f"[yellow]! .env already exists, skipping creation[/]")
                
    except Exception as e:
        console.print(f"[bold red]Initialization failed:[/] {e}")
        raise typer.Exit(1)
    
    console.print(f"\n[bold green]Initialization complete![/]")
    console.print(f"Run 'docvector serve' or 'docvector mcp' to start.")


# =============================================================================
# INDEX COMMANDS
# =============================================================================

@app.command()
def index(
    url: str = typer.Argument(..., help="URL to crawl and index"),
    library_id: Optional[str] = typer.Option(None, "--library", "-l", help="Library ID to associate with"),
    max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum crawl depth"),
    max_pages: int = typer.Option(100, "--pages", "-p", help="Maximum pages to crawl"),
):
    """Index documentation from a URL.

    Crawls the URL and its linked pages, extracts content, generates embeddings,
    and stores everything in the vector database.

    Examples:
        docvector index https://fastapi.tiangolo.com/
        docvector index https://docs.python.org/3/ --library python/docs --depth 2
    """
    async def _index():
        from docvector.db import get_db_session
        from docvector.services.ingestion_service import IngestionService

        console.print(f"[bold blue]Indexing:[/] {url}")
        console.print(f"  Max depth: {max_depth}, Max pages: {max_pages}")

        async with get_db_session() as db:
            ingestion_service = IngestionService(db)

            with console.status("[bold green]Crawling and indexing..."):
                result = await ingestion_service.ingest_url(
                    url=url,
                    library_id=library_id,
                    max_depth=max_depth,
                    max_pages=max_pages,
                )

            console.print(f"\n[bold green]✓ Indexing complete![/]")
            console.print(f"  Documents: {result.get('documents_indexed', 0)}")
            console.print(f"  Chunks: {result.get('chunks_created', 0)}")

    run_async(_index())


# =============================================================================
# SEARCH COMMANDS
# =============================================================================

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    library: Optional[str] = typer.Option(None, "--library", "-l", help="Filter by library ID"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results"),
    show_content: bool = typer.Option(False, "--content", "-c", help="Show full content"),
):
    """Search indexed documentation.

    Uses hybrid search (vector + keyword) to find relevant documentation chunks.

    Examples:
        docvector search "how to handle async errors"
        docvector search "authentication" --library fastapi/docs
        docvector search "database connection" --limit 10 --content
    """
    async def _search():
        from docvector.db import get_db_session
        from docvector.services.search_service import SearchService

        search_service = SearchService()

        filters = {}
        if library:
            from docvector.services.library_service import LibraryService
            async with get_db_session() as db:
                lib_service = LibraryService(db)
                lib = await lib_service.get_library_by_id(library)
                if lib:
                    filters["library_id"] = str(lib.id)

        with console.status("[bold green]Searching..."):
            results = await search_service.search(
                query=query,
                limit=limit,
                search_type="hybrid",
                filters=filters,
            )

        if not results:
            console.print("[yellow]No results found.[/]")
            return

        console.print(f"\n[bold]Found {len(results)} results:[/]\n")

        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            result_url = result.get("url", "")
            score = result.get("score", 0)

            console.print(f"[bold cyan]{i}. {title}[/] [dim](score: {score:.3f})[/]")
            if result_url:
                console.print(f"   [link]{result_url}[/link]")

            if show_content:
                content = result.get("content", "")
                content = content[:500] + "..." if len(content) > 500 else content
                console.print(f"   [dim]{content}[/dim]")

            console.print()

    run_async(_search())


# =============================================================================
# SERVE COMMANDS
# =============================================================================

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """Start the API server.

    Runs the FastAPI server for HTTP-based access to DocVector.

    Examples:
        docvector serve
        docvector serve --port 8080
        docvector serve --reload  # For development
    """
    import uvicorn

    console.print(f"[bold blue]Starting DocVector API server[/]")
    console.print(f"  Host: {host}:{port}")
    console.print(f"  Reload: {reload}")
    console.print(f"\n  API docs: http://{host}:{port}/docs\n")

    uvicorn.run(
        "docvector.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def mcp(
    mode: str = typer.Option("local", "--mode", "-m", help="Operating mode: local, cloud, hybrid"),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport protocol: stdio, http, sse"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="DocVector Cloud API key"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="DocVector Cloud API URL"),
):
    """Start the MCP server.

    Runs the Model Context Protocol server for AI code editor integration.
    Supports three modes:

    - local: All data stays on your machine (default, fully private)
    - cloud: Connect to DocVector Cloud for community Q&A
    - hybrid: Local docs + cloud Q&A (recommended)

    Examples:
        docvector mcp                              # Local mode, stdio transport
        docvector mcp --mode hybrid --api-key xxx  # Hybrid mode with cloud
        docvector mcp --transport http             # HTTP for web clients
    """
    from docvector.mcp.server import mcp as mcp_server, set_mcp_config

    console.print(f"[bold blue]Starting DocVector MCP server[/]")
    console.print(f"  Mode: {mode}")
    console.print(f"  Transport: {transport}")

    if mode == "local":
        console.print("  [dim]All data stays on your machine - fully private[/dim]")
    elif mode == "cloud":
        console.print("  [dim]Connected to DocVector Cloud for community Q&A[/dim]")
    elif mode == "hybrid":
        console.print("  [dim]Local docs + cloud Q&A - best of both worlds[/dim]")

    if mode in ("cloud", "hybrid") and not api_key:
        console.print("  [yellow]Warning: No API key provided - cloud features limited[/yellow]")

    console.print()

    # Configure MCP mode
    set_mcp_config(mode=mode, api_url=api_url, api_key=api_key)

    # Run the server
    mcp_server.run(transport=transport if transport != "http" else "streamable-http")


# =============================================================================
# LIBRARY COMMANDS
# =============================================================================

libraries_app = typer.Typer(help="Manage indexed libraries")
app.add_typer(libraries_app, name="libraries")


@libraries_app.command("list")
def list_libraries(
    query: Optional[str] = typer.Option(None, "--search", "-s", help="Search filter"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results"),
):
    """List indexed libraries.

    Examples:
        docvector libraries list
        docvector libraries list --search python
    """
    async def _list():
        from docvector.db import get_db_session
        from docvector.services.library_service import LibraryService

        async with get_db_session() as db:
            lib_service = LibraryService(db)

            if query:
                libraries = await lib_service.search_libraries(query, limit=limit)
            else:
                libraries = await lib_service.list_libraries(skip=0, limit=limit)

            if not libraries:
                console.print("[yellow]No libraries found.[/]")
                return

            table = Table(title="Indexed Libraries")
            table.add_column("Library ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Description")

            for lib in libraries:
                desc = lib.description[:50] + "..." if lib.description and len(lib.description) > 50 else (lib.description or "")
                table.add_row(lib.library_id, lib.name, desc)

            console.print(table)

    run_async(_list())


@libraries_app.command("add")
def add_library(
    library_id: str = typer.Argument(..., help="Library ID (e.g., 'fastapi/docs')"),
    name: str = typer.Argument(..., help="Library name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Description"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Homepage URL"),
):
    """Add a new library.

    Examples:
        docvector libraries add fastapi/docs "FastAPI" --description "Modern Python web framework"
    """
    async def _add():
        from docvector.db import get_db_session
        from docvector.services.library_service import LibraryService

        async with get_db_session() as db:
            lib_service = LibraryService(db)

            library = await lib_service.create_library(
                library_id=library_id,
                name=name,
                description=description,
                homepage_url=url,
            )

            console.print(f"[bold green]✓ Library created:[/] {library.library_id}")

    run_async(_add())


# =============================================================================
# SOURCE COMMANDS
# =============================================================================

sources_app = typer.Typer(help="Manage documentation sources")
app.add_typer(sources_app, name="sources")


@sources_app.command("list")
def list_sources(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results"),
):
    """List configured documentation sources.

    Examples:
        docvector sources list
    """
    async def _list():
        from docvector.db import get_db_session
        from docvector.services.source_service import SourceService

        async with get_db_session() as db:
            source_service = SourceService(db)
            sources = await source_service.list_sources(limit=limit)

            if not sources:
                console.print("[yellow]No sources configured.[/]")
                return

            table = Table(title="Documentation Sources")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Status")
            table.add_column("Last Synced")

            for source in sources:
                status_color = "green" if source.status == "active" else "yellow"
                last_synced = source.last_synced_at.strftime("%Y-%m-%d %H:%M") if source.last_synced_at else "Never"
                table.add_row(
                    source.name,
                    source.type,
                    f"[{status_color}]{source.status}[/{status_color}]",
                    last_synced,
                )

            console.print(table)

    run_async(_list())


# =============================================================================
# STATUS COMMAND
# =============================================================================

@app.command()
def status():
    """Show DocVector status and configuration.

    Displays current configuration, database connection status,
    and indexed content statistics.
    """
    async def _status():
        from docvector.db import get_db_session
        from docvector.services.library_service import LibraryService
        from docvector.services.source_service import SourceService

        console.print("[bold]DocVector Status[/]\n")

        # Configuration
        console.print("[cyan]Configuration:[/]")
        console.print(f"  Database: {settings.database_url[:50]}...")
        console.print(f"  Redis: {settings.redis_url}")
        console.print(f"  Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")
        console.print(f"  Embedding: {settings.embedding_provider}")

        # Database stats
        async with get_db_session() as db:
            lib_service = LibraryService(db)
            source_service = SourceService(db)

            libraries = await lib_service.list_libraries(skip=0, limit=1000)
            sources = await source_service.list_sources(limit=1000)

            console.print(f"\n[cyan]Statistics:[/]")
            console.print(f"  Libraries: {len(libraries)}")
            console.print(f"  Sources: {len(sources)}")

        console.print(f"\n[green]✓ DocVector is running[/]")

    run_async(_status())


if __name__ == "__main__":
    app()
