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
    local: bool = typer.Option(False, "--local", "-l", help="Create local project config instead of global"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive configuration mode"),
):
    """Initialize DocVector configuration.

    Creates a configuration file with default settings and verifies that
    required dependencies (Redis, Qdrant) are accessible. Optionally creates
    database tables.

    Examples:
        docvector init                      # Create global config at ~/.docvector/config.yaml
        docvector init --local              # Create local config at ./docvector.yaml
        docvector init --interactive        # Interactive setup with prompts
        docvector init --force              # Overwrite existing config
    """
    from pathlib import Path
    
    import httpx
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    from docvector.config import get_global_config_path, get_local_config_path, save_config
    from docvector.core import Settings
    
    # Determine config path
    config_path = get_local_config_path() if local else get_global_config_path()
    
    # Check if config already exists
    if config_path.exists() and not force:
        console.print(f"[yellow]Config already exists at {config_path}[/]")
        console.print("Use --force to overwrite")
        raise typer.Exit(1)
    
    console.print(Panel.fit(
        "[bold blue]DocVector Initialization[/bold blue]",
        subtitle=f"Config: {config_path}"
    ))
    
    # Interactive mode: prompt for configuration values
    config_overrides = {}
    if interactive:
        console.print("\n[bold cyan]Interactive Configuration[/bold cyan]")
        console.print("[dim]Press Enter to use default values[/dim]\n")
        
        # Embedding provider
        embedding_provider = typer.prompt(
            "Embedding provider (local/openai)",
            default="local",
            show_default=True
        )
        config_overrides["embedding_provider"] = embedding_provider
        
        # Embedding model based on provider
        if embedding_provider == "local":
            embedding_model = typer.prompt(
                "Embedding model",
                default="sentence-transformers/all-MiniLM-L6-v2",
                show_default=True
            )
        elif embedding_provider == "openai":
            embedding_model = typer.prompt(
                "Embedding model",
                default="text-embedding-3-small",
                show_default=True
            )
            openai_key = typer.prompt(
                "OpenAI API key",
                default="",
                hide_input=True
            )
            if openai_key:
                config_overrides["openai_api_key"] = openai_key
        else:
            embedding_model = settings.embedding_model
        
        config_overrides["embedding_model"] = embedding_model
        
        # Database URL
        database_url = typer.prompt(
            "Database URL",
            default=settings.database_url,
            show_default=False
        )
        config_overrides["database_url"] = database_url
        
        # Redis URL
        redis_url = typer.prompt(
            "Redis URL",
            default=settings.redis_url,
            show_default=False
        )
        config_overrides["redis_url"] = redis_url
        
        # Qdrant host and port
        qdrant_host = typer.prompt(
            "Qdrant host",
            default=settings.qdrant_host,
            show_default=True
        )
        config_overrides["qdrant_host"] = qdrant_host
        
        qdrant_port = typer.prompt(
            "Qdrant port",
            default=str(settings.qdrant_port),
            show_default=True
        )
        config_overrides["qdrant_port"] = int(qdrant_port)
        
        # Chunking settings
        chunk_size = typer.prompt(
            "Chunk size (characters)",
            default=str(settings.chunk_size),
            show_default=True
        )
        config_overrides["chunk_size"] = int(chunk_size)
        
        chunk_overlap = typer.prompt(
            "Chunk overlap (characters)",
            default=str(settings.chunk_overlap),
            show_default=True
        )
        config_overrides["chunk_overlap"] = int(chunk_overlap)
        
        console.print()
    
    # Create settings with overrides
    final_settings = Settings(**{**settings.model_dump(), **config_overrides}) if config_overrides else settings
    
    # Create config file
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating configuration file...", total=None)
        
        try:
            save_config(config_path, final_settings, template=True)
            progress.update(task, completed=True)
            console.print(f"[green]✓[/green] Config created: {config_path}")
        except Exception as e:
            console.print(f"[red]✗ Failed to create config:[/red] {e}")
            raise typer.Exit(1)
    
    # Initialize database tables
    console.print("\n[bold]Initializing database...[/]")
    
    async def init_database():
        """Create database tables."""
        try:
            from docvector.db import get_engine
            from docvector.models import Base
            
            engine = get_engine()
            
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
            
            console.print("[green]✓[/green] Database: Tables created")
            return True
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Database: Failed to create tables - {e}")
            return False
    
    db_initialized = run_async(init_database())
    
    # Verify dependencies
    console.print("\n[bold]Checking dependencies...[/]")
    
    dependencies_ok = True
    
    # Check Redis
    try:
        import redis
        r = redis.from_url(final_settings.redis_url, socket_connect_timeout=2)
        r.ping()
        console.print("[green]✓[/green] Redis: Connected")
    except Exception as e:
        console.print(f"[red]✗[/red] Redis: Not accessible - {e}")
        console.print(f"   Expected at: {final_settings.redis_url}")
        dependencies_ok = False
    
    # Check Qdrant
    try:
        qdrant_url = f"http://{final_settings.qdrant_host}:{final_settings.qdrant_port}/health"
        response = httpx.get(qdrant_url, timeout=2.0)
        if response.status_code == 200:
            console.print("[green]✓[/green] Qdrant: Connected")
        else:
            console.print(f"[red]✗[/red] Qdrant: Unhealthy (status {response.status_code})")
            dependencies_ok = False
    except Exception as e:
        console.print(f"[red]✗[/red] Qdrant: Not accessible - {e}")
        console.print(f"   Expected at: {final_settings.qdrant_host}:{final_settings.qdrant_port}")
        dependencies_ok = False
    
    # Check Database connectivity
    async def check_db():
        try:
            from docvector.db import get_db_session
            async with get_db_session() as db:
                # Try a simple query
                from sqlalchemy import text
                await db.execute(text("SELECT 1"))
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] Database: Not accessible - {e}")
            console.print(f"   URL: {final_settings.database_url[:50]}...")
            return False
    
    db_ok = run_async(check_db())
    if db_ok:
        console.print("[green]✓[/green] Database: Connected")
    else:
        dependencies_ok = False
    
    # Final status
    console.print()
    if dependencies_ok and db_initialized:
        console.print(Panel.fit(
            "[bold green]✓ Initialization complete![/bold green]\n\n"
            "Next steps:\n"
            "  1. Edit config: " + str(config_path) + "\n"
            "  2. Index documentation: docvector index <url>\n"
            "  3. Search: docvector search <query>",
            border_style="green"
        ))
    else:
        console.print(Panel.fit(
            "[bold yellow]⚠ Setup incomplete[/bold yellow]\n\n"
            "Some dependencies are not accessible or database initialization failed.\n"
            "Start required services with: docker-compose up -d",
            border_style="yellow"
        ))
        raise typer.Exit(1)


