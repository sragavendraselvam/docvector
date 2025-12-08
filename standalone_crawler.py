#!/usr/bin/env python3
"""
Standalone Web Crawler

A self-contained web crawler that can be shared and run independently.
Supports both lightweight aiohttp-based crawling and advanced Crawl4AI
(with JavaScript rendering).

Features:
- Sitemap discovery and parsing
- BFS/recursive crawling with depth limits
- Concurrent request handling
- robots.txt compliance (configurable)
- Multiple output formats (JSON, JSONL, CSV)
- Qdrant vector database storage with embeddings
- PostgreSQL storage with full-text search
- Job queue with status tracking and retries
- Worker mode for continuous crawling
- Progress reporting

Usage:
    # Basic crawl to file
    python standalone_crawler.py https://docs.example.com --output results.json
    python standalone_crawler.py https://docs.example.com --format jsonl --max-pages 50

    # Crawl and store in Qdrant with embeddings
    python standalone_crawler.py https://docs.example.com --qdrant --collection my_docs

    # Use Crawl4AI for JavaScript-heavy sites
    python standalone_crawler.py https://docs.example.com --engine crawl4ai

Requirements:
    pip install aiohttp beautifulsoup4 lxml

For Crawl4AI engine (optional, for JS rendering):
    pip install crawl4ai

For Qdrant storage (optional):
    pip install qdrant-client sentence-transformers python-dotenv

Environment Variables (or .env file):
    QDRANT_URL      - Qdrant server URL (e.g., https://xxx.cloud.qdrant.io:6333)
    QDRANT_API_KEY  - Qdrant API key for authentication
    DB_HOST         - PostgreSQL host
    DB_PORT         - PostgreSQL port (default: 5432)
    DB_NAME         - PostgreSQL database name
    DB_USER         - PostgreSQL username
    DB_PASSWORD     - PostgreSQL password
"""

import argparse
import asyncio
import csv
import json
import os
import random
import re
import signal
import sys
import traceback
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

# Core dependencies (always required)
import aiohttp
from bs4 import BeautifulSoup

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars only

# Qdrant Cloud configuration from environment variables
QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")

# PostgreSQL configuration from environment variables
DB_HOST = os.environ.get("DB_HOST", "")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")


@dataclass
class CrawledPage:
    """Represents a crawled page."""
    url: str
    title: Optional[str]
    content: str
    content_type: str
    status_code: int
    depth: int
    crawled_at: str
    word_count: int
    links_found: int
    metadata: Dict


