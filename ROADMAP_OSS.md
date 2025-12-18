# DocVector OSS Roadmap

**Repository:** github.com/docvector-hub/docvector (Public) **License:** MIT / Apache 2.0 **Last Updated:** December 5, 2025 **Product Owner:** \[TBD\]

---

## Executive Summary

The OSS repository provides a **self-hostable documentation search engine with MCP server**. Goal: Enable developers to run DocVector locally with zero cloud dependency, while providing an excellent developer experience that drives adoption.

**Target Users:**

- Self-hosters (data-sensitive companies)  
- OSS developers (no cost, full control)  
- Early adopters experimenting with MCP  
- Developers embedding DocVector in their tools

---

## Current State

| Component | Status | Completion |
| :---- | :---- | :---- |
| Search Engine (hybrid) | Production | 90% |
| MCP Server | Production | 90% |
| Web Crawler | Production | 85% |
| Docker Setup | Production | 80% |
| Documentation | Good | 75% |
| CLI Tool | Missing | 0% |
| Examples | Partial | 30% |

---

## Phase 1: OSS Launch Readiness (Weeks 1-4)

### OSS-1.1: CLI Tool Implementation

**Priority:** P0 \- Critical **Effort:** 1 week **Owner:** \[TBD\] **Status:** Not Started

**Description:** Create a user-friendly CLI tool using Click/Typer for common operations. This is the primary interface for self-hosters.

**User Story:**

As a developer, I want to manage DocVector from the command line so that I can easily index docs, search, and run the MCP server without writing code.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | CLI-1 | `docvector init` \- Initialize local configuration | Must | | CLI-2 | `docvector index <url>` \- Crawl and index a documentation site | Must | | CLI-3 | `docvector search <query>` \- Search indexed documentation | Must | | CLI-4 | `docvector serve` \- Start MCP server (stdio/http modes) | Must | | CLI-5 | `docvector sources list/add/remove` \- Manage sources | Must | | CLI-6 | `docvector stats` \- Show indexing statistics | Should | | CLI-7 | `docvector export/import` \- Backup/restore data | Could |

**Technical Specifications:**

Location: src/docvector/cli.py

Dependencies: typer, rich (for formatting)

Config file: \~/.docvector/config.yaml or ./docvector.yaml

**Success Criteria:**

- [ ] All Must requirements implemented and tested  
- [ ] `pip install docvector && docvector --help` works  
- [ ] CLI documented in README with examples  
- [ ] Integration tests for all commands  
- [ ] \<100ms startup time for help/simple commands

**Acceptance Criteria:**

\# User can index React docs in under 5 minutes

$ docvector init

$ docvector index https://react.dev/reference \--max-pages 100

$ docvector search "how to use hooks"

\# Returns relevant results with sources

---

### OSS-1.2: Claude Desktop Integration Guide

**Priority:** P0 \- Critical **Effort:** 3 days **Owner:** \[TBD\] **Status:** Not Started

**Description:** Create comprehensive guide and example configurations for integrating DocVector MCP server with Claude Desktop and other MCP hosts.

**User Story:**

As a Claude Desktop user, I want to connect DocVector to my Claude so that I can search my indexed documentation directly from conversations.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | CD-1 | Claude Desktop config example (claude\_desktop\_config.json) | Must | | CD-2 | Step-by-step setup tutorial | Must | | CD-3 | Troubleshooting guide for common issues | Must | | CD-4 | Video walkthrough (or GIF demo) | Should | | CD-5 | VS Code / Cursor integration examples | Should | | CD-6 | Example conversation screenshots | Should |

**Deliverables:**

examples/

├── claude\_desktop\_config.json

├── vscode\_mcp\_config.json

├── cursor\_config.json

└── README.md (setup guide)

docs/

├── CLAUDE\_DESKTOP\_SETUP.md

└── TROUBLESHOOTING.md

**Success Criteria:**

- [ ] New user can connect Claude Desktop to DocVector in \<10 minutes  
- [ ] All 3 MCP tools work (search-docs, get-library-docs, resolve-library-id)  
- [ ] Guide tested on macOS, Windows, Linux  
- [ ] Zero support issues from unclear documentation

**Acceptance Criteria:**

- User follows guide, types "search React hooks" in Claude, gets documentation results  
- No terminal/code knowledge required beyond copy-paste

---

### OSS-1.3: Docker Compose Improvements

**Priority:** P1 \- High **Effort:** 3 days **Owner:** \[TBD\] **Status:** Partial

**Description:** Improve Docker setup for production readiness and easier onboarding.

**Current State:**

- Basic docker-compose.yml exists with Redis \+ Qdrant  
- Missing health checks, resource limits, persistence docs

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | DC-1 | Add health checks for all services | Must | | DC-2 | Document volume persistence for data durability | Must | | DC-3 | Create docker-compose.prod.yml with resource limits | Must | | DC-4 | Add .env.example with all configuration options | Must | | DC-5 | One-command startup: `docker compose up` just works | Must | | DC-6 | GPU support for local embeddings (optional) | Could |

**Success Criteria:**