# =============================================================================
# STATS COMMAND
# =============================================================================

@app.command()
def stats():
    """Show DocVector statistics and status.

    Displays comprehensive statistics including indexed documents, chunks,
    libraries, sources, vector database information, and Redis cache stats.

    Examples:
        docvector stats
    """
    async def _stats():
        from rich.panel import Panel
        
        from docvector.db import get_db_session
        from docvector.services.library_service import LibraryService
        from docvector.services.source_service import SourceService
        from docvector.vectordb import QdrantVectorDB
        
        console.print(Panel.fit("[bold]DocVector Statistics[/bold]"))
        
        # Database statistics
        async with get_db_session() as db:
            lib_service = LibraryService(db)
            source_service = SourceService(db)
            
            # Get library and source counts
            libraries = await lib_service.list_libraries(skip=0, limit=10000)
            sources = await source_service.list_sources(limit=10000)
            
            # Count documents and chunks
            from sqlalchemy import func, select
            
            from docvector.models import Chunk, Document
            
            doc_count_query = select(func.count(Document.id))
            doc_count_result = await db.execute(doc_count_query)
            doc_count = doc_count_result.scalar() or 0
            
            chunk_count_query = select(func.count(Chunk.id))
            chunk_count_result = await db.execute(chunk_count_query)
            chunk_count = chunk_count_result.scalar() or 0
        
        # Create statistics table
        table = Table(title="Indexed Content", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")
        
        table.add_row("Libraries", f"{len(libraries):,}")
        table.add_row("Sources", f"{len(sources):,}")
        table.add_row("Documents", f"{doc_count:,}")
        table.add_row("Chunks", f"{chunk_count:,}")
        
        console.print(table)
        
        # Vector database statistics (ENHANCED)
        console.print()  # Spacing
        try:
            vector_db = QdrantVectorDB()
            collection_info = await vector_db.get_collection_info(settings.qdrant_collection)
            
            if collection_info:
                vector_table = Table(title="Vector Database", show_header=False)
                vector_table.add_column("Metric", style="cyan")
                vector_table.add_column("Value", style="green", justify="right")
                
                vector_table.add_row("Collection", collection_info["name"])
                vector_table.add_row("Vectors", f"{collection_info['vectors_count']:,}")
                vector_table.add_row("Points", f"{collection_info['points_count']:,}")
                vector_table.add_row("Dimensions", str(collection_info["vector_size"]))
                vector_table.add_row("Distance Metric", collection_info["distance"])
                
                # Color-code status
                status = collection_info["status"]
                if "green" in status.lower() or "ready" in status.lower():
                    status_display = f"[green]●[/green] {status}"
                else:
                    status_display = f"[yellow]●[/yellow] {status}"
                vector_table.add_row("Status", status_display)
                
                console.print(vector_table)
            else:
                console.print("[yellow]⚠ Vector database collection not found[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠ Vector database not accessible: {e}[/yellow]")
        
        # Redis Cache Statistics (NEW)
        console.print()  # Spacing
        redis_table = Table(title="Redis Cache", show_header=False)
        redis_table.add_column("Metric", style="cyan")
        redis_table.add_column("Value", style="yellow", justify="right")
        
        try:
            import redis
            r = redis.from_url(settings.redis_url, socket_connect_timeout=2, decode_responses=True)
            
            # Ping to verify connection
            r.ping()
            
            # Get Redis info
            memory_info = r.info("memory")
            stats_info = r.info("stats")
            
            # Connection status
            redis_table.add_row("Status", "[green]●[/green] Connected")
            
            # Memory usage
            used_memory = memory_info.get("used_memory_human", "N/A")
            redis_table.add_row("Memory Usage", used_memory)
            
            # Peak memory
            peak_memory = memory_info.get("used_memory_peak_human", "N/A")
            redis_table.add_row("Peak Memory", peak_memory)
            
            # Total keys
            db_size = r.dbsize()
            redis_table.add_row("Total Keys", f"{db_size:,}")
            
            # Hit rate (if stats available)
            hits = stats_info.get("keyspace_hits", 0)
            misses = stats_info.get("keyspace_misses", 0)
            total = hits + misses
            if total > 0:
                hit_rate = (hits / total) * 100
                hit_rate_color = "green" if hit_rate >= 80 else "yellow" if hit_rate >= 60 else "red"
                redis_table.add_row("Hit Rate", f"[{hit_rate_color}]{hit_rate:.1f}%[/{hit_rate_color}]")
            else:
                redis_table.add_row("Hit Rate", "[dim]N/A[/dim]")
            
            # Connected clients
            connected_clients = r.info("clients").get("connected_clients", 0)
            redis_table.add_row("Connected Clients", str(connected_clients))
            
            console.print(redis_table)
            
        except Exception as e:
            redis_table.add_row("Status", f"[red]✗[/red] Not accessible")
            redis_table.add_row("Error", str(e)[:50])
            console.print(redis_table)
        
        # Configuration table
        console.print()  # Spacing
        conf_table = Table(title="Configuration", show_header=False)
        conf_table.add_column("Setting", style="cyan")
        conf_table.add_column("Value", style="yellow")
        
        conf_table.add_row("Embedding Provider", settings.embedding_provider)
        conf_table.add_row("Embedding Model", settings.embedding_model)
        conf_table.add_row("Database", settings.database_url[:60] + ("..." if len(settings.database_url) > 60 else ""))
        conf_table.add_row("Vector Store", f"{settings.qdrant_host}:{settings.qdrant_port}")
        conf_table.add_row("Collection", settings.qdrant_collection)
        conf_table.add_row("Chunk Size", f"{settings.chunk_size} chars")
        conf_table.add_row("Chunk Overlap", f"{settings.chunk_overlap} chars")
        
        console.print(conf_table)
        
        # Recent sources (ENHANCED with better colors)
        if sources:
            console.print("\n[bold]Recent Sources:[/bold]")
            recent_table = Table()
            recent_table.add_column("Name", style="cyan", no_wrap=False)
            recent_table.add_column("Type", style="green")
            recent_table.add_column("Status", justify="center")
            recent_table.add_column("Last Synced", style="dim")
            
            for source in sources[:5]:  # Show only 5 most recent
                # Enhanced status colors with bullet points
                if source.status == "active":
                    status_display = "[green]●[/green] active"
                elif source.status == "syncing":
                    status_display = "[blue]●[/blue] syncing"
                elif source.status == "error":
                    status_display = "[red]●[/red] error"
                elif source.status == "pending":
                    status_display = "[yellow]●[/yellow] pending"
                else:
                    status_display = f"[dim]●[/dim] {source.status}"
                
                # Format last synced
                if source.last_synced_at:
                    last_synced = source.last_synced_at.strftime("%Y-%m-%d %H:%M")
                else:
                    last_synced = "[dim]Never[/dim]"
                
                recent_table.add_row(
                    source.name[:40] + ("..." if len(source.name) > 40 else ""),
                    source.type,
                    status_display,
                    last_synced,
                )
            
            console.print(recent_table)
    
    run_async(_stats())


# =============================================================================
# EXPORT COMMAND
# =============================================================================

@app.command()
def export(
    output: Optional[str] = typer.Argument(None, help="Output file path (default: stdout)"),
    pretty: bool = typer.Option(True, "--pretty/--compact", help="Pretty-print JSON"),
):
    """Export DocVector configuration and metadata.

    Exports libraries, sources, and settings to JSON format for backup
    or migration to another environment. Does NOT export document content
    or vector embeddings (those can be regenerated by re-indexing).

    Examples:
        docvector export > backup.json
        docvector export backup.json
        docvector export config.json --compact
    """
    import json
    from datetime import datetime
    
    async def _export():
        from docvector.db import get_db_session
        from docvector.services.library_service import LibraryService
        from docvector.services.source_service import SourceService
        
        export_data = {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "libraries": [],
            "sources": [],
            "settings": {}
        }
        
        # Export libraries
        async with get_db_session() as db:
            lib_service = LibraryService(db)
            source_service = SourceService(db)
            
            libraries = await lib_service.list_libraries(skip=0, limit=10000)
            for lib in libraries:
                export_data["libraries"].append({
                    "library_id": lib.library_id,
                    "name": lib.name,
                    "description": lib.description,
                    "homepage_url": lib.homepage_url,
                })
            
            # Export sources
            sources = await source_service.list_sources(limit=10000)
            for source in sources:
                # Find associated library_id if exists
                library_id = None
                if source.library_id:
                    for lib in libraries:
                        if lib.id == source.library_id:
                            library_id = lib.library_id
                            break
                
                export_data["sources"].append({
                    "name": source.name,
                    "type": source.type,
                    "config": source.config,
                    "library_id": library_id,
                    "status": source.status,
                })
        
        # Export relevant settings (exclude sensitive data)
        export_data["settings"] = {
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "chunking_strategy": settings.chunking_strategy,
            "embedding_model": settings.embedding_model,
            "crawler_max_depth": settings.crawler_max_depth,
            "crawler_max_pages": settings.crawler_max_pages,
        }
        
        # Format JSON
        indent = 2 if pretty else None
        json_output = json.dumps(export_data, indent=indent, ensure_ascii=False)
        
        # Write to file or stdout
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json_output)
            console.print(f"[green]✓ Exported to {output}[/]")
            console.print(f"  Libraries: {len(export_data['libraries'])}")
            console.print(f"  Sources: {len(export_data['sources'])}")
        else:
            # Output to stdout for piping
            print(json_output)
    
    run_async(_export())