class VersionExtractor:
    """
    Extracts version information from documentation pages.

    Detects versions from:
    - URL patterns (e.g., /v2/, /docs/3.0/, /stable/)
    - Page content (version badges, headers)
    - Meta tags
    - JSON-LD structured data
    """

    # Common version patterns in URLs
    URL_VERSION_PATTERNS = [
        r'/v(\d+(?:\.\d+)*(?:-\w+)?)',  # /v1, /v2.0, /v1.0-beta
        r'/(\d+\.\d+(?:\.\d+)?(?:-\w+)?)',  # /3.0, /2.1.0, /1.0.0-rc1
        r'/version[/-]?(\d+(?:\.\d+)*)',  # /version/2, /version-3.0
        r'/(stable|latest|current|main|master)',  # /stable, /latest
        r'/docs?/(\d+\.\d+)',  # /docs/3.0, /doc/2.1
        r'/en/(\d+\.\d+)',  # Django style /en/5.0/
    ]

    # Patterns to find version in page content
    CONTENT_VERSION_PATTERNS = [
        r'(?:version|release|v)[:\s]*(\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?)',
        r'(\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?)\s*(?:documentation|docs|release)',
        r'(?:^|\s)v(\d+\.\d+(?:\.\d+)?)',
        r'@(\d+\.\d+(?:\.\d+)?)',  # @1.0.0 in package names
        r'(?:React|Vue|Angular|Next\.?js|Svelte|Django|Flask|FastAPI|PyTorch|TensorFlow)\s+(\d+(?:\.\d+)*)',  # "React 18", "Django 5.0"
    ]

    @classmethod
    def extract_from_url(cls, url: str) -> Optional[str]:
        """Extract version from URL path."""
        for pattern in cls.URL_VERSION_PATTERNS:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                version = match.group(1)
                # Normalize special versions
                if version.lower() in ('stable', 'latest', 'current', 'main', 'master'):
                    return version.lower()
                return version
        return None

    @classmethod
    def extract_from_content(cls, content: str, title: str = "") -> Optional[str]:
        """Extract version from page content and title."""
        # Check title first (often most reliable)
        if title:
            for pattern in cls.CONTENT_VERSION_PATTERNS:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    return match.group(1)

        # Check first 2000 chars of content (version usually near top)
        content_snippet = content[:2000] if len(content) > 2000 else content

        for pattern in cls.CONTENT_VERSION_PATTERNS:
            match = re.search(pattern, content_snippet, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    @classmethod
    def extract_from_html(cls, html: str) -> Optional[str]:
        """Extract version from HTML meta tags or structured data."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Check meta tags
            version_meta = soup.find('meta', attrs={'name': re.compile(r'version', re.I)})
            if version_meta and version_meta.get('content'):
                return version_meta['content']

            # Check for version in og:title or similar
            og_title = soup.find('meta', attrs={'property': 'og:title'})
            if og_title and og_title.get('content'):
                for pattern in cls.CONTENT_VERSION_PATTERNS:
                    match = re.search(pattern, og_title['content'], re.IGNORECASE)
                    if match:
                        return match.group(1)

            # Check JSON-LD
            json_ld = soup.find('script', type='application/ld+json')
            if json_ld:
                try:
                    import json
                    data = json.loads(json_ld.string)
                    if isinstance(data, dict):
                        if 'version' in data:
                            return str(data['version'])
                        if 'softwareVersion' in data:
                            return str(data['softwareVersion'])
                except:
                    pass

            # Check common version badge/indicator classes
            version_elements = soup.find_all(class_=re.compile(r'version|release', re.I))
            for elem in version_elements[:3]:  # Check first 3 matches
                text = elem.get_text(strip=True)
                for pattern in cls.CONTENT_VERSION_PATTERNS:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return match.group(1)
                # Direct version number
                if re.match(r'^\d+\.\d+(?:\.\d+)?$', text):
                    return text

        except Exception:
            pass

        return None

    @classmethod
    def extract(cls, url: str, content: str = "", title: str = "", html: str = "") -> Dict[str, Any]:
        """
        Extract version using all available methods.

        Returns dict with:
        - version: The detected version string
        - version_source: Where the version was found (url, content, html, title)
        - is_latest: Whether this appears to be the latest/stable version
        """
        result = {
            'version': None,
            'version_source': None,
            'is_latest': False,
        }

        # Try URL first (most reliable for docs)
        version = cls.extract_from_url(url)
        if version:
            result['version'] = version
            result['version_source'] = 'url'
            result['is_latest'] = version.lower() in ('stable', 'latest', 'current', 'main', 'master')
            return result

        # Try HTML meta tags
        if html:
            version = cls.extract_from_html(html)
            if version:
                result['version'] = version
                result['version_source'] = 'html'
                return result

        # Try content/title
        version = cls.extract_from_content(content, title)
        if version:
            result['version'] = version
            result['version_source'] = 'content'
            return result

        return result


class StandaloneCrawler:
    """
    Lightweight web crawler using aiohttp and BeautifulSoup.

    Good for most documentation sites. Fast and memory-efficient.
    """

    def __init__(
        self,
        max_depth: int = 3,
        max_pages: int = 100,
        concurrent_requests: int = 5,
        respect_robots: bool = True,
        user_agent: str = "StandaloneCrawler/1.0",
        timeout: int = 30,
        allowed_domains: Optional[List[str]] = None,
        verbose: bool = False,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.concurrent_requests = concurrent_requests
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self.timeout = timeout
        self.allowed_domains = allowed_domains or []
        self.verbose = verbose

        self.visited_urls: Set[str] = set()
        self.session: Optional[aiohttp.ClientSession] = None
        self._robots_cache: Dict[str, RobotFileParser] = {}

    def log(self, message: str):
        """Print log message if verbose mode is on."""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr)

    async def crawl(self, start_url: str) -> List[CrawledPage]:
        """
        Crawl a website starting from the given URL.

        Args:
            start_url: The URL to start crawling from

        Returns:
            List of CrawledPage objects
        """
        self.log(f"Starting crawl of {start_url}")
        self.log(f"Max depth: {self.max_depth}, Max pages: {self.max_pages}")

        # Auto-detect allowed domain if not specified
        if not self.allowed_domains:
            parsed = urlparse(start_url)
            self.allowed_domains = [parsed.netloc]
            self.log(f"Auto-detected domain: {parsed.netloc}")

        await self._init_session()

        try:
            # Load robots.txt if respecting it
            if self.respect_robots:
                await self._load_robots_txt(start_url)

            # Try sitemap first
            sitemap_urls = await self._fetch_sitemap(start_url)

            if sitemap_urls:
                self.log(f"Found {len(sitemap_urls)} URLs in sitemap")
                urls_to_fetch = list(sitemap_urls)[:self.max_pages]
                pages = await self._fetch_urls_batch(urls_to_fetch)
            else:
                self.log("No sitemap found, using BFS crawling")
                pages = await self._crawl_bfs(start_url)

            self.log(f"Crawl completed. Fetched {len(pages)} pages.")
            return pages

        finally:
            await self._close_session()

    async def _init_session(self):
        """Initialize HTTP session."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": self.user_agent},
            )

    async def _close_session(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def _load_robots_txt(self, url: str):
        """Load and cache robots.txt for the domain."""
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        if base_url in self._robots_cache:
            return

        robots_url = f"{base_url}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, rp.read)
            self._robots_cache[base_url] = rp
            self.log(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            self.log(f"Could not load robots.txt: {e}")
            self._robots_cache[base_url] = rp

    def _can_fetch(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        if not self.respect_robots:
            return True

        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        rp = self._robots_cache.get(base_url)
        if not rp:
            return True

        return rp.can_fetch(self.user_agent, url)

    async def _fetch_sitemap(self, base_url: str) -> Set[str]:
        """Try to fetch and parse sitemap.xml."""
        parsed = urlparse(base_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"

        try:
            async with self.session.get(sitemap_url) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, "lxml-xml")

                    urls = set()
                    for loc in soup.find_all("loc"):
                        url = loc.text.strip()
                        if url and self._should_crawl(url):
                            urls.add(url)

                    return urls
        except Exception as e:
            self.log(f"Failed to fetch sitemap: {e}")

        return set()

    def _should_crawl(self, url: str) -> bool:
        """Check if URL should be crawled."""
        if not url:
            return False

        parsed = urlparse(url)

        # Skip non-http(s) URLs
        if parsed.scheme not in ("http", "https"):
            return False

        # Skip fragments
        if parsed.fragment:
            url = url.split("#")[0]

        # Skip common non-content extensions
        skip_extensions = {
            ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg",
            ".css", ".js", ".ico", ".woff", ".woff2", ".ttf",
            ".eot", ".zip", ".tar", ".gz", ".mp4", ".mp3",
        }
        if any(parsed.path.lower().endswith(ext) for ext in skip_extensions):
            return False

        # Check allowed domains
        if self.allowed_domains:
            if not any(parsed.netloc.endswith(domain) for domain in self.allowed_domains):
                return False

        # Check robots.txt
        if not self._can_fetch(url):
            return False

        return True

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and trailing slashes."""
        if not url:
            return ""

        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        if normalized.endswith("/") and parsed.path != "/":
            normalized = normalized[:-1]

        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"

        return normalized

    async def _fetch_urls_batch(self, urls: List[str]) -> List[CrawledPage]:
        """Fetch multiple URLs concurrently."""
        semaphore = asyncio.Semaphore(self.concurrent_requests)

        async def fetch_with_semaphore(url: str) -> Optional[CrawledPage]:
            async with semaphore:
                return await self._fetch_page(url, depth=0)

        tasks = [fetch_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks)

        return [page for page in results if page is not None]

    async def _crawl_bfs(self, start_url: str) -> List[CrawledPage]:
        """Crawl using breadth-first search."""
        pages: List[CrawledPage] = []
        queue: List[tuple[str, int]] = [(self._normalize_url(start_url), 0)]
        visited: Set[str] = set()

        semaphore = asyncio.Semaphore(self.concurrent_requests)

        while queue and len(pages) < self.max_pages:
            # Get batch of URLs at same depth level
            batch: List[tuple[str, int]] = []
            current_depth = queue[0][1] if queue else 0

            while queue and queue[0][1] == current_depth and len(batch) < self.concurrent_requests:
                url, depth = queue.pop(0)
                normalized = self._normalize_url(url)
                if normalized not in visited:
                    visited.add(normalized)
                    batch.append((normalized, depth))

            if not batch:
                continue

            self.log(f"Crawling batch at depth {current_depth}: {len(batch)} URLs")

            async def fetch_and_extract(url: str, depth: int):
                async with semaphore:
                    page = await self._fetch_page(url, depth)
                    links = []

                    if page and depth < self.max_depth:
                        # Extract links from the page
                        try:
                            soup = BeautifulSoup(page.content, "html.parser")
                            for link in soup.find_all("a", href=True):
                                href = link["href"]
                                absolute_url = urljoin(url, href)
                                normalized = self._normalize_url(absolute_url)
                                if normalized and self._should_crawl(normalized):
                                    if normalized not in visited:
                                        links.append(normalized)
                        except Exception:
                            pass

                    return page, links

            tasks = [fetch_and_extract(url, depth) for url, depth in batch]
            results = await asyncio.gather(*tasks)

            for result in results:
                if result[0]:  # page
                    pages.append(result[0])
                    print(f"\r[{len(pages)}/{self.max_pages}] Crawled: {result[0].url[:80]}...", end="", file=sys.stderr)

                    if len(pages) >= self.max_pages:
                        break

                # Add new links to queue
                for link in result[1]:
                    if link not in visited and len(queue) < self.max_pages * 2:
                        queue.append((link, current_depth + 1))

        print("", file=sys.stderr)  # New line after progress
        return pages

    async def _fetch_page(self, url: str, depth: int) -> Optional[CrawledPage]:
        """Fetch a single page and extract content."""
        try:
            async with self.session.get(url) as response:
                status_code = response.status
                content_type = response.headers.get("Content-Type", "")

                if status_code != 200:
                    return None

                if "text/html" not in content_type:
                    return None

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Extract title
                title = None
                if soup.title:
                    title = soup.title.string

                # Remove script and style elements
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                # Extract main content
                main_content = soup.find("main") or soup.find("article") or soup.find("body")
                text_content = main_content.get_text(separator="\n", strip=True) if main_content else ""

                # Count words and links
                word_count = len(text_content.split())
                links = soup.find_all("a", href=True)

                # Extract version information
                version_info = VersionExtractor.extract(
                    url=url,
                    content=text_content,
                    title=title or "",
                    html=html
                )

                return CrawledPage(
                    url=url,
                    title=title,
                    content=text_content,
                    content_type=content_type.split(";")[0].strip(),
                    status_code=status_code,
                    depth=depth,
                    crawled_at=datetime.utcnow().isoformat(),
                    word_count=word_count,
                    links_found=len(links),
                    metadata={
                        "html_length": len(html),
                        "version": version_info.get("version"),
                        "version_source": version_info.get("version_source"),
                        "is_latest": version_info.get("is_latest", False),
                    },
                )

        except Exception as e:
            self.log(f"Failed to fetch {url}: {e}")
            return None


class Crawl4AIWrapper:
    """
    Advanced crawler using Crawl4AI library.

    Features:
    - JavaScript rendering
    - Clean markdown output
    - AI-optimized content extraction

    Requires: pip install crawl4ai
    """

    def __init__(
        self,
        max_depth: int = 3,
        max_pages: int = 100,
        concurrent_requests: int = 5,
        respect_robots: bool = True,
        headless: bool = True,
        verbose: bool = False,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.concurrent_requests = concurrent_requests
        self.respect_robots = respect_robots
        self.headless = headless
        self.verbose = verbose

        self._crawler = None
        self._robots_cache: Dict[str, RobotFileParser] = {}

    def log(self, message: str):
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr)

    async def crawl(self, start_url: str) -> List[CrawledPage]:
        """Crawl using Crawl4AI."""
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        except ImportError:
            print("Error: crawl4ai is not installed.", file=sys.stderr)
            print("Install it with: pip install crawl4ai", file=sys.stderr)
            sys.exit(1)

        self.log(f"Starting Crawl4AI crawl of {start_url}")

        parsed = urlparse(start_url)
        allowed_domains = [parsed.netloc]

        browser_config = BrowserConfig(headless=self.headless, verbose=False)

        async with AsyncWebCrawler(config=browser_config) as crawler:
            pages: List[CrawledPage] = []
            visited: Set[str] = set()
            queue: List[tuple[str, int]] = [(start_url, 0)]

            while queue and len(pages) < self.max_pages:
                url, depth = queue.pop(0)
                normalized = self._normalize_url(url)

                if normalized in visited:
                    continue
                visited.add(normalized)

                self.log(f"Fetching: {url}")

                try:
                    run_config = CrawlerRunConfig(
                        cache_mode=CacheMode.BYPASS,
                        process_iframes=False,
                        remove_overlay_elements=True,
                    )

                    result = await crawler.arun(url=url, config=run_config)

                    if not result.success:
                        continue

                    content = result.markdown.raw_markdown if result.markdown else ""
                    title = result.metadata.get("title") if result.metadata else None
                    html = result.html if hasattr(result, 'html') else ""

                    # Extract version information
                    version_info = VersionExtractor.extract(
                        url=url,
                        content=content,
                        title=title or "",
                        html=html
                    )

                    page = CrawledPage(
                        url=url,
                        title=title,
                        content=content,
                        content_type="text/markdown",
                        status_code=result.status_code,
                        depth=depth,
                        crawled_at=datetime.utcnow().isoformat(),
                        word_count=len(content.split()),
                        links_found=len(result.links.get("internal", [])) if result.links else 0,
                        metadata={
                            "crawl4ai": True,
                            "version": version_info.get("version"),
                            "version_source": version_info.get("version_source"),
                            "is_latest": version_info.get("is_latest", False),
                        },
                    )

                    pages.append(page)
                    print(f"\r[{len(pages)}/{self.max_pages}] Crawled: {url[:80]}...", end="", file=sys.stderr)

                    # Extract links for next level
                    if depth < self.max_depth and result.links:
                        internal_links = result.links.get("internal", [])
                        for link_info in internal_links:
                            link_url = link_info.get("href", "") if isinstance(link_info, dict) else str(link_info)
                            normalized_link = self._normalize_url(link_url)
                            if normalized_link and normalized_link not in visited:
                                link_parsed = urlparse(normalized_link)
                                if any(link_parsed.netloc.endswith(d) for d in allowed_domains):
                                    queue.append((normalized_link, depth + 1))

                except Exception as e:
                    self.log(f"Failed to fetch {url}: {e}")

            print("", file=sys.stderr)
            self.log(f"Crawl completed. Fetched {len(pages)} pages.")
            return pages

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if normalized.endswith("/") and parsed.path != "/":
            normalized = normalized[:-1]
        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"
        return normalized


class QdrantStorage:
    """
    Store crawled pages in Qdrant vector database with embeddings.

    Features:
    - Single unified collection for all libraries (filterable by library name)
    - Automatic text chunking for long documents
    - Embedding generation using sentence-transformers
    - Qdrant Cloud support with API key authentication
    - Metadata storage for filtering

    Requires: pip install qdrant-client sentence-transformers
    """

    # Single unified collection name for all documentation
    UNIFIED_COLLECTION = "docs"

    def __init__(
        self,
        library_name: str,
        qdrant_url: str = QDRANT_URL,
        qdrant_api_key: str = QDRANT_API_KEY,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        verbose: bool = False,
        collection_name: str = None,  # Deprecated, kept for backward compatibility
    ):
        self.library_name = library_name
        self.collection_name = self.UNIFIED_COLLECTION  # Always use unified collection
        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        self.embedding_model_name = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose

        self._client = None
        self._embedder = None
        self._embedding_dim = None

    def log(self, message: str):
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Qdrant] {message}", file=sys.stderr)

    def _init_client(self):
        """Initialize Qdrant client."""
        if self._client is not None:
            return

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models
        except ImportError:
            print("Error: qdrant-client is not installed.", file=sys.stderr)
            print("Install it with: pip install qdrant-client", file=sys.stderr)
            sys.exit(1)

        # Validate credentials
        if not self.qdrant_url:
            print("Error: QDRANT_URL is not set.", file=sys.stderr)
            print("Set it in .env file or environment variable, or use --qdrant-url", file=sys.stderr)
            sys.exit(1)

        if not self.qdrant_api_key:
            print("Error: QDRANT_API_KEY is not set.", file=sys.stderr)
            print("Set it in .env file or environment variable, or use --qdrant-key", file=sys.stderr)
            sys.exit(1)

        self.log(f"Connecting to Qdrant at {self.qdrant_url}")
        self._client = QdrantClient(
            url=self.qdrant_url,
            api_key=self.qdrant_api_key,
        )

        # Verify connection
        try:
            self._client.get_collections()
            self.log("Connected to Qdrant successfully")
        except Exception as e:
            print(f"Error: Failed to connect to Qdrant: {e}", file=sys.stderr)
            sys.exit(1)

    def _init_embedder(self):
        """Initialize sentence-transformers embedder."""
        if self._embedder is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("Error: sentence-transformers is not installed.", file=sys.stderr)
            print("Install it with: pip install sentence-transformers", file=sys.stderr)
            sys.exit(1)

        self.log(f"Loading embedding model: {self.embedding_model_name}")
        self._embedder = SentenceTransformer(self.embedding_model_name)
        self._embedding_dim = self._embedder.get_sentence_embedding_dimension()
        self.log(f"Embedding dimension: {self._embedding_dim}")

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        from qdrant_client.http import models

        collections = self._client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            self.log(f"Creating collection: {self.collection_name}")
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self._embedding_dim,
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            self.log(f"Collection exists: {self.collection_name}")

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []

        words = text.split()
        if len(words) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(words):
            end = start + self.chunk_size
            chunk_words = words[start:end]
            chunks.append(" ".join(chunk_words))
            start = end - self.chunk_overlap

        return chunks

    def store(self, pages: List[CrawledPage]) -> int:
        """
        Store crawled pages in Qdrant with embeddings.

        Args:
            pages: List of crawled pages

        Returns:
            Number of vectors stored
        """
        from qdrant_client.http import models
        import uuid

        self._init_client()
        self._init_embedder()
        self._ensure_collection()

        total_stored = 0
        batch_size = 100

        for page in pages:
            # Chunk the content
            chunks = self._chunk_text(page.content)
            if not chunks:
                continue

            self.log(f"Processing {page.url}: {len(chunks)} chunks")

            # Generate embeddings
            embeddings = self._embedder.encode(chunks, show_progress_bar=False)

            # Prepare points
            points = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                point_id = str(uuid.uuid4())
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=embedding.tolist(),
                        payload={
                            "library": self.library_name,
                            "url": page.url,
                            "title": page.title or "",
                            "chunk_index": i,
                            "chunk_count": len(chunks),
                            "content": chunk,
                            "word_count": len(chunk.split()),
                            "crawled_at": page.crawled_at,
                            "depth": page.depth,
                            "version": page.metadata.get("version"),
                        },
                    )
                )

            # Upload in batches
            for batch_start in range(0, len(points), batch_size):
                batch = points[batch_start:batch_start + batch_size]
                self._client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                )
                total_stored += len(batch)

            print(f"\r[Qdrant] Stored {total_stored} vectors...", end="", file=sys.stderr)

        print("", file=sys.stderr)
        self.log(f"Total vectors stored: {total_stored}")
        return total_stored

    def search(self, query: str, limit: int = 5, library: str = None) -> List[Dict]:
        """
        Search for similar content.

        Args:
            query: Search query
            limit: Number of results
            library: Optional library name to filter results (e.g., "langchain", "react")

        Returns:
            List of matching chunks with scores
        """
        from qdrant_client.http import models

        self._init_client()
        self._init_embedder()

        query_embedding = self._embedder.encode(query).tolist()

        # Build filter if library specified
        query_filter = None
        if library:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="library",
                        match=models.MatchValue(value=library),
                    )
                ]
            )

        # Use query_points (newer API) instead of deprecated search
        try:
            results = self._client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                query_filter=query_filter,
                limit=limit,
            ).points
        except (AttributeError, TypeError):
            # Fallback for older qdrant-client versions
            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=limit,
            )

        return [
            {
                "score": r.score,
                "library": r.payload.get("library"),
                "url": r.payload.get("url"),
                "title": r.payload.get("title"),
                "content": r.payload.get("content"),
                "chunk_index": r.payload.get("chunk_index"),
                "version": r.payload.get("version"),
            }
            for r in results
        ]

    def get_stats(self) -> Dict:
        """Get collection statistics including per-library breakdown."""
        self._init_client()

        try:
            info = self._client.get_collection(self.collection_name)
            stats = {
                "collection": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
            }

            # Get library breakdown by scrolling through points
            # This is a simplified approach - for large collections, use aggregations
            try:
                from collections import Counter
                library_counts = Counter()
                offset = None
                while True:
                    points, offset = self._client.scroll(
                        collection_name=self.collection_name,
                        limit=1000,
                        offset=offset,
                        with_payload=["library"],
                        with_vectors=False,
                    )
                    for p in points:
                        lib = p.payload.get("library", "unknown")
                        library_counts[lib] += 1
                    if offset is None:
                        break
                stats["libraries"] = dict(library_counts)
            except Exception:
                pass

            return stats
        except Exception:
            return {"collection": self.collection_name, "exists": False}


class PostgresStorage:
    """
    Store crawled pages in PostgreSQL database.

    Features:
    - Automatic table creation
    - Async operations with asyncpg
    - Full-text search support
    - Metadata storage as JSONB

    Requires: pip install asyncpg
    """

    # SQL for creating tables
    CREATE_TABLES_SQL = """
    -- Crawl sources (websites)
    CREATE TABLE IF NOT EXISTS crawl_sources (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE,
        start_url TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_crawled_at TIMESTAMP,
        config JSONB DEFAULT '{}'
    );

    -- Crawled pages
    CREATE TABLE IF NOT EXISTS crawled_pages (
        id SERIAL PRIMARY KEY,
        source_id INTEGER REFERENCES crawl_sources(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        title TEXT,
        content TEXT,
        content_type VARCHAR(100),
        status_code INTEGER,
        depth INTEGER,
        word_count INTEGER,
        links_found INTEGER,
        content_hash VARCHAR(64),
        crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        metadata JSONB DEFAULT '{}',
        UNIQUE(source_id, url)
    );

    -- Text chunks for embeddings
    CREATE TABLE IF NOT EXISTS page_chunks (
        id SERIAL PRIMARY KEY,
        page_id INTEGER REFERENCES crawled_pages(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        word_count INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(page_id, chunk_index)
    );

    -- Indexes for better query performance
    CREATE INDEX IF NOT EXISTS idx_crawled_pages_source ON crawled_pages(source_id);
    CREATE INDEX IF NOT EXISTS idx_crawled_pages_url ON crawled_pages(url);
    CREATE INDEX IF NOT EXISTS idx_page_chunks_page ON page_chunks(page_id);
    """

    def __init__(
        self,
        source_name: str,
        host: str = DB_HOST,
        port: str = DB_PORT,
        database: str = DB_NAME,
        user: str = DB_USER,
        password: str = DB_PASSWORD,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        verbose: bool = False,
    ):
        self.source_name = source_name
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose

        self._pool = None
        self._source_id = None

    def log(self, message: str):
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [PostgreSQL] {message}", file=sys.stderr)

    async def _init_pool(self):
        """Initialize connection pool."""
        if self._pool is not None:
            return

        try:
            import asyncpg
        except ImportError:
            print("Error: asyncpg is not installed.", file=sys.stderr)
            print("Install it with: pip install asyncpg", file=sys.stderr)
            sys.exit(1)

        # Validate credentials
        if not self.host:
            print("Error: DB_HOST is not set.", file=sys.stderr)
            print("Set it in .env file or environment variable, or use --db-host", file=sys.stderr)
            sys.exit(1)

        if not self.password:
            print("Error: DB_PASSWORD is not set.", file=sys.stderr)
            print("Set it in .env file or environment variable, or use --db-password", file=sys.stderr)
            sys.exit(1)

        self.log(f"Connecting to PostgreSQL at {self.host}:{self.port}/{self.database}")

        try:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=int(self.port),
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=1,
                max_size=5,
            )
            self.log("Connected to PostgreSQL successfully")
        except Exception as e:
            print(f"Error: Failed to connect to PostgreSQL: {e}", file=sys.stderr)
            sys.exit(1)

    async def _ensure_tables(self):
        """Create tables if they don't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLES_SQL)
            self.log("Database tables ready")

    async def _get_or_create_source(self, start_url: str) -> int:
        """Get or create source entry."""
        async with self._pool.acquire() as conn:
            # Try to get existing source
            row = await conn.fetchrow(
                "SELECT id FROM crawl_sources WHERE name = $1",
                self.source_name
            )

            if row:
                # Update last crawled time
                await conn.execute(
                    "UPDATE crawl_sources SET last_crawled_at = CURRENT_TIMESTAMP, start_url = $2 WHERE id = $1",
                    row['id'], start_url
                )
                return row['id']

            # Create new source
            row = await conn.fetchrow(
                """INSERT INTO crawl_sources (name, start_url, last_crawled_at)
                   VALUES ($1, $2, CURRENT_TIMESTAMP)
                   RETURNING id""",
                self.source_name, start_url
            )
            return row['id']

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []

        words = text.split()
        if len(words) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(words):
            end = start + self.chunk_size
            chunk_words = words[start:end]
            chunks.append(" ".join(chunk_words))
            start = end - self.chunk_overlap

        return chunks

    def _hash_content(self, content: str) -> str:
        """Generate hash of content for deduplication."""
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()

    async def store(self, pages: List[CrawledPage], start_url: str) -> Dict:
        """
        Store crawled pages in PostgreSQL.

        Args:
            pages: List of crawled pages
            start_url: The starting URL of the crawl

        Returns:
            Statistics about stored data
        """
        await self._init_pool()
        await self._ensure_tables()

        source_id = await self._get_or_create_source(start_url)
        self._source_id = source_id

        pages_stored = 0
        pages_updated = 0
        chunks_stored = 0

        async with self._pool.acquire() as conn:
            for page in pages:
                content_hash = self._hash_content(page.content)

                # Check if page exists
                existing = await conn.fetchrow(
                    "SELECT id, content_hash FROM crawled_pages WHERE source_id = $1 AND url = $2",
                    source_id, page.url
                )

                if existing:
                    if existing['content_hash'] == content_hash:
                        # Content unchanged, skip
                        continue

                    # Update existing page
                    page_id = existing['id']
                    # Parse crawled_at string to datetime
                    crawled_at = datetime.fromisoformat(page.crawled_at) if isinstance(page.crawled_at, str) else page.crawled_at
                    await conn.execute(
                        """UPDATE crawled_pages SET
                           title = $1, content = $2, content_type = $3, status_code = $4,
                           depth = $5, word_count = $6, links_found = $7, content_hash = $8,
                           crawled_at = $9, metadata = $10
                           WHERE id = $11""",
                        page.title, page.content, page.content_type, page.status_code,
                        page.depth, page.word_count, page.links_found, content_hash,
                        crawled_at, json.dumps(page.metadata), page_id
                    )

                    # Delete old chunks
                    await conn.execute("DELETE FROM page_chunks WHERE page_id = $1", page_id)
                    pages_updated += 1
                else:
                    # Insert new page
                    # Parse crawled_at string to datetime
                    crawled_at = datetime.fromisoformat(page.crawled_at) if isinstance(page.crawled_at, str) else page.crawled_at
                    row = await conn.fetchrow(
                        """INSERT INTO crawled_pages
                           (source_id, url, title, content, content_type, status_code,
                            depth, word_count, links_found, content_hash, crawled_at, metadata)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                           RETURNING id""",
                        source_id, page.url, page.title, page.content, page.content_type,
                        page.status_code, page.depth, page.word_count, page.links_found,
                        content_hash, crawled_at, json.dumps(page.metadata)
                    )
                    page_id = row['id']
                    pages_stored += 1

                # Store chunks
                chunks = self._chunk_text(page.content)
                for i, chunk in enumerate(chunks):
                    await conn.execute(
                        """INSERT INTO page_chunks (page_id, chunk_index, content, word_count)
                           VALUES ($1, $2, $3, $4)""",
                        page_id, i, chunk, len(chunk.split())
                    )
                    chunks_stored += 1

                print(f"\r[PostgreSQL] Stored {pages_stored + pages_updated} pages, {chunks_stored} chunks...", end="", file=sys.stderr)

        print("", file=sys.stderr)

        stats = {
            "source_id": source_id,
            "source_name": self.source_name,
            "pages_stored": pages_stored,
            "pages_updated": pages_updated,
            "chunks_stored": chunks_stored,
        }
        self.log(f"Storage complete: {stats}")
        return stats

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search stored pages using full-text search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching pages
        """
        await self._init_pool()

        async with self._pool.acquire() as conn:
            # Use PostgreSQL full-text search
            results = await conn.fetch(
                """SELECT p.url, p.title, p.content, p.word_count, p.crawled_at,
                          ts_rank(to_tsvector('english', p.content), plainto_tsquery('english', $1)) as rank
                   FROM crawled_pages p
                   JOIN crawl_sources s ON p.source_id = s.id
                   WHERE s.name = $2
                     AND to_tsvector('english', p.content) @@ plainto_tsquery('english', $1)
                   ORDER BY rank DESC
                   LIMIT $3""",
                query, self.source_name, limit
            )

            return [
                {
                    "url": r['url'],
                    "title": r['title'],
                    "content": r['content'][:500] + "..." if len(r['content']) > 500 else r['content'],
                    "word_count": r['word_count'],
                    "crawled_at": r['crawled_at'].isoformat() if r['crawled_at'] else None,
                    "rank": float(r['rank']),
                }
                for r in results
            ]

    async def get_stats(self) -> Dict:
        """Get storage statistics."""
        await self._init_pool()

        async with self._pool.acquire() as conn:
            # Get source info
            source = await conn.fetchrow(
                "SELECT id, name, start_url, created_at, last_crawled_at FROM crawl_sources WHERE name = $1",
                self.source_name
            )

            if not source:
                return {"source": self.source_name, "exists": False}

            # Get counts
            page_count = await conn.fetchval(
                "SELECT COUNT(*) FROM crawled_pages WHERE source_id = $1",
                source['id']
            )

            chunk_count = await conn.fetchval(
                """SELECT COUNT(*) FROM page_chunks pc
                   JOIN crawled_pages p ON pc.page_id = p.id
                   WHERE p.source_id = $1""",
                source['id']
            )

            total_words = await conn.fetchval(
                "SELECT COALESCE(SUM(word_count), 0) FROM crawled_pages WHERE source_id = $1",
                source['id']
            )

            return {
                "source": self.source_name,
                "exists": True,
                "start_url": source['start_url'],
                "created_at": source['created_at'].isoformat() if source['created_at'] else None,
                "last_crawled_at": source['last_crawled_at'].isoformat() if source['last_crawled_at'] else None,
                "pages": page_count,
                "chunks": chunk_count,
                "total_words": total_words,
            }

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None


class JobStatus(Enum):
    """Status of a crawl job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class CrawlJob:
    """Represents a crawl job."""
    id: int
    name: str
    url: str
    status: str
    priority: int
    max_pages: int
    max_depth: int
    retry_count: int
    max_retries: int
    worker_id: Optional[str]
    locked_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    crawl_config: Dict
    crawl_stats: Dict
    created_at: datetime
    updated_at: datetime


class CrawlJobManager:
    """
    Manages crawl jobs with status tracking, locking, and retries.

    Features:
    - Job queue with priority and random selection
    - Distributed locking to prevent duplicate processing
    - Automatic retries with exponential backoff
    - Crawl statistics tracking
    - Worker mode for continuous processing

    Requires: pip install asyncpg
    """

    # SQL for creating job tracking tables
    CREATE_TABLES_SQL = """
    -- Crawl jobs table
    CREATE TABLE IF NOT EXISTS crawl_jobs (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE,
        url TEXT NOT NULL,
        status VARCHAR(50) DEFAULT 'pending',
        priority INTEGER DEFAULT 0,
        max_pages INTEGER DEFAULT 100,
        max_depth INTEGER DEFAULT 3,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        worker_id VARCHAR(100),
        locked_at TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        next_retry_at TIMESTAMP,
        error_message TEXT,
        crawl_config JSONB DEFAULT '{}',
        crawl_stats JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Indexes for efficient querying
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_priority ON crawl_jobs(priority DESC);
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_next_retry ON crawl_jobs(next_retry_at);
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_worker ON crawl_jobs(worker_id);
    """

    # Lock timeout in minutes - jobs locked longer than this are considered stale
    LOCK_TIMEOUT_MINUTES = 30

    # Retry delays (exponential backoff): 1min, 5min, 15min, 30min, 1hr
    RETRY_DELAYS = [60, 300, 900, 1800, 3600]

    def __init__(
        self,
        host: str = DB_HOST,
        port: str = DB_PORT,
        database: str = DB_NAME,
        user: str = DB_USER,
        password: str = DB_PASSWORD,
        worker_id: Optional[str] = None,
        verbose: bool = False,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.verbose = verbose

        self._pool = None
        self._shutdown = False

    def log(self, message: str):
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [JobManager] {message}", file=sys.stderr)

    async def _init_pool(self):
        """Initialize connection pool."""
        if self._pool is not None:
            return

        try:
            import asyncpg
        except ImportError:
            print("Error: asyncpg is not installed.", file=sys.stderr)
            print("Install it with: pip install asyncpg", file=sys.stderr)
            sys.exit(1)

        if not self.host:
            print("Error: DB_HOST is not set.", file=sys.stderr)
            sys.exit(1)

        self.log(f"Connecting to PostgreSQL at {self.host}:{self.port}/{self.database}")

        try:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=int(self.port),
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=1,
                max_size=5,
            )
            self.log(f"Connected as worker: {self.worker_id}")
        except Exception as e:
            print(f"Error: Failed to connect to PostgreSQL: {e}", file=sys.stderr)
            sys.exit(1)

    async def _ensure_tables(self):
        """Create tables if they don't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLES_SQL)
            self.log("Job tables ready")

    async def add_job(
        self,
        name: str,
        url: str,
        max_pages: int = 100,
        max_depth: int = 3,
        priority: int = 0,
        max_retries: int = 3,
        crawl_config: Optional[Dict] = None,
    ) -> int:
        """
        Add a new crawl job to the queue.

        Args:
            name: Unique name for the job
            url: Starting URL to crawl
            max_pages: Maximum pages to crawl
            max_depth: Maximum crawl depth
            priority: Job priority (higher = processed first)
            max_retries: Maximum retry attempts
            crawl_config: Additional crawl configuration

        Returns:
            Job ID
        """
        await self._init_pool()
        await self._ensure_tables()

        config = crawl_config or {}

        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """INSERT INTO crawl_jobs
                       (name, url, max_pages, max_depth, priority, max_retries, crawl_config)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       RETURNING id""",
                    name, url, max_pages, max_depth, priority, max_retries, json.dumps(config)
                )
                self.log(f"Added job: {name} (ID: {row['id']})")
                return row['id']
            except Exception as e:
                if "unique constraint" in str(e).lower():
                    # Job already exists, get its ID
                    row = await conn.fetchrow(
                        "SELECT id FROM crawl_jobs WHERE name = $1", name
                    )
                    self.log(f"Job already exists: {name} (ID: {row['id']})")
                    return row['id']
                raise

    async def pick_job(self) -> Optional[CrawlJob]:
        """
        Pick a random pending job and lock it for processing.

        Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions.

        Returns:
            CrawlJob if one was picked, None otherwise
        """
        await self._init_pool()
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            # First, release any stale locks (jobs locked too long)
            stale_threshold = datetime.utcnow() - timedelta(minutes=self.LOCK_TIMEOUT_MINUTES)
            await conn.execute(
                """UPDATE crawl_jobs
                   SET status = 'pending', worker_id = NULL, locked_at = NULL
                   WHERE status = 'running' AND locked_at < $1""",
                stale_threshold
            )

            # Pick a random job from pending or retrying jobs ready for retry
            # Using TABLESAMPLE or ORDER BY RANDOM() with LIMIT
            row = await conn.fetchrow(
                """WITH eligible_jobs AS (
                       SELECT id FROM crawl_jobs
                       WHERE (status = 'pending')
                          OR (status = 'retrying' AND next_retry_at <= CURRENT_TIMESTAMP)
                       ORDER BY priority DESC, RANDOM()
                       LIMIT 1
                       FOR UPDATE SKIP LOCKED
                   )
                   UPDATE crawl_jobs j
                   SET status = 'running',
                       worker_id = $1,
                       locked_at = CURRENT_TIMESTAMP,
                       started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                       updated_at = CURRENT_TIMESTAMP
                   FROM eligible_jobs e
                   WHERE j.id = e.id
                   RETURNING j.*"""
                , self.worker_id
            )

            if not row:
                return None

            job = CrawlJob(
                id=row['id'],
                name=row['name'],
                url=row['url'],
                status=row['status'],
                priority=row['priority'],
                max_pages=row['max_pages'],
                max_depth=row['max_depth'],
                retry_count=row['retry_count'],
                max_retries=row['max_retries'],
                worker_id=row['worker_id'],
                locked_at=row['locked_at'],
                started_at=row['started_at'],
                completed_at=row['completed_at'],
                error_message=row['error_message'],
                crawl_config=json.loads(row['crawl_config']) if row['crawl_config'] else {},
                crawl_stats=json.loads(row['crawl_stats']) if row['crawl_stats'] else {},
                created_at=row['created_at'],
                updated_at=row['updated_at'],
            )

            self.log(f"Picked job: {job.name} (ID: {job.id}, retry: {job.retry_count})")
            return job

    async def complete_job(self, job_id: int, stats: Dict):
        """
        Mark a job as completed with crawl statistics.

        Args:
            job_id: Job ID
            stats: Crawl statistics to store
        """
        await self._init_pool()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE crawl_jobs
                   SET status = 'completed',
                       completed_at = CURRENT_TIMESTAMP,
                       crawl_stats = $2,
                       error_message = NULL,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = $1""",
                job_id, json.dumps(stats)
            )
            self.log(f"Completed job ID: {job_id}")

    async def fail_job(self, job_id: int, error: str, can_retry: bool = True):
        """
        Mark a job as failed, optionally scheduling a retry.

        Args:
            job_id: Job ID
            error: Error message
            can_retry: Whether to schedule a retry
        """
        await self._init_pool()

        async with self._pool.acquire() as conn:
            # Get current retry count
            row = await conn.fetchrow(
                "SELECT retry_count, max_retries FROM crawl_jobs WHERE id = $1",
                job_id
            )

            if not row:
                return

            retry_count = row['retry_count']
            max_retries = row['max_retries']

            if can_retry and retry_count < max_retries:
                # Schedule retry with exponential backoff
                delay_idx = min(retry_count, len(self.RETRY_DELAYS) - 1)
                delay_seconds = self.RETRY_DELAYS[delay_idx]
                next_retry = datetime.utcnow() + timedelta(seconds=delay_seconds)

                await conn.execute(
                    """UPDATE crawl_jobs
                       SET status = 'retrying',
                           retry_count = retry_count + 1,
                           next_retry_at = $2,
                           error_message = $3,
                           worker_id = NULL,
                           locked_at = NULL,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = $1""",
                    job_id, next_retry, error
                )
                self.log(f"Job {job_id} scheduled for retry in {delay_seconds}s (attempt {retry_count + 1}/{max_retries})")
            else:
                # Max retries exceeded, mark as failed
                await conn.execute(
                    """UPDATE crawl_jobs
                       SET status = 'failed',
                           error_message = $2,
                           worker_id = NULL,
                           locked_at = NULL,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = $1""",
                    job_id, error
                )
                self.log(f"Job {job_id} failed permanently: {error[:100]}")

    async def release_job(self, job_id: int):
        """
        Release a job lock without completing or failing it.
        Used when worker shuts down gracefully.
        """
        await self._init_pool()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE crawl_jobs
                   SET status = 'pending',
                       worker_id = NULL,
                       locked_at = NULL,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = $1 AND worker_id = $2""",
                job_id, self.worker_id
            )
            self.log(f"Released job ID: {job_id}")

    async def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        List jobs with optional status filter.

        Args:
            status: Filter by status (pending, running, completed, failed, retrying)
            limit: Maximum number of jobs to return

        Returns:
            List of job dictionaries
        """
        await self._init_pool()
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """SELECT * FROM crawl_jobs
                       WHERE status = $1
                       ORDER BY priority DESC, created_at DESC
                       LIMIT $2""",
                    status, limit
                )
            else:
                rows = await conn.fetch(
                    """SELECT * FROM crawl_jobs
                       ORDER BY priority DESC, created_at DESC
                       LIMIT $1""",
                    limit
                )

            return [
                {
                    "id": r['id'],
                    "name": r['name'],
                    "url": r['url'],
                    "status": r['status'],
                    "priority": r['priority'],
                    "max_pages": r['max_pages'],
                    "max_depth": r['max_depth'],
                    "retry_count": r['retry_count'],
                    "max_retries": r['max_retries'],
                    "worker_id": r['worker_id'],
                    "error_message": r['error_message'][:100] if r['error_message'] else None,
                    "crawl_stats": json.loads(r['crawl_stats']) if r['crawl_stats'] else {},
                    "created_at": r['created_at'].isoformat() if r['created_at'] else None,
                    "started_at": r['started_at'].isoformat() if r['started_at'] else None,
                    "completed_at": r['completed_at'].isoformat() if r['completed_at'] else None,
                }
                for r in rows
            ]

    async def get_stats(self) -> Dict:
        """Get job queue statistics."""
        await self._init_pool()
        await self._ensure_tables()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                       COUNT(*) FILTER (WHERE status = 'pending') as pending,
                       COUNT(*) FILTER (WHERE status = 'running') as running,
                       COUNT(*) FILTER (WHERE status = 'completed') as completed,
                       COUNT(*) FILTER (WHERE status = 'failed') as failed,
                       COUNT(*) FILTER (WHERE status = 'retrying') as retrying,
                       COUNT(*) as total
                   FROM crawl_jobs"""
            )

            return {
                "pending": row['pending'],
                "running": row['running'],
                "completed": row['completed'],
                "failed": row['failed'],
                "retrying": row['retrying'],
                "total": row['total'],
            }

    async def reset_job(self, job_id: int):
        """Reset a failed job to pending status."""
        await self._init_pool()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE crawl_jobs
                   SET status = 'pending',
                       retry_count = 0,
                       error_message = NULL,
                       worker_id = NULL,
                       locked_at = NULL,
                       started_at = NULL,
                       completed_at = NULL,
                       next_retry_at = NULL,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = $1""",
                job_id
            )
            self.log(f"Reset job ID: {job_id}")

    async def delete_job(self, job_id: int):
        """Delete a job."""
        await self._init_pool()

        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM crawl_jobs WHERE id = $1", job_id)
            self.log(f"Deleted job ID: {job_id}")

    def shutdown(self):
        """Signal the worker to shut down gracefully."""
        self._shutdown = True
        self.log("Shutdown signal received")

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None


async def run_worker(
    job_manager: CrawlJobManager,
    postgres_storage: bool = True,
    qdrant_storage: bool = False,
    qdrant_url: str = QDRANT_URL,
    qdrant_api_key: str = QDRANT_API_KEY,
    embedding_model: str = "all-MiniLM-L6-v2",
    chunk_size: int = 500,
    engine: str = "crawl4ai",
    verbose: bool = False,
):
    """
    Run a worker that continuously processes crawl jobs.

    Args:
        job_manager: CrawlJobManager instance
        postgres_storage: Store results in PostgreSQL
        qdrant_storage: Store results in Qdrant
        qdrant_url: Qdrant server URL
        qdrant_api_key: Qdrant API key
        embedding_model: Embedding model for Qdrant
        chunk_size: Chunk size for text splitting
        engine: Crawler engine (basic or crawl4ai)
        verbose: Verbose output
    """
    def log(msg: str):
        if verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Worker] {msg}", file=sys.stderr)

    log(f"Starting worker: {job_manager.worker_id}")
    log(f"PostgreSQL storage: {postgres_storage}, Qdrant storage: {qdrant_storage}")

    current_job: Optional[CrawlJob] = None

    # Handle graceful shutdown
    def handle_signal(signum, frame):
        log("Received shutdown signal")
        job_manager.shutdown()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not job_manager._shutdown:
        try:
            # Pick a job
            job = await job_manager.pick_job()

            if not job:
                # No jobs available, wait and retry
                log("No jobs available, waiting...")
                await asyncio.sleep(5)
                continue

            current_job = job
            log(f"Processing job: {job.name} ({job.url})")

            # Create crawler
            if engine == "crawl4ai":
                crawler = Crawl4AIWrapper(
                    max_depth=job.max_depth,
                    max_pages=job.max_pages,
                    concurrent_requests=job.crawl_config.get("concurrent", 5),
                    verbose=verbose,
                )
            else:
                crawler = StandaloneCrawler(
                    max_depth=job.max_depth,
                    max_pages=job.max_pages,
                    concurrent_requests=job.crawl_config.get("concurrent", 5),
                    respect_robots=job.crawl_config.get("respect_robots", True),
                    verbose=verbose,
                )

            # Run crawl
            start_time = datetime.utcnow()
            pages = await crawler.crawl(job.url)

            if not pages:
                await job_manager.fail_job(job.id, "No pages crawled")
                current_job = None
                continue

            # Extract version from crawled pages (most common version found)
            detected_versions = {}
            for p in pages:
                version = p.metadata.get("version")
                if version:
                    detected_versions[version] = detected_versions.get(version, 0) + 1

            # Find the most common version
            primary_version = None
            version_source = None
            if detected_versions:
                primary_version = max(detected_versions, key=detected_versions.get)
                # Find the source of this version from the first page that has it
                for p in pages:
                    if p.metadata.get("version") == primary_version:
                        version_source = p.metadata.get("version_source")
                        break

            crawl_stats = {
                "pages_crawled": len(pages),
                "total_words": sum(p.word_count for p in pages),
                "crawl_duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "version": primary_version,
                "version_source": version_source,
                "all_versions_detected": detected_versions,
            }

            # Store in PostgreSQL
            if postgres_storage:
                log(f"Storing {len(pages)} pages in PostgreSQL...")
                pg_storage = PostgresStorage(
                    source_name=job.name,
                    host=job_manager.host,
                    port=job_manager.port,
                    database=job_manager.database,
                    user=job_manager.user,
                    password=job_manager.password,
                    chunk_size=chunk_size,
                    verbose=verbose,
                )
                pg_stats = await pg_storage.store(pages, job.url)
                crawl_stats["postgres"] = pg_stats

            # Store in Qdrant
            if qdrant_storage:
                log(f"Storing {len(pages)} pages in Qdrant...")
                qdrant = QdrantStorage(
                    library_name=job.name,
                    qdrant_url=qdrant_url,
                    qdrant_api_key=qdrant_api_key,
                    embedding_model=embedding_model,
                    chunk_size=chunk_size,
                    verbose=verbose,
                )
                vectors_stored = qdrant.store(pages)
                crawl_stats["qdrant"] = {"vectors_stored": vectors_stored, "collection": qdrant.collection_name}

            # Mark job as completed
            await job_manager.complete_job(job.id, crawl_stats)
            log(f"Job completed: {job.name} - {crawl_stats}")
            current_job = None

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            log(f"Error processing job: {error_msg[:200]}")

            if current_job:
                await job_manager.fail_job(current_job.id, error_msg[:1000])
                current_job = None

            # Wait before retrying to avoid tight loop on persistent errors
            await asyncio.sleep(5)

    # Graceful shutdown - release any held job
    if current_job:
        log(f"Releasing job {current_job.id} on shutdown")
        await job_manager.release_job(current_job.id)

    log("Worker stopped")


def save_results(pages: List[CrawledPage], output_path: str, format: str):
    """Save crawled pages to file."""
    path = Path(output_path)

    if format == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(p) for p in pages], f, indent=2, ensure_ascii=False)

    elif format == "jsonl":
        with open(path, "w", encoding="utf-8") as f:
            for page in pages:
                f.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")

    elif format == "csv":
        with open(path, "w", newline="", encoding="utf-8") as f:
            if pages:
                writer = csv.DictWriter(f, fieldnames=list(asdict(pages[0]).keys()))
                writer.writeheader()
                for page in pages:
                    row = asdict(page)
                    # Convert metadata dict to string for CSV
                    row["metadata"] = json.dumps(row["metadata"])
                    writer.writerow(row)

    else:
        raise ValueError(f"Unknown format: {format}")


