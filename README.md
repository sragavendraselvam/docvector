# DocVector

> A self-hostable documentation search system powered by vector embeddings and hybrid search

DocVector enables semantic search across your documentation by combining vector similarity with keyword matching. Built with FastAPI, it's easy to deploy and scales from local development to production.

## Features

- **Semantic Search** - Find relevant content even when exact keywords don't match
- **Hybrid Search Engine** - Combines vector embeddings (70%) and keyword search (30%) for optimal results
- **Multiple Embedding Models** - Use local sentence-transformers or OpenAI's embedding API
- **Automatic Web Crawling** - Index entire documentation sites with configurable depth and limits
- **Smart Chunking** - Fixed-size and semantic chunking strategies for optimal context
- **Production Ready** - Redis caching, connection pooling, and health monitoring
- **RESTful API** - Clean API with automatic OpenAPI documentation
- **Flexible Storage** - SQLite for development, PostgreSQL for production
- **Dual Vector DB Support** - ChromaDB for local/embedded, Qdrant for cloud/production

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Development](#development)
- [Architecture](#architecture)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## Quick Start

The fastest way to get started:

```bash
# 1. Start required services
docker-compose up -d

# 2. Run the automated setup
./start.sh
```

That's it! The API will be available at `http://localhost:8000`.

## Installation

### Requirements

- **Python 3.9+**
- **Vector Database** (choose one):
  - **ChromaDB** - Embedded vector database for local deployments (included by default, no setup needed)
  - **Qdrant** - Vector database for cloud/production deployments
- **Redis** (optional) - For caching embeddings and search results (cloud mode)
- **PostgreSQL** (optional) - For production deployments (cloud mode)

### Step-by-Step Setup

#### 1. Clone and Setup Python Environment

```bash
git clone <repository-url>
cd docvector

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# For development with testing tools
pip install -e ".[dev]"
```

#### 2. Start External Services (Optional for Local Mode)

DocVector supports two deployment modes:

**Local Mode (Default)** - No external services needed!
- Uses embedded ChromaDB for vector storage (included in dependencies)
- Uses SQLite for metadata storage
- Perfect for development, testing, and air-gapped environments
- Simply skip this step and proceed to configuration

**Cloud/Production Mode** - Requires external services:

**Option A: Docker Compose (Recommended)**

```bash
docker-compose up -d
```

This starts Redis and Qdrant with proper configuration and persistent storage.

**Option B: Individual Docker Containers**

```bash
# Redis
docker run -d --name docvector-redis -p 6379:6379 redis:7-alpine

# Qdrant
docker run -d --name docvector-qdrant \
  -p 6333:6333 -p 6334:6334 \
  qdrant/qdrant:latest
```

**Option C: Native Installation**

```bash
# macOS with Homebrew
brew install redis qdrant
brew services start redis
brew services start qdrant

# Linux - see Redis and Qdrant documentation
```

#### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your preferred settings (defaults work for local development)
```

#### 4. Initialize Database

```bash
python init_db.py
```

#### 5. Start the Server

```bash
# Using the startup script (recommended)
./start.sh

# Or manually
python -m docvector.api.main
```

Visit `http://localhost:8000/docs` for the interactive API documentation.

## Configuration

Configuration is managed through environment variables with the `DOCVECTOR_` prefix.

### Essential Settings

**Local Mode (Default):**
```bash
# MCP Mode (local = embedded ChromaDB, cloud = Qdrant)
DOCVECTOR_MCP_MODE=local

# Database
DOCVECTOR_DATABASE_URL=sqlite+aiosqlite:///./docvector.db

# ChromaDB (local vector database)
DOCVECTOR_CHROMA_PERSIST_DIRECTORY=./data/chroma
DOCVECTOR_CHROMA_COLLECTION=documents

# Embeddings
DOCVECTOR_EMBEDDING_PROVIDER=local
DOCVECTOR_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

**Cloud/Production Mode:**
```bash
# MCP Mode
DOCVECTOR_MCP_MODE=cloud

# Database
DOCVECTOR_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/docvector

# Redis
DOCVECTOR_REDIS_URL=redis://localhost:6379/0

# Qdrant (cloud vector database)
DOCVECTOR_QDRANT_HOST=localhost
DOCVECTOR_QDRANT_PORT=6333
DOCVECTOR_QDRANT_COLLECTION=documents

# Embeddings
DOCVECTOR_EMBEDDING_PROVIDER=local
DOCVECTOR_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Advanced Configuration

<details>
<summary>Click to expand all configuration options</summary>

```bash
# Application
DOCVECTOR_ENVIRONMENT=development          # development, staging, production
DOCVECTOR_LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR
DOCVECTOR_API_PORT=8000
DOCVECTOR_API_HOST=0.0.0.0
DOCVECTOR_API_RELOAD=true                  # Auto-reload on code changes

# Search Tuning
DOCVECTOR_SEARCH_MIN_SCORE=0.7             # Minimum similarity score (0-1)
DOCVECTOR_SEARCH_VECTOR_WEIGHT=0.7         # Weight for vector similarity
DOCVECTOR_SEARCH_KEYWORD_WEIGHT=0.3        # Weight for keyword matching

# Chunking Strategy
DOCVECTOR_CHUNK_SIZE=1000                  # Characters per chunk
DOCVECTOR_CHUNK_OVERLAP=200                # Overlap between chunks

# Web Crawler
DOCVECTOR_CRAWLER_MAX_DEPTH=3              # Maximum crawl depth
DOCVECTOR_CRAWLER_MAX_PAGES=100            # Maximum pages to crawl
DOCVECTOR_CRAWLER_CONCURRENT_REQUESTS=5    # Parallel requests

# OpenAI (if using OpenAI embeddings)
DOCVECTOR_EMBEDDING_PROVIDER=openai
DOCVECTOR_EMBEDDING_MODEL=text-embedding-3-small
DOCVECTOR_OPENAI_API_KEY=sk-...
```

</details>

### Production Configuration

For production deployments:

```bash
# Use PostgreSQL
DOCVECTOR_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/docvector

# Disable auto-reload
DOCVECTOR_API_RELOAD=false

# Set environment
DOCVECTOR_ENVIRONMENT=production

# Increase connection limits
DOCVECTOR_REDIS_MAX_CONNECTIONS=20
```

## Usage

### Indexing Documentation

Index a documentation website by crawling it:

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.python.org/3/",
    "source_name": "Python 3 Documentation",
    "max_depth": 2,
    "max_pages": 50
  }'
```

The crawler will:
1. Fetch and parse HTML content
2. Extract text from each page
3. Split content into optimized chunks
4. Generate embeddings for each chunk
5. Store in Qdrant for vector search
6. Cache embeddings in Redis

### Searching

Perform a semantic search:

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I handle exceptions in async functions?",
    "limit": 5,
    "min_score": 0.7
  }'
```

Response:

```json
{
  "success": true,
  "results": [
    {
      "chunk_id": "abc123",
      "content": "Relevant text snippet...",
      "score": 0.89,
      "metadata": {
        "source_name": "Python 3 Documentation",
        "url": "https://docs.python.org/3/library/asyncio-task.html",
        "title": "Coroutines and Tasks"
      }
    }
  ],
  "total": 5,
  "query_time_ms": 45
}
```

### Managing Sources

```bash
# List all indexed sources
curl http://localhost:8000/api/v1/sources

# Get details for a specific source
curl http://localhost:8000/api/v1/sources/{source_id}

# Delete a source and all its documents
curl -X DELETE http://localhost:8000/api/v1/sources/{source_id}

# Re-index a source
curl -X POST http://localhost:8000/api/v1/sources/{source_id}/reindex
```

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API information and status |
| `GET` | `/health` | Health check with dependency status |
| `GET` | `/docs` | Interactive API documentation (Swagger UI) |
| `GET` | `/redoc` | Alternative API documentation (ReDoc) |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/search` | Hybrid semantic + keyword search |

**Request Body:**

```json
{
  "query": "string",
  "limit": 10,
  "min_score": 0.7,
  "source_ids": ["optional", "filter"]
}
```

### Sources

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/sources` | List all documentation sources |
| `POST` | `/api/v1/sources` | Create a new source manually |
| `GET` | `/api/v1/sources/{id}` | Get source details |
| `PUT` | `/api/v1/sources/{id}` | Update source metadata |
| `DELETE` | `/api/v1/sources/{id}` | Delete source and documents |

### Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/ingest` | Crawl and index documentation from URL |

**Request Body:**

```json
{
  "url": "https://docs.example.com",
  "source_name": "Example Docs",
  "max_depth": 3,
  "max_pages": 100
}
```

Visit `/docs` for complete API documentation with request/response schemas.

## Development

### Running Tests

```bash
# Run all tests with coverage
pytest --cov=docvector --cov-report=html

# Run specific test file
pytest tests/test_search.py -v

# Run tests in parallel
pytest -n auto

# Run only integration tests
pytest -m integration

# Watch mode (requires pytest-watch)
ptw -- --cov=docvector
```

### Code Quality

```bash
# Format code
black src tests

# Lint
ruff check src tests

# Type checking
mypy src

# Run all checks
black src tests && ruff check src tests && mypy src
```

### Pre-commit Hooks

Install pre-commit hooks to automatically check code before commits:

```bash
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Project Structure

```
docvector/
├── src/docvector/
│   ├── api/                    # FastAPI application
│   │   ├── main.py            # App initialization
│   │   ├── routes/            # API endpoints
│   │   └── schemas/           # Pydantic models
│   ├── db/                     # Database layer
│   │   ├── models.py          # SQLAlchemy models
│   │   └── repositories/      # Data access layer
│   ├── embeddings/             # Embedding providers
│   │   ├── local_embedder.py  # Sentence transformers
│   │   └── openai_embedder.py # OpenAI API
│   ├── search/                 # Search implementations
│   │   ├── vector_search.py   # Vector similarity
│   │   └── hybrid_search.py   # Hybrid search
│   ├── ingestion/              # Content ingestion
│   │   └── web_crawler.py     # Documentation crawler
│   ├── processing/             # Content processing
│   │   ├── parsers/           # HTML, Markdown parsers
│   │   └── chunkers/          # Text chunking strategies
│   ├── vectordb/               # Vector database clients
│   │   └── qdrant_client.py   # Qdrant integration
│   ├── cache/                  # Redis caching
│   ├── services/               # Business logic
│   └── core.py                 # Configuration & logging
├── tests/                      # Test suite
├── docker-compose.yml          # Development services
├── start.sh                    # Automated startup script
├── init_db.py                  # Database initialization
└── pyproject.toml              # Project configuration
```

## Architecture

### System Overview

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│          FastAPI Server             │
│  ┌────────────────────────────────┐ │
│  │      Search Service            │ │
│  │  ┌──────────┬────────────────┐ │ │
│  │  │  Vector  │    Keyword     │ │ │
│  │  │  Search  │    Search      │ │ │
│  │  └──────────┴────────────────┘ │ │
│  └────────────────────────────────┘ │
│  ┌────────────────────────────────┐ │
│  │   Ingestion Service            │ │
│  │  ┌────────┐  ┌──────────────┐ │ │
│  │  │Crawler │→ │   Parser     │ │ │
│  │  └────────┘  └──────┬───────┘ │ │
│  │              ┌──────▼───────┐  │ │
│  │              │   Chunker    │  │ │
│  │              └──────┬───────┘  │ │
│  │              ┌──────▼───────┐  │ │
│  │              │  Embeddings  │  │ │
│  │              └──────────────┘  │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
       │           │           │
       ▼           ▼           ▼
┌──────────┐ ┌──────────────┐ ┌─────────┐
│PostgreSQL│ │ ChromaDB/    │ │  Redis  │
│/SQLite   │ │ Qdrant       │ │ (Cache) │
│(Metadata)│ │ (Vectors)    │ │(Optional)│
└──────────┘ └──────────────┘ └─────────┘
```

### Key Components

- **API Layer**: FastAPI with automatic OpenAPI docs
- **Search Engine**: Hybrid search combining vector and keyword approaches
- **Embedding Service**: Pluggable providers (local sentence-transformers or OpenAI)
- **Vector Store**: ChromaDB (local/embedded) or Qdrant (cloud/production)
- **Cache Layer**: Redis for embedding and result caching (optional, cloud mode only)
- **Database**: SQLAlchemy with async support (SQLite for local, PostgreSQL for cloud)
- **Ingestion Pipeline**: Web crawler → Parser → Chunker → Embedder

### Vector Database Modes

DocVector supports two vector database backends:

**ChromaDB (Local Mode)**
- Embedded, no separate server required
- Stores data in local filesystem (`./data/chroma` by default)
- Perfect for development, testing, and air-gapped deployments
- Lower resource usage, simpler setup
- Suitable for small to medium datasets (< 1M vectors)

**Qdrant (Cloud/Production Mode)**
- Client-server architecture with remote connections
- Supports cloud hosting and horizontal scaling
- Advanced features: distributed search, replication, snapshots
- Better performance for large datasets (> 1M vectors)
- Recommended for production deployments

## Deployment

### Docker

Build and run with Docker:

```dockerfile
# Dockerfile example
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -e .

CMD ["python", "-m", "docvector.api.main"]
```

```bash
# Build
docker build -t docvector:latest .

# Run
docker run -p 8000:8000 --env-file .env docvector:latest
```

### Docker Compose (Full Stack)

The included `docker-compose.yml` can be extended to include the app:

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - redis
      - qdrant
```

### Production Checklist

- [ ] Use PostgreSQL instead of SQLite
- [ ] Set `DOCVECTOR_ENVIRONMENT=production`
- [ ] Disable API auto-reload
- [ ] Configure proper CORS origins
- [ ] Set up reverse proxy (nginx/traefik)
- [ ] Enable HTTPS
- [ ] Configure log aggregation
- [ ] Set up monitoring (health checks, metrics)
- [ ] Use strong credentials for databases
- [ ] Configure backup strategy
- [ ] Set resource limits for containers

## Troubleshooting

### Common Issues

**Database locked error (SQLite)**

SQLite doesn't handle high concurrency well. Switch to PostgreSQL:

```bash
DOCVECTOR_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/docvector
```

**Redis connection refused**

Verify Redis is running:

```bash
redis-cli ping  # Should return PONG

# If not running:
docker-compose up -d redis
```

**Qdrant not found**

Check Qdrant health:

```bash
curl http://localhost:6333/health

# If not running:
docker-compose up -d qdrant
```

**Slow first search**

The embedding model downloads on first use (~90MB). Subsequent requests will be fast due to caching.

**Import errors**

Ensure you installed the package in editable mode:

```bash
pip install -e .
```

### Debug Mode

Enable debug logging:

```bash
DOCVECTOR_LOG_LEVEL=DEBUG python -m docvector.api.main
```

### Performance Tuning

**Improve search speed:**
- Increase `DOCVECTOR_REDIS_MAX_CONNECTIONS`
- Enable Redis persistence
- Use Qdrant's gRPC interface: `DOCVECTOR_QDRANT_USE_GRPC=true`

**Reduce memory usage:**
- Use smaller embedding models
- Reduce chunk size
- Limit concurrent crawler requests

## Contributing

Contributions are welcome! Please check out:

- [Testing Guide](TESTING_GUIDE.md) - How to write and run tests
- [Priority List](PRIORITY_LIST.md) - Features we're working on
- [Competitive Analysis](COMPETITIVE_ANALYSIS.md) - How we compare to alternatives

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make changes and add tests
4. Run tests and linting: `pytest && black . && ruff check .`
5. Commit changes: `git commit -m "Add your feature"`
6. Push to your fork: `git push origin feature/your-feature`
7. Open a Pull Request

## License

[Specify your license here]

## Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/docvector/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-repo/docvector/discussions)
- **Documentation**: Check `/docs` endpoint when running

---

Made with ❤️ for better documentation search
