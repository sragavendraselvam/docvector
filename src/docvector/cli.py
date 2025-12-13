"""DocVector CLI - Command-line interface for documentation search.

Usage:
    docvector index <url>              Index documentation from URL
    docvector search <query>           Search indexed documentation
    docvector serve                    Start the API server
    docvector mcp                      Start the MCP server
    docvector libraries list           List indexed libraries
    docvector sources list             List configured sources
    docvector models list              List available embedding models
    docvector models info <model>      Show model details
    docvector models recommend         Get model recommendation
"""

import asyncio
from typing import Optional

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
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport mode: stdio, http, sse"),
):
    """Start the MCP server.

    Runs the Model Context Protocol server for AI code editor integration.

    Examples:
        docvector mcp                    # stdio for Claude Desktop
        docvector mcp --transport http   # HTTP for web clients
    """
    from docvector.mcp.server import mcp as mcp_server

    console.print(f"[bold blue]Starting DocVector MCP server[/]")
    console.print(f"  Transport: {transport}")

    if transport == "stdio":
        console.print("  Mode: stdio (for Claude Desktop, Cursor, etc.)\n")
    elif transport == "http":
        console.print("  Mode: HTTP (streamable)\n")

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
# MODELS COMMANDS
# =============================================================================

models_app = typer.Typer(help="Manage embedding models")
app.add_typer(models_app, name="models")


@models_app.command("list")
def list_models_cmd(
    provider: Optional[str] = typer.Option(
        None, "--provider", "-p", help="Filter by provider (sentence-transformers, openai)"
    ),
    speed: Optional[str] = typer.Option(
        None, "--speed", "-s", help="Filter by speed (fast, medium, slow)"
    ),
):
    """List available embedding models.

    Shows all supported embedding models grouped by speed category.

    Examples:
        docvector models list
        docvector models list --provider openai
        docvector models list --speed fast
    """
    from docvector.embeddings import (
        DEFAULT_MODEL,
        EMBEDDING_MODELS,
        ModelSpeed,
    )

    # Group models by speed
    speed_groups = {
        ModelSpeed.FAST: [],
        ModelSpeed.MEDIUM: [],
        ModelSpeed.SLOW: [],
    }

    for name, info in EMBEDDING_MODELS.items():
        if provider and info.provider != provider:
            continue
        if speed and info.speed.value != speed:
            continue
        speed_groups[info.speed].append((name, info))

    console.print("\n[bold]Available Embedding Models[/]\n")

    speed_labels = {
        ModelSpeed.FAST: ("FAST MODELS (< 100ms)", "green"),
        ModelSpeed.MEDIUM: ("MEDIUM MODELS (100-500ms)", "yellow"),
        ModelSpeed.SLOW: ("LARGE MODELS (> 500ms)", "red"),
    }

    total_shown = 0
    for speed_cat in [ModelSpeed.FAST, ModelSpeed.MEDIUM, ModelSpeed.SLOW]:
        models = speed_groups[speed_cat]
        if not models:
            continue

        label, color = speed_labels[speed_cat]
        console.print(f"[bold {color}]{label}[/bold {color}]")
        console.print("─" * len(label))

        for name, info in models:
            default_tag = " [yellow][DEFAULT][/yellow]" if name == DEFAULT_MODEL else ""
            console.print(f"  [green]{name}[/green]{default_tag}")
            console.print(
                f"    Dimension: {info.dimension} │ Memory: {info.memory_mb}MB │ Quality: {info.quality.value}"
            )
            console.print(f"    [dim]{info.description}[/dim]")
            console.print()
            total_shown += 1

    if total_shown == 0:
        console.print("[yellow]No models match the specified filters.[/]")
    else:
        console.print(
            "[dim]Use 'docvector models info <model>' for detailed information.[/dim]"
        )


@models_app.command("info")
def model_info_cmd(
    model_name: str = typer.Argument(..., help="Model name to show info for"),
):
    """Show detailed information about a model.

    Displays all metadata for a specific embedding model.

    Examples:
        docvector models info sentence-transformers/all-MiniLM-L6-v2
        docvector models info BAAI/bge-base-en-v1.5
    """
    from docvector.embeddings import get_model_info

    info = get_model_info(model_name)

    if not info:
        console.print(f"[red]Model '{model_name}' not found in registry.[/red]")
        console.print(
            "[dim]Use 'docvector models list' to see available models.[/dim]"
        )
        raise typer.Exit(1)

    console.print(f"\n[bold]Model: {model_name}[/bold]")
    console.print("=" * (len(model_name) + 7))

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Provider", info.provider)
    table.add_row("Dimension", str(info.dimension))
    table.add_row("Speed", info.speed.value)
    table.add_row("Quality", info.quality.value)
    table.add_row("Memory", f"~{info.memory_mb} MB")
    table.add_row("Max Tokens", str(info.max_tokens))

    console.print(table)

    console.print(f"\n[bold]Description:[/bold]")
    console.print(f"  {info.description}")

    console.print(f"\n[bold]Recommended For:[/bold]")
    for use_case in info.use_cases:
        console.print(f"  • {use_case}")

    console.print(f"\n[bold]Configuration:[/bold]")
    console.print(f"  export DOCVECTOR_EMBEDDING_MODEL={model_name}")
    console.print()


@models_app.command("recommend")
def recommend_model_cmd(
    use_case: str = typer.Option(
        "general",
        "--use-case",
        "-u",
        help="Use case: general, technical, code, documentation, production, high-precision",
    ),
):
    """Get a model recommendation for your use case.

    Suggests the best model based on your specific needs.

    Examples:
        docvector models recommend
        docvector models recommend --use-case technical
        docvector models recommend --use-case code
    """
    from docvector.embeddings import get_model_info, get_recommended_model

    model_name = get_recommended_model(use_case)
    info = get_model_info(model_name)

    console.print(f"\n[bold]Recommended Model for '{use_case}' Use Case[/bold]")
    console.print("=" * 45)

    console.print(f"\n  [bold green]Model: {model_name}[/bold green]")

    if info:
        console.print(f"\n  [bold]Why this model:[/bold]")
        console.print(f"    • Quality: {info.quality.value}")
        console.print(f"    • Speed: {info.speed.value}")
        console.print(f"    • Memory: ~{info.memory_mb}MB")
        console.print(f"    • {info.description}")

    console.print(f"\n  [bold]To use this model:[/bold]")
    console.print(f"    export DOCVECTOR_EMBEDDING_MODEL={model_name}")
    console.print()


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