# =============================================================================
# IMPORT COMMAND
# =============================================================================

@app.command()
def import_config(
    input_file: str = typer.Argument(..., help="Input JSON file to import"),
    merge: bool = typer.Option(False, "--merge", "-m", help="Merge with existing data instead of replacing"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be imported without making changes"),
):
    """Import DocVector configuration and metadata.

    Imports libraries and sources from a JSON export file. By default,
    this will skip items that already exist. Use --merge to update existing items.

    After import, you'll need to re-index sources to regenerate documents
    and vector embeddings.

    Examples:
        docvector import backup.json
        docvector import backup.json --merge
        docvector import backup.json --dry-run
    """
    import json
    from pathlib import Path
    
    from rich.panel import Panel
    
    async def _import():
        # Read import file
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                import_data = json.load(f)
        except FileNotFoundError:
            console.print(f"[red]Error: File not found: {input_file}[/]")
            raise typer.Exit(1)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error: Invalid JSON: {e}[/]")
            raise typer.Exit(1)
        
        # Validate format
        if "version" not in import_data:
            console.print("[red]Error: Invalid export file (missing version)[/]")
            raise typer.Exit(1)
        
        libraries = import_data.get("libraries", [])
        sources = import_data.get("sources", [])
        
        console.print(Panel.fit(
            f"[bold]Import Preview[/bold]\n\n"
            f"Libraries: {len(libraries)}\n"
            f"Sources: {len(sources)}\n"
            f"Exported: {import_data.get('exported_at', 'unknown')}",
            border_style="blue"
        ))
        
        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes will be made[/]")
            
            if libraries:
                console.print("\n[bold]Libraries to import:[/]")
                for lib in libraries:
                    console.print(f"  • {lib['library_id']}: {lib['name']}")
            
            if sources:
                console.print("\n[bold]Sources to import:[/]")
                for src in sources:
                    console.print(f"  • {src['name']} ({src['type']})")
            
            return
        
        # Perform import
        from docvector.db import get_db_session
        from docvector.models import Source
        from docvector.services.library_service import LibraryService
        from docvector.services.source_service import SourceService
        
        imported_libs = 0
        imported_sources = 0
        skipped_libs = 0
        skipped_sources = 0
        
        async with get_db_session() as db:
            lib_service = LibraryService(db)
            source_service = SourceService(db)
            
            # Import libraries
            for lib_data in libraries:
                try:
                    # Check if library already exists
                    existing = await lib_service.get_library_by_id(lib_data["library_id"])
                    
                    if existing:
                        if merge:
                            # Update existing library
                            existing.name = lib_data.get("name", existing.name)
                            existing.description = lib_data.get("description", existing.description)
                            existing.homepage_url = lib_data.get("homepage_url", existing.homepage_url)
                            await db.commit()
                            imported_libs += 1
                        else:
                            skipped_libs += 1
                    else:
                        # Create new library
                        await lib_service.create_library(
                            library_id=lib_data["library_id"],
                            name=lib_data["name"],
                            description=lib_data.get("description"),
                            homepage_url=lib_data.get("homepage_url"),
                        )
                        imported_libs += 1
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to import library {lib_data.get('library_id')}: {e}[/]")
            
            # Import sources
            for src_data in sources:
                try:
                    # Find library ID if specified
                    library_db_id = None
                    if src_data.get("library_id"):
                        lib = await lib_service.get_library_by_id(src_data["library_id"])
                        if lib:
                            library_db_id = lib.id
                    
                    # Check if source with same name exists
                    existing_sources = await source_service.list_sources(limit=10000)
                    existing = next((s for s in existing_sources if s.name == src_data["name"]), None)
                    
                    if existing:
                        if merge:
                            # Update existing source
                            existing.type = src_data.get("type", existing.type)
                            existing.config = src_data.get("config", existing.config)
                            existing.library_id = library_db_id
                            await db.commit()
                            imported_sources += 1
                        else:
                            skipped_sources += 1
                    else:
                        # Create new source
                        source = Source(
                            name=src_data["name"],
                            type=src_data["type"],
                            config=src_data.get("config", {}),
                            status=src_data.get("status", "pending"),
                            library_id=library_db_id,
                        )
                        await source_service.create_source(source)
                        await db.commit()
                        imported_sources += 1
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to import source {src_data.get('name')}: {e}[/]")
        
        # Summary
        console.print(f"\n[bold green]✓ Import complete![/]")
        console.print(f"\n[cyan]Libraries:[/]")
        console.print(f"  Imported: {imported_libs}")
        if skipped_libs > 0:
            console.print(f"  Skipped (already exist): {skipped_libs}")
        
        console.print(f"\n[cyan]Sources:[/]")
        console.print(f"  Imported: {imported_sources}")
        if skipped_sources > 0:
            console.print(f"  Skipped (already exist): {skipped_sources}")
        
        if imported_sources > 0:
            console.print(f"\n[yellow]Note: Run 'docvector index' for each source to regenerate content and vectors[/]")
    
    run_async(_import())


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
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        from docvector.db import get_db_session
        from docvector.services.ingestion_service import IngestionService

        console.print(f"[bold blue]Indexing:[/] {url}")
        console.print(f"  Max depth: {max_depth}, Max pages: {max_pages}\n")

        try:
            # Use Progress with spinner and text for better visual feedback
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                
                task = progress.add_task("[cyan]Crawling and indexing...", total=None)
                
                async with get_db_session() as db:
                    ingestion_service = IngestionService(db)

                    result = await ingestion_service.ingest_url(
                        url=url,
                        library_id=library_id,
                        max_depth=max_depth,
                        max_pages=max_pages,
                    )
                
                progress.update(task, description="[green]✓ Complete!")

            console.print(f"\n[bold green]✓ Indexing complete![/]")
            console.print(f"  Documents indexed: {result.get('documents_indexed', 0)}")
            console.print(f"  Chunks created: {result.get('chunks_created', 0)}")
            
            if result.get('errors'):
                console.print(f"\n[yellow]⚠ Warnings:[/]")
                for error in result.get('errors', [])[:5]:  # Show first 5 errors
                    console.print(f"  • {error}")
        
        except ConnectionError as e:
            console.print(f"\n[bold red]✗ Connection failed:[/] {e}")
            console.print("\n[yellow]Make sure services are running:[/]")
            console.print("  docker-compose up -d")
            raise typer.Exit(1)
        
        except ValueError as e:
            console.print(f"\n[bold red]✗ Invalid URL:[/] {e}")
            console.print("\n[yellow]Hint:[/] URL must start with http:// or https://")
            raise typer.Exit(1)
        
        except Exception as e:
            console.print(f"\n[bold red]✗ Indexing failed:[/] {e}")
            logger.exception("Index command failed")
            raise typer.Exit(1)

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
    format: str = typer.Option("text", "--format", "-f", help="Output format (text/json)"),
):
    """Search indexed documentation.

    Uses hybrid search (vector + keyword) to find relevant documentation chunks.

    Examples:
        docvector search "how to handle async errors"
        docvector search "authentication" --library fastapi/docs
        docvector search "database connection" --limit 10 --content
        docvector search "async" --format json | jq '.results[0].title'
    """
    async def _search():
        import json
        from docvector.db import get_db_session
        from docvector.services.search_service import SearchService
        
        try:
            search_service = SearchService()
            
            filters = {}
            if library:
                from docvector.services.library_service import LibraryService
                async with get_db_session() as db:
                    lib_service = LibraryService(db)
                    lib = await lib_service.get_library_by_id(library)
                    if lib:
                        filters["library_id"] = str(lib.id)
                    else:
                        if format == "json":
                            print(json.dumps({"error": f"Library not found: {library}"}))
                        else:
                            console.print(f"[bold red]✗ Library not found:[/] {library}")
                        raise typer.Exit(1)
            
            # Only show spinner for text output
            if format == "text":
                with console.status("[bold green]Searching..."):
                    results = await search_service.search(
                        query=query,
                        limit=limit,
                        search_type="hybrid",
                        filters=filters,
                    )
            else:
                results = await search_service.search(
                    query=query,
                    limit=limit,
                    search_type="hybrid",
                    filters=filters,
                )
            
            if not results:
                if format == "json":
                    output = {
                        "query": query,
                        "count": 0,
                        "results": []
                    }
                    print(json.dumps(output, indent=2))
                else:
                    console.print("[yellow]No results found.[/]")
                return
            
            # Format output
            if format == "json":
                # JSON output
                output = {
                    "query": query,
                    "count": len(results),
                    "results": [
                        {
                            "rank": i + 1,
                            "title": r.get("title", "Untitled"),
                            "url": r.get("url", ""),
                            "score": round(r.get("score", 0), 4),
                            "content": r.get("content", "") if show_content else None,
                            "chunk_id": r.get("chunk_id", ""),
                            "document_id": r.get("document_id", ""),
                        }
                        for i, r in enumerate(results)
                    ]
                }
                print(json.dumps(output, indent=2))
            else:
                # Text output (existing with improvements)
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
        
        except ConnectionError as e:
            if format == "json":
                print(json.dumps({"error": "Connection failed", "details": str(e)}))
            else:
                console.print(f"[bold red]✗ Connection failed:[/] {e}")
                console.print("\n[yellow]Make sure services are running:[/]")
                console.print("  docker-compose up -d")
            raise typer.Exit(1)
        
        except Exception as e:
            if format == "json":
                print(json.dumps({"error": "Search failed", "details": str(e)}))
            else:
                console.print(f"[bold red]✗ Search failed:[/] {e}")
                logger.exception("Search command failed")
            raise typer.Exit(1)

    run_async(_search())