- [ ] `docker compose up` starts all services with no errors  
- [ ] Data persists across container restarts  
- [ ] Health endpoint returns healthy within 30 seconds  
- [ ] Memory usage documented (minimum 2GB RAM)  
- [ ] Works on Docker Desktop (Mac/Windows) and Linux

**Acceptance Criteria:**

$ git clone https://github.com/docvector-hub/docvector

$ cd docvector

$ docker compose up \-d

$ curl http://localhost:8000/health

\# Returns: {"status": "healthy", "services": {...}}

---

### OSS-1.4: README and Documentation Refresh

**Priority:** P1 \- High **Effort:** 1 week **Owner:** \[TBD\] **Status:** Partial

**Description:** Update README and documentation for OSS launch with clear value proposition and quick start.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | DOC-1 | Hero section with clear value prop and demo GIF | Must | | DOC-2 | 5-minute quickstart (Docker path) | Must | | DOC-3 | 5-minute quickstart (pip install path) | Must | | DOC-4 | Architecture diagram (visual, not ASCII) | Must | | DOC-5 | Full API reference | Must | | DOC-6 | MCP tools reference with examples | Must | | DOC-7 | Configuration reference (all env vars) | Must | | DOC-8 | Contributing guide | Should | | DOC-9 | Changelog | Should |

**Success Criteria:**

- [ ] README answers "what is this" in first 10 seconds  
- [ ] New developer can run first search in \<5 minutes  
- [ ] All configuration options documented  
- [ ] No broken links or outdated information

---

### OSS-1.5: Example Integrations

**Priority:** P1 \- High **Effort:** 1 week **Owner:** \[TBD\] **Status:** Not Started

**Description:** Create example integrations showing DocVector usage with popular frameworks.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | EX-1 | LangChain integration example | Must | | EX-2 | LlamaIndex integration example | Must | | EX-3 | Python SDK usage example | Must | | EX-4 | Next.js search UI example | Should | | EX-5 | Slack bot example | Could | | EX-6 | Discord bot example | Could |

**Deliverables:**

examples/

├── langchain\_retriever.py

├── llamaindex\_reader.py

├── python\_client.py

├── nextjs-search-ui/

│   ├── package.json

│   └── src/

└── README.md

**Success Criteria:**

- [ ] Each example runs with minimal setup  
- [ ] Examples use real DocVector API (not mocked)  
- [ ] Code is well-commented and follows best practices  
- [ ] README explains each example's use case

---

## Phase 2: Community Growth (Weeks 5-8)

### OSS-2.1: Plugin System Architecture

**Priority:** P2 \- Medium **Effort:** 2 weeks **Owner:** \[TBD\] **Status:** Not Started

**Description:** Design and implement extensibility system for custom sources, parsers, and embedders.

**User Story:**

As a developer, I want to add custom data sources (Jira, Confluence, Notion) so that I can index all my team's documentation in one place.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | PL-1 | Plugin interface specification | Must | | PL-2 | Source plugin type (custom crawlers) | Must | | PL-3 | Parser plugin type (custom formats) | Must | | PL-4 | Embedder plugin type (custom models) | Should | | PL-5 | Plugin discovery mechanism | Should | | PL-6 | Example plugin template | Must |

**Technical Design:**

\# Plugin interface

class SourcePlugin(Protocol):

    name: str

    version: str

    async def fetch(self, config: dict) \-\> AsyncIterator\[Document\]:

        ...

    def get\_config\_schema(self) \-\> dict:

        ...

**Success Criteria:**

- [ ] Plugin architecture documented  
- [ ] At least one example plugin working  
- [ ] Plugins can be installed via pip  
- [ ] No core code changes needed for new plugins

---

### OSS-2.2: Search Quality Improvements

**Priority:** P2 \- Medium **Effort:** 2 weeks **Owner:** \[TBD\] **Status:** Not Started

**Description:** Improve search relevance through better ranking, filtering, and result presentation.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | SQ-1 | Recency boosting (newer docs rank higher) | Should | | SQ-2 | Source quality weighting | Should | | SQ-3 | Cross-source deduplication | Should | | SQ-4 | Query expansion (synonyms) | Could | | SQ-5 | Faceted search (filter by source, date, type) | Should | | SQ-6 | Search result highlighting | Should |

**Success Criteria:**

- [ ] Search relevance improves (measure via test queries)  
- [ ] Users can filter results by source  
- [ ] Duplicate content is deduplicated  
- [ ] Query response time \<200ms (p95)

---

### OSS-2.3: Incremental Indexing

**Priority:** P2 \- Medium **Effort:** 1 week **Owner:** \[TBD\] **Status:** Not Started

**Description:** Support incremental updates instead of full re-crawl for faster syncs.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | II-1 | Track document content hashes | Must | | II-2 | Only re-embed changed documents | Must | | II-3 | Delete removed documents from index | Must | | II-4 | Resume interrupted crawls | Should | | II-5 | Show sync status/progress | Should |

**Success Criteria:**

- [ ] Incremental sync 10x faster than full re-crawl  
- [ ] No stale documents in index after source changes  
- [ ] Progress shown during long syncs

---

### OSS-2.4: Test Coverage & CI/CD