def main():
    parser = argparse.ArgumentParser(
        description="Standalone Web Crawler - Crawl websites and save content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic crawl with default settings
  python standalone_crawler.py https://docs.python.org

  # Crawl with custom limits and JSON output
  python standalone_crawler.py https://docs.example.com -o results.json -d 2 -p 50

  # Use Crawl4AI for JavaScript-heavy sites
  python standalone_crawler.py https://react.dev --engine crawl4ai

  # JSONL output for streaming processing
  python standalone_crawler.py https://docs.example.com --format jsonl -o docs.jsonl

  # Store in Qdrant with embeddings
  python standalone_crawler.py https://docs.example.com --qdrant --collection my_docs

  # Store in PostgreSQL
  python standalone_crawler.py https://docs.example.com --postgres --source my_docs

  # Store in both Qdrant and PostgreSQL
  python standalone_crawler.py https://docs.example.com --qdrant --postgres --collection my_docs --source my_docs

  # Search Qdrant collection (semantic search)
  python standalone_crawler.py --search "how to authenticate" --collection my_docs

  # Search PostgreSQL (full-text search)
  python standalone_crawler.py --pg-search "authentication" --source my_docs

  # View PostgreSQL stats
  python standalone_crawler.py --pg-stats --source my_docs

  # Job Queue Mode
  # Add a job to the queue
  python standalone_crawler.py --job-add my_docs https://docs.example.com -p 50 -d 2

  # Start a worker to process jobs
  python standalone_crawler.py --worker --postgres

  # Start worker with both storage backends
  python standalone_crawler.py --worker --postgres --qdrant

  # List all jobs
  python standalone_crawler.py --job-list

  # List jobs by status
  python standalone_crawler.py --job-list --job-status pending

  # View job queue stats
  python standalone_crawler.py --job-stats

  # Reset a failed job
  python standalone_crawler.py --job-reset 123

  # Delete a job
  python standalone_crawler.py --job-delete 123

  # Verbose mode to see progress
  python standalone_crawler.py https://docs.example.com -v
        """,
    )

    parser.add_argument("url", nargs="?", help="Starting URL to crawl")
    parser.add_argument("-o", "--output", default="crawl_results.json", help="Output file path (default: crawl_results.json)")
    parser.add_argument("-f", "--format", choices=["json", "jsonl", "csv"], default="json", help="Output format (default: json)")
    parser.add_argument("-d", "--max-depth", type=int, default=3, help="Maximum crawl depth (default: 3)")
    parser.add_argument("-p", "--max-pages", type=int, default=100, help="Maximum pages to crawl (default: 100)")
    parser.add_argument("-c", "--concurrent", type=int, default=5, help="Concurrent requests (default: 5)")
    parser.add_argument("--engine", choices=["basic", "crawl4ai"], default="crawl4ai", help="Crawler engine (default: crawl4ai)")
    parser.add_argument("--no-robots", action="store_true", help="Ignore robots.txt")
    parser.add_argument("--user-agent", default="StandaloneCrawler/1.0", help="Custom user agent")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # Qdrant options
    qdrant_group = parser.add_argument_group("Qdrant Storage")
    qdrant_group.add_argument("--qdrant", action="store_true", help="Store results in Qdrant with embeddings")
    qdrant_group.add_argument("--collection", default="crawled_docs", help="Qdrant collection name (default: crawled_docs)")
    qdrant_group.add_argument("--qdrant-url", default=QDRANT_URL, help="Qdrant server URL")
    qdrant_group.add_argument("--qdrant-key", default=QDRANT_API_KEY, help="Qdrant API key")
    qdrant_group.add_argument("--embedding-model", default="all-MiniLM-L6-v2", help="Embedding model (default: all-MiniLM-L6-v2)")
    qdrant_group.add_argument("--chunk-size", type=int, default=500, help="Words per chunk (default: 500)")

    # PostgreSQL options
    pg_group = parser.add_argument_group("PostgreSQL Storage")
    pg_group.add_argument("--postgres", action="store_true", help="Store results in PostgreSQL")
    pg_group.add_argument("--source", default="crawled_docs", help="Source name for PostgreSQL (default: crawled_docs)")
    pg_group.add_argument("--db-host", default=DB_HOST, help="PostgreSQL host")
    pg_group.add_argument("--db-port", default=DB_PORT, help="PostgreSQL port (default: 5432)")
    pg_group.add_argument("--db-name", default=DB_NAME, help="PostgreSQL database name")
    pg_group.add_argument("--db-user", default=DB_USER, help="PostgreSQL username")
    pg_group.add_argument("--db-password", default=DB_PASSWORD, help="PostgreSQL password")

    # Search mode (Qdrant)
    search_group = parser.add_argument_group("Search Mode (Qdrant)")
    search_group.add_argument("--search", metavar="QUERY", help="Semantic search in Qdrant collection")
    search_group.add_argument("--library", metavar="NAME", help="Filter search to specific library (e.g., langchain, react)")
    search_group.add_argument("--limit", type=int, default=5, help="Number of search results (default: 5)")
    search_group.add_argument("--stats", action="store_true", help="Show Qdrant collection statistics")

    # Search mode (PostgreSQL)
    pg_search_group = parser.add_argument_group("Search Mode (PostgreSQL)")
    pg_search_group.add_argument("--pg-search", metavar="QUERY", help="Full-text search in PostgreSQL")
    pg_search_group.add_argument("--pg-stats", action="store_true", help="Show PostgreSQL source statistics")

    # Job queue management
    job_group = parser.add_argument_group("Job Queue")
    job_group.add_argument("--job-add", nargs=2, metavar=("NAME", "URL"), help="Add a crawl job to the queue")
    job_group.add_argument("--job-priority", type=int, default=0, help="Job priority (higher = processed first)")
    job_group.add_argument("--job-retries", type=int, default=3, help="Maximum retry attempts (default: 3)")
    job_group.add_argument("--job-list", action="store_true", help="List all jobs")
    job_group.add_argument("--job-status", choices=["pending", "running", "completed", "failed", "retrying"], help="Filter jobs by status")
    job_group.add_argument("--job-stats", action="store_true", help="Show job queue statistics")
    job_group.add_argument("--job-reset", type=int, metavar="ID", help="Reset a failed job to pending")
    job_group.add_argument("--job-delete", type=int, metavar="ID", help="Delete a job")

    # Worker mode
    worker_group = parser.add_argument_group("Worker Mode")
    worker_group.add_argument("--worker", action="store_true", help="Run as a worker processing jobs from the queue")
    worker_group.add_argument("--worker-id", help="Custom worker ID (default: auto-generated)")

    args = parser.parse_args()

    # Handle Qdrant search mode
    if args.search:
        storage = QdrantStorage(
            library_name="search",  # Not used for search, just required param
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_key,
            embedding_model=args.embedding_model,
            verbose=args.verbose,
        )

        library_filter = getattr(args, 'library', None)
        filter_msg = f" (library: {library_filter})" if library_filter else " (all libraries)"
        print(f"Searching docs{filter_msg} for: {args.search}", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

        results = storage.search(args.search, limit=args.limit, library=library_filter)

        for i, result in enumerate(results, 1):
            print(f"\n[{i}] Score: {result['score']:.4f} | Library: {result.get('library', '-')} | Version: {result.get('version', '-')}")
            print(f"    URL: {result['url']}")
            print(f"    Title: {result['title']}")
            print(f"    Content: {result['content'][:200]}...")

        return

    # Handle Qdrant stats mode
    if args.stats:
        storage = QdrantStorage(
            library_name="stats",  # Not used for stats, just required param
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_key,
            verbose=args.verbose,
        )

        stats = storage.get_stats()
        print(f"Collection: {stats.get('collection')}")
        print(f"Total Vectors: {stats.get('vectors_count', 'N/A')}")
        print(f"Status: {stats.get('status', 'N/A')}")

        libraries = stats.get('libraries', {})
        if libraries:
            print(f"\nLibraries ({len(libraries)}):")
            for lib, count in sorted(libraries.items(), key=lambda x: -x[1]):
                print(f"  {lib}: {count} vectors")
        return

    # Handle PostgreSQL search mode
    if args.pg_search:
        storage = PostgresStorage(
            source_name=args.source,
            host=args.db_host,
            port=args.db_port,
            database=args.db_name,
            user=args.db_user,
            password=args.db_password,
            verbose=args.verbose,
        )

        print(f"Searching PostgreSQL source '{args.source}' for: {args.pg_search}", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

        results = asyncio.run(storage.search(args.pg_search, limit=args.limit))

        for i, result in enumerate(results, 1):
            print(f"\n[{i}] Rank: {result['rank']:.4f}")
            print(f"    URL: {result['url']}")
            print(f"    Title: {result['title']}")
            print(f"    Content: {result['content'][:200]}...")

        return

    # Handle PostgreSQL stats mode
    if args.pg_stats:
        storage = PostgresStorage(
            source_name=args.source,
            host=args.db_host,
            port=args.db_port,
            database=args.db_name,
            user=args.db_user,
            password=args.db_password,
            verbose=args.verbose,
        )

        stats = asyncio.run(storage.get_stats())
        print(f"Source: {stats.get('source')}")
        if stats.get('exists'):
            print(f"Start URL: {stats.get('start_url')}")
            print(f"Pages: {stats.get('pages')}")
            print(f"Chunks: {stats.get('chunks')}")
            print(f"Total Words: {stats.get('total_words'):,}")
            print(f"Created: {stats.get('created_at')}")
            print(f"Last Crawled: {stats.get('last_crawled_at')}")
        else:
            print("Source does not exist")
        return

    # Create job manager for job-related operations
    def get_job_manager():
        return CrawlJobManager(
            host=args.db_host,
            port=args.db_port,
            database=args.db_name,
            user=args.db_user,
            password=args.db_password,
            worker_id=getattr(args, 'worker_id', None),
            verbose=args.verbose,
        )

    # Handle job add
    if args.job_add:
        name, url = args.job_add
        job_manager = get_job_manager()

        job_id = asyncio.run(job_manager.add_job(
            name=name,
            url=url,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            priority=args.job_priority,
            max_retries=args.job_retries,
            crawl_config={
                "concurrent": args.concurrent,
                "respect_robots": not args.no_robots,
                "engine": args.engine,
            }
        ))

        print(f"Added job: {name} (ID: {job_id})")
        print(f"  URL: {url}")
        print(f"  Max pages: {args.max_pages}, Max depth: {args.max_depth}")
        print(f"  Priority: {args.job_priority}, Max retries: {args.job_retries}")
        return

    # Handle job list
    if args.job_list:
        job_manager = get_job_manager()
        jobs = asyncio.run(job_manager.list_jobs(status=args.job_status, limit=100))

        if not jobs:
            print("No jobs found")
            return

        print(f"{'ID':<6} {'Name':<25} {'Status':<12} {'Version':<12} {'Pages':<8} {'Retries':<10}")
        print("-" * 90)

        for job in jobs:
            retry_info = f"{job['retry_count']}/{job['max_retries']}"
            name = job['name'][:22] + "..." if len(job['name']) > 25 else job['name']
            crawl_stats = job.get('crawl_stats', {}) or {}
            version = crawl_stats.get('version') or '-'
            if len(str(version)) > 10:
                version = str(version)[:9] + "..."
            print(f"{job['id']:<6} {name:<25} {job['status']:<12} {version:<12} {job['max_pages']:<8} {retry_info:<10}")

        return

    # Handle job stats
    if args.job_stats:
        job_manager = get_job_manager()
        stats = asyncio.run(job_manager.get_stats())

        print("Job Queue Statistics")
        print("-" * 30)
        print(f"Pending:   {stats['pending']}")
        print(f"Running:   {stats['running']}")
        print(f"Completed: {stats['completed']}")
        print(f"Failed:    {stats['failed']}")
        print(f"Retrying:  {stats['retrying']}")
        print("-" * 30)
        print(f"Total:     {stats['total']}")
        return

    # Handle job reset
    if args.job_reset:
        job_manager = get_job_manager()
        asyncio.run(job_manager.reset_job(args.job_reset))
        print(f"Reset job ID: {args.job_reset}")
        return

    # Handle job delete
    if args.job_delete:
        job_manager = get_job_manager()
        asyncio.run(job_manager.delete_job(args.job_delete))
        print(f"Deleted job ID: {args.job_delete}")
        return

    # Handle worker mode
    if args.worker:
        if not args.postgres and not args.qdrant:
            print("Warning: No storage backend specified. Use --postgres and/or --qdrant", file=sys.stderr)
            print("Running worker with PostgreSQL storage by default...", file=sys.stderr)
            args.postgres = True

        job_manager = get_job_manager()

        print(f"Starting worker: {job_manager.worker_id}", file=sys.stderr)
        print(f"PostgreSQL: {args.postgres}, Qdrant: {args.qdrant}", file=sys.stderr)
        print("Press Ctrl+C to stop", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

        asyncio.run(run_worker(
            job_manager=job_manager,
            postgres_storage=args.postgres,
            qdrant_storage=args.qdrant,
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_key,
            embedding_model=args.embedding_model,
            chunk_size=args.chunk_size,
            engine=args.engine,
            verbose=args.verbose,
        ))
        return

    # Validate URL for crawling mode
    if not args.url:
        parser.error("URL is required for crawling mode. Use --search, --worker, or --job-* for other modes.")

    parsed = urlparse(args.url)
    if not parsed.scheme or not parsed.netloc:
        print(f"Error: Invalid URL '{args.url}'", file=sys.stderr)
        print("URL must include scheme (http:// or https://)", file=sys.stderr)
        sys.exit(1)

    print(f"Starting crawl of {args.url}", file=sys.stderr)
    print(f"Engine: {args.engine}, Max pages: {args.max_pages}, Max depth: {args.max_depth}", file=sys.stderr)
    if args.qdrant:
        print(f"Qdrant: Storing to collection '{args.collection}'", file=sys.stderr)
    if args.postgres:
        print(f"PostgreSQL: Storing to source '{args.source}'", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    # Choose crawler engine
    if args.engine == "crawl4ai":
        crawler = Crawl4AIWrapper(
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            concurrent_requests=args.concurrent,
            respect_robots=not args.no_robots,
            verbose=args.verbose,
        )
    else:
        crawler = StandaloneCrawler(
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            concurrent_requests=args.concurrent,
            respect_robots=not args.no_robots,
            user_agent=args.user_agent,
            timeout=args.timeout,
            verbose=args.verbose,
        )

    # Run crawler
    pages = asyncio.run(crawler.crawl(args.url))

    if not pages:
        print("No pages crawled!", file=sys.stderr)
        sys.exit(1)

    # Store in Qdrant if requested
    if args.qdrant:
        print("-" * 60, file=sys.stderr)
        print("Storing in Qdrant with embeddings...", file=sys.stderr)

        qdrant_storage = QdrantStorage(
            collection_name=args.collection,
            qdrant_url=args.qdrant_url,
            qdrant_api_key=args.qdrant_key,
            embedding_model=args.embedding_model,
            chunk_size=args.chunk_size,
            verbose=args.verbose,
        )

        vectors_stored = qdrant_storage.store(pages)
        print(f"Stored {vectors_stored} vectors in collection '{args.collection}'", file=sys.stderr)

    # Store in PostgreSQL if requested
    if args.postgres:
        print("-" * 60, file=sys.stderr)
        print("Storing in PostgreSQL...", file=sys.stderr)

        pg_storage = PostgresStorage(
            source_name=args.source,
            host=args.db_host,
            port=args.db_port,
            database=args.db_name,
            user=args.db_user,
            password=args.db_password,
            chunk_size=args.chunk_size,
            verbose=args.verbose,
        )

        pg_stats = asyncio.run(pg_storage.store(pages, args.url))
        print(f"Stored {pg_stats['pages_stored']} new pages, {pg_stats['pages_updated']} updated, {pg_stats['chunks_stored']} chunks", file=sys.stderr)

    # Save results to file
    save_results(pages, args.output, args.format)

    print("-" * 60, file=sys.stderr)
    print(f"Crawled {len(pages)} pages", file=sys.stderr)
    print(f"Total words: {sum(p.word_count for p in pages):,}", file=sys.stderr)
    print(f"Results saved to: {args.output}", file=sys.stderr)
    if args.qdrant:
        print(f"Vectors stored in Qdrant collection: {args.collection}", file=sys.stderr)
    if args.postgres:
        print(f"Pages stored in PostgreSQL source: {args.source}", file=sys.stderr)


if __name__ == "__main__":
    main()