# =============================================================================
# SOURCES COMMANDS
# =============================================================================

# Create a sub-application for sources commands
sources_app = typer.Typer(help="Manage documentation sources")
app.add_typer(sources_app, name="sources")


@sources_app.command("list")
def sources_list(
    limit: int = typer.Option(100, "--limit", "-n", help="Max sources to show"),
):
    """List all documentation sources.
    
    Examples:
        docvector sources list
        docvector sources list --limit 50
    """
    async def _list():
        from docvector.db import get_db_session
        from docvector.services.source_service import SourceService
        
        try:
            async with get_db_session() as db:
                source_service = SourceService(db)
                sources = await source_service.list_sources(limit=limit)
            
            if not sources:
                console.print("[yellow]No sources found.[/]")
                console.print("\n[dim]Add a source with:[/dim]")
                console.print("  docvector sources add <name> <url>")
                return
            
            table = Table(title=f"Documentation Sources ({len(sources)})")
            table.add_column("Name", style="cyan", no_wrap=False)
            table.add_column("Type", style="green")
            table.add_column("Status", justify="center")
            table.add_column("Last Synced", style="dim")
            
            for source in sources:
                status = source.status
                if status == "active":
                    status_display = "[green]●[/green] active"
                elif status == "error":
                    status_display = "[red]●[/red] error"
                elif status == "syncing":
                    status_display = "[blue]●[/blue] syncing"
                else:
                    status_display = f"[yellow]●[/yellow] {status}"
                
                last_synced = source.last_synced_at.strftime("%Y-%m-%d %H:%M") if source.last_synced_at else "[dim]Never[/dim]"
                
                table.add_row(
                    source.name[:50] + ("..." if len(source.name) > 50 else ""),
                    source.type,
                    status_display,
                    last_synced,
                )
            
            console.print(table)
        
        except Exception as e:
            console.print(f"[bold red]✗ Failed to list sources:[/] {e}")
            logger.exception("Sources list command failed")
            raise typer.Exit(1)
    
    run_async(_list())