**Priority:** P2 \- Medium **Effort:** 1 week **Owner:** \[TBD\] **Status:** Partial

**Description:** Improve test coverage and CI/CD pipeline for reliability.

**Current State:**

- pytest configured with 60% coverage  
- Pre-commit hooks exist  
- No automated release process

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | CI-1 | Increase test coverage to 80% | Must | | CI-2 | GitHub Actions CI pipeline | Must | | CI-3 | Automated PyPI release on tag | Must | | CI-4 | Docker image build and push | Must | | CI-5 | Integration test suite | Should | | CI-6 | Performance regression tests | Could |

**Success Criteria:**

- [ ] All PRs require passing tests  
- [ ] Coverage report in PR comments  
- [ ] Releases are automated (tag → PyPI \+ Docker Hub)  
- [ ] No manual steps in release process

---

## Phase 3: Ecosystem (Weeks 9-12)

### OSS-3.1: Python SDK

**Priority:** P3 \- Low **Effort:** 1 week **Owner:** \[TBD\] **Status:** Not Started

**Description:** Create typed Python SDK for programmatic DocVector usage.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | SDK-1 | Typed client with Pydantic models | Must | | SDK-2 | Async and sync interfaces | Must | | SDK-3 | Published to PyPI as `docvector-client` | Must | | SDK-4 | Complete API coverage | Must | | SDK-5 | Retry logic and error handling | Should |

**Example Usage:**

from docvector import DocVectorClient

client \= DocVectorClient("http://localhost:8000")

results \= await client.search("how to use hooks", limit=5)

for result in results:

    print(f"{result.title}: {result.content\[:100\]}")

**Success Criteria:**

- [ ] SDK published to PyPI  
- [ ] 100% API coverage  
- [ ] Full type hints for IDE support  
- [ ] Examples in documentation

---

### OSS-3.2: JavaScript/TypeScript SDK

**Priority:** P3 \- Low **Effort:** 1 week **Owner:** \[TBD\] **Status:** Not Started

**Description:** Create typed TypeScript SDK for frontend and Node.js usage.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | JS-1 | TypeScript definitions | Must | | JS-2 | Works in browser and Node.js | Must | | JS-3 | Published to npm as `@docvector/client` | Must | | JS-4 | Complete API coverage | Must |

**Success Criteria:**

- [ ] SDK published to npm  
- [ ] Works in Next.js/React apps  
- [ ] TypeScript types are accurate  
- [ ] Bundle size \<50KB

---

### OSS-3.3: Helm Chart for Kubernetes

**Priority:** P3 \- Low **Effort:** 1 week **Owner:** \[TBD\] **Status:** Not Started

**Description:** Create Helm chart for Kubernetes deployment.

**Requirements:** | ID | Requirement | Priority | |----|-------------|----------| | K8S-1 | Helm chart with configurable values | Must | | K8S-2 | Horizontal pod autoscaling | Should | | K8S-3 | Ingress configuration | Must | | K8S-4 | Persistent volume claims | Must | | K8S-5 | Published to Artifact Hub | Should |

**Success Criteria:**

- [ ] `helm install docvector ./charts/docvector` works  
- [ ] All configuration via values.yaml  
- [ ] Production-ready defaults  
- [ ] Resource requests/limits defined

---

## Success Metrics (OSS)

### Adoption Metrics

| Metric | Target (3 months) | Target (6 months) |
| :---- | :---- | :---- |
| GitHub Stars | 500 | 2,000 |
| PyPI Downloads/month | 1,000 | 5,000 |
| Docker Pulls/month | 500 | 2,000 |
| Contributors | 10 | 25 |

### Quality Metrics

| Metric | Target |
| :---- | :---- |
| Test Coverage | \>80% |
| Open Issues (P0/P1) | \<5 |
| Time to First Response | \<24 hours |
| Documentation Coverage | 100% of public APIs |

### Performance Metrics

| Metric | Target |
| :---- | :---- |
| Search Latency (p95) | \<200ms |
| Indexing Speed | \>100 pages/minute |
| Memory Usage (idle) | \<512MB |
| Cold Start Time | \<5 seconds |

---

## Appendix: File Locations

src/docvector/

├── cli.py              \# OSS-1.1: CLI tool (NEW)

├── mcp/

│   └── server.py       \# MCP server (EXISTS \- enhance)

├── api/

│   └── main.py         \# REST API (EXISTS)

├── services/

│   ├── search\_service.py

│   └── ingestion\_service.py

└── plugins/            \# OSS-2.1: Plugin system (NEW)

    ├── \_\_init\_\_.py

    ├── base.py

    └── sources/

examples/               \# OSS-1.5: Examples (NEW/ENHANCE)

├── claude\_desktop\_config.json

├── langchain\_retriever.py

├── llamaindex\_reader.py

└── nextjs-search-ui/

charts/                 \# OSS-3.3: Helm (NEW)

└── docvector/

    ├── Chart.yaml

    ├── values.yaml

    └── templates/

---

## Version History

| Version | Date | Changes |
| :---- | :---- | :---- |
| 1.0 | 2025-12-05 | Initial roadmap |