@sources_app.command("add")
def sources_add(
    name: str = typer.Argument(..., help="Source name"),
    url: str = typer.Argument(..., help="Source URL"),
    source_type: str = typer.Option("web", "--type", "-t", help="Source type (web/github/file)"),
    library_id: Optional[str] = typer.Option(None, "--library", "-l", help="Associate with library ID"),
):
    """Add a new documentation source.
    
    Examples:
        docvector sources add "FastAPI Docs" https://fastapi.tiangolo.com
        docvector sources add "Python Docs" https://docs.python.org/3/ --type web
    """
    async def _add():
        from docvector.db import get_db_session
        from docvector.services.source_service import SourceService
        
        console.print(f"[bold blue]Adding source:[/] {name}")
        console.print(f"  URL: {url}")
        console.print(f"  Type: {source_type}\n")
        
        try:
            async with get_db_session() as db:
                source_service = SourceService(db)
                
                # Check if source already exists
                existing_sources = await source_service.list_sources(limit=1000)
                if any(s.name == name for s in existing_sources):
                    console.print(f"[bold red]✗ Source already exists:[/] {name}")
                    console.print("\n[yellow]Hint:[/] Use a different name or remove the existing source first")
                    raise typer.Exit(1)
                
                source = await source_service.create_source(
                    name=name,
                    type=source_type,
                    config={"url": url},
                    library_id=library_id,
                )
                
                await db.commit()
            
            console.print(f"[bold green]✓ Source added successfully![/]")
            console.print(f"  ID: {source.id}")
            console.print(f"  Name: {source.name}")
            console.print(f"\n[dim]Index this source with:[/dim]")
            console.print(f"  docvector index {url}")
        
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[bold red]✗ Failed to add source:[/] {e}")
            logger.exception("Sources add command failed")
            raise typer.Exit(1)
    
    run_async(_add())


@sources_app.command("remove")
def sources_remove(
    name: str = typer.Argument(..., help="Source name to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove a documentation source and its documents.
    
    Examples:
        docvector sources remove "FastAPI Docs"
        docvector sources remove "Python Docs" --force
    """
    async def _remove():
        from docvector.db import get_db_session
        from docvector.services.source_service import SourceService
        
        try:
            async with get_db_session() as db:
                source_service = SourceService(db)
                
                # Find source by name
                sources = await source_service.list_sources(limit=1000)
                source = next((s for s in sources if s.name == name), None)
                
                if not source:
                    console.print(f"[bold red]✗ Source not found:[/] {name}")
                    console.print("\n[yellow]Hint:[/] List sources with 'docvector sources list'")
                    raise typer.Exit(1)
                
                # Confirm deletion
                if not force:
                    console.print(f"[bold yellow]⚠ Warning:[/] This will delete source '{name}' and all its documents.")
                    confirm = typer.confirm("Are you sure?")
                    if not confirm:
                        console.print("Cancelled.")
                        return
                
                # Delete source
                await source_service.delete_source(source.id)
                await db.commit()
                
                console.print(f"[bold green]✓ Source removed successfully![/]")
        
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[bold red]✗ Failed to remove source:[/] {e}")
            logger.exception("Sources remove command failed")
            raise typer.Exit(1)
    
    run_async(_remove())


@sources_app.command("info")
def sources_info(
    name: str = typer.Argument(..., help="Source name"),
):
    """Show detailed information about a source.
    
    Examples:
        docvector sources info "FastAPI Docs"
    """
    async def _info():
        import json
        from docvector.db import get_db_session
        from docvector.services.source_service import SourceService
        from rich.panel import Panel
        
        try:
            async with get_db_session() as db:
                source_service = SourceService(db)
                
                sources = await source_service.list_sources(limit=1000)
                source = next((s for s in sources if s.name == name), None)
                
                if not source:
                    console.print(f"[bold red]✗ Source not found:[/] {name}")
                    console.print("\n[yellow]Hint:[/] List sources with 'docvector sources list'")
                    raise typer.Exit(1)
                
                # Create info table
                info_table = Table(show_header=False, box=None)
                info_table.add_column("Property", style="cyan")
                info_table.add_column("Value")
                
                info_table.add_row("Name", source.name)
                info_table.add_row("Type", source.type)
                info_table.add_row("Status", f"[{'green' if source.status == 'active' else 'yellow'}]{source.status}[/]")
                info_table.add_row("Created", source.created_at.strftime("%Y-%m-%d %H:%M:%S"))
                info_table.add_row("Last Synced", source.last_synced_at.strftime("%Y-%m-%d %H:%M:%S") if source.last_synced_at else "Never")
                
                if source.config:
                    config_str = json.dumps(source.config, indent=2)
                    info_table.add_row("Config", config_str)
                
                if source.error_message:
                    info_table.add_row("Error", f"[red]{source.error_message}[/red]")
                
                console.print(Panel(info_table, title=f"Source: {name}", border_style="cyan"))
        
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[bold red]✗ Failed to get source info:[/] {e}")
            logger.exception("Sources info command failed")
            raise typer.Exit(1)
    
    run_async(_info())


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


@sources_app.command("add")
def add_source(
    name: str = typer.Argument(..., help="Source name"),
    url: str = typer.Argument(..., help="Source URL"),
    source_type: str = typer.Option("web", "--type", "-t", help="Source type (web, git, api)"),
    library_id: Optional[str] = typer.Option(None, "--library", "-l", help="Associated library ID"),
):
    """Add a new documentation source.

    Examples:
        docvector sources add "FastAPI Docs" "https://fastapi.tiangolo.com/"
        docvector sources add "Python Docs" "https://docs.python.org/3/" --library python/docs
    """
    async def _add():
        from docvector.db import get_db_session
        from docvector.models import Source
        from docvector.services.source_service import SourceService
        
        async with get_db_session() as db:
            source_service = SourceService(db)
            
            # Create source
            source = Source(
                name=name,
                type=source_type,
                config={"url": url},
                status="pending",
            )
            
            if library_id:
                from docvector.services.library_service import LibraryService
                lib_service = LibraryService(db)
                library = await lib_service.get_library_by_id(library_id)
                if library:
                    source.library_id = library.id
                else:
                    console.print(f"[yellow]Warning: Library '{library_id}' not found[/]")
            
            created_source = await source_service.create_source(source)
            await db.commit()
            
            console.print(f"[bold green]✓ Source added:[/] {created_source.name}")
            console.print(f"  ID: {created_source.id}")
            console.print(f"  Type: {created_source.type}")
            console.print(f"  URL: {url}")
    
    run_async(_add())


@sources_app.command("remove")
def remove_source(
    source_id: int = typer.Argument(..., help="Source ID to remove"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a documentation source.

    This will delete the source and all its associated documents.

    Examples:
        docvector sources remove 123
        docvector sources remove 123 --yes
    """
    async def _remove():
        from docvector.db import get_db_session
        from docvector.services.source_service import SourceService
        
        async with get_db_session() as db:
            source_service = SourceService(db)
            
            # Get source details
            source = await source_service.get_source(source_id)
            if not source:
                console.print(f"[red]Error: Source {source_id} not found[/]")
                raise typer.Exit(1)
            
            # Confirm deletion
            if not confirm:
                console.print(f"[yellow]About to delete source:[/] {source.name}")
                console.print("This will remove all associated documents and chunks.")
                if not typer.confirm("Are you sure?"):
                    console.print("Cancelled")
                    raise typer.Exit(0)
            
            # Delete source
            await source_service.delete_source(source_id)
            await db.commit()
            
            console.print(f"[bold green]✓ Source removed:[/] {source.name}")
    
    run_async(_remove())


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
