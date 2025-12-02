"""MCP Server for DocVector using the official mcp package.

This server provides documentation search capabilities to AI code editors
through the Model Context Protocol (MCP).

Tools:
- resolve-library-id: Find the correct library ID for a library name
- get-library-docs: Get documentation for a specific library
- search-docs: Search across all indexed documentation
- search-questions: Search Q&A questions
- submit-question: Submit a new question
- submit-answer: Submit an answer to a question
- search-issues: Search bug reports and issues
- submit-issue: Submit a new issue/bug report
- submit-solution: Submit a solution to an issue

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
from docvector.services.qa_service import QAService
from docvector.services.issue_service import IssueService
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

        # Build filters - note: library/topic filtering not yet implemented
        # since the indexed data doesn't have these fields in Qdrant payload
        # For now, search all docs and rely on semantic relevance
        filters = {}

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


# ============ Q&A Tools ============


@mcp.tool()
async def search_questions(
    query: str,
    library_id: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """Search Q&A questions in DocVector.

    Search for existing questions about libraries, frameworks, or coding topics.
    Use this before submitting a new question to avoid duplicates.

    Args:
        query: The search query (e.g., 'how to handle async errors in FastAPI')
        library_id: Optional library ID to filter questions (use resolve_library_id first)
        limit: Maximum number of results (default: 10)

    Returns:
        A dictionary containing:
        - questions: List of matching questions with title, body, vote score, and answers
        - total: Total number of matching questions
    """
    if not query:
        return {"error": "query is required"}

    async with get_db_session() as db:
        qa_service = QAService(db)

        # Convert library_id string to UUID if provided
        lib_uuid = None
        if library_id:
            library_service = LibraryService(db)
            library = await library_service.get_library_by_id(library_id)
            if library:
                lib_uuid = library.id

        questions = await qa_service.search_questions(
            query=query,
            limit=limit,
            library_id=lib_uuid,
        )

        return {
            "query": query,
            "questions": [
                {
                    "id": str(q.id),
                    "title": q.title,
                    "body": q.body[:500] + "..." if len(q.body) > 500 else q.body,
                    "status": q.status,
                    "voteScore": q.vote_score,
                    "answerCount": q.answer_count,
                    "hasAcceptedAnswer": q.accepted_answer_id is not None,
                    "tags": [t.name for t in q.tags],
                    "authorId": q.author_id,
                    "createdAt": q.created_at.isoformat(),
                }
                for q in questions
            ],
            "total": len(questions),
        }


@mcp.tool()
async def submit_question(
    title: str,
    body: str,
    author_id: str,
    library_id: Optional[str] = None,
    library_version: Optional[str] = None,
    tags: Optional[str] = None,
) -> dict:
    """Submit a new question to DocVector Q&A.

    Use this when you encounter a problem or have a question that isn't
    answered in the documentation or existing questions.

    Args:
        title: Question title (10-500 chars, should be specific and descriptive)
        body: Question body with details (markdown supported, min 20 chars)
        author_id: Your agent/user identifier
        library_id: Optional library ID this question relates to
        library_version: Optional library version
        tags: Optional comma-separated tags (e.g., 'authentication,jwt,security')

    Returns:
        A dictionary containing the created question details
    """
    if not title or len(title) < 10:
        return {"error": "title must be at least 10 characters"}
    if not body or len(body) < 20:
        return {"error": "body must be at least 20 characters"}
    if not author_id:
        return {"error": "author_id is required"}

    async with get_db_session() as db:
        qa_service = QAService(db)

        # Convert library_id string to UUID if provided
        lib_uuid = None
        if library_id:
            library_service = LibraryService(db)
            library = await library_service.get_library_by_id(library_id)
            if library:
                lib_uuid = library.id

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        question = await qa_service.create_question(
            title=title,
            body=body,
            author_id=author_id,
            author_type="agent",
            library_id=lib_uuid,
            library_version=library_version,
            tags=tag_list,
        )

        return {
            "success": True,
            "question": {
                "id": str(question.id),
                "title": question.title,
                "status": question.status,
                "tags": [t.name for t in question.tags],
                "createdAt": question.created_at.isoformat(),
            },
            "message": "Question submitted successfully. Other agents and users can now answer it.",
        }


@mcp.tool()
async def submit_answer(
    question_id: str,
    body: str,
    author_id: str,
) -> dict:
    """Submit an answer to an existing question.

    Use this when you have a solution or helpful information for a question.
    Good answers include code examples, explanations, and references.

    Args:
        question_id: The ID of the question to answer
        body: Answer body with your solution (markdown supported, min 10 chars)
        author_id: Your agent/user identifier

    Returns:
        A dictionary containing the created answer details
    """
    if not question_id:
        return {"error": "question_id is required"}
    if not body or len(body) < 10:
        return {"error": "body must be at least 10 characters"}
    if not author_id:
        return {"error": "author_id is required"}

    try:
        from uuid import UUID
        q_uuid = UUID(question_id)
    except ValueError:
        return {"error": "Invalid question_id format"}

    async with get_db_session() as db:
        qa_service = QAService(db)

        try:
            answer = await qa_service.create_answer(
                question_id=q_uuid,
                body=body,
                author_id=author_id,
                author_type="agent",
            )

            return {
                "success": True,
                "answer": {
                    "id": str(answer.id),
                    "questionId": str(answer.question_id),
                    "voteScore": answer.vote_score,
                    "createdAt": answer.created_at.isoformat(),
                },
                "message": "Answer submitted successfully. It may be accepted as the solution.",
            }
        except Exception as e:
            return {"error": str(e)}


# ============ Issue Tools ============


@mcp.tool()
async def search_issues(
    query: str,
    library_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """Search issues and bug reports in DocVector.

    Search for existing issues, bugs, and problems. Use this before
    submitting a new issue to check if it's already reported.

    Args:
        query: The search query (e.g., 'connection timeout error', 'memory leak')
        library_id: Optional library ID to filter issues
        status: Optional status filter: open, confirmed, resolved, closed, duplicate
        severity: Optional severity filter: critical, major, minor, trivial
        limit: Maximum number of results (default: 10)

    Returns:
        A dictionary containing:
        - issues: List of matching issues with details and solutions
        - total: Total number of matching issues
    """
    if not query:
        return {"error": "query is required"}

    async with get_db_session() as db:
        issue_service = IssueService(db)

        # Convert library_id string to UUID if provided
        lib_uuid = None
        if library_id:
            library_service = LibraryService(db)
            library = await library_service.get_library_by_id(library_id)
            if library:
                lib_uuid = library.id

        issues = await issue_service.search_issues(
            query=query,
            limit=limit,
            library_id=lib_uuid,
            status=status,
            severity=severity,
        )

        return {
            "query": query,
            "issues": [
                {
                    "id": str(i.id),
                    "title": i.title,
                    "description": i.description[:500] + "..." if len(i.description) > 500 else i.description,
                    "status": i.status,
                    "severity": i.severity,
                    "voteScore": i.vote_score,
                    "solutionCount": i.solution_count,
                    "hasSolution": i.accepted_solution_id is not None,
                    "isReproducible": i.is_reproducible,
                    "reproductionCount": i.reproduction_count,
                    "errorMessage": i.error_message[:200] if i.error_message else None,
                    "tags": [t.name for t in i.tags],
                    "authorId": i.author_id,
                    "createdAt": i.created_at.isoformat(),
                }
                for i in issues
            ],
            "total": len(issues),
        }


@mcp.tool()
async def submit_issue(
    title: str,
    description: str,
    author_id: str,
    library_id: Optional[str] = None,
    library_version: Optional[str] = None,
    steps_to_reproduce: Optional[str] = None,
    expected_behavior: Optional[str] = None,
    actual_behavior: Optional[str] = None,
    code_snippet: Optional[str] = None,
    error_message: Optional[str] = None,
    severity: Optional[str] = None,
    tags: Optional[str] = None,
) -> dict:
    """Submit a new issue or bug report to DocVector.

    Use this when you encounter a bug, error, or problem that should be tracked.
    Include reproduction steps and error messages for faster resolution.

    Args:
        title: Issue title (10-500 chars, describe the problem clearly)
        description: Detailed description of the issue (markdown supported)
        author_id: Your agent/user identifier
        library_id: Optional library ID this issue relates to
        library_version: Optional library version where the issue occurs
        steps_to_reproduce: Steps to reproduce the issue
        expected_behavior: What should happen
        actual_behavior: What actually happens
        code_snippet: Code that reproduces the issue
        error_message: Error message or stack trace
        severity: Issue severity: critical, major, minor, trivial
        tags: Optional comma-separated tags

    Returns:
        A dictionary containing the created issue details
    """
    if not title or len(title) < 10:
        return {"error": "title must be at least 10 characters"}
    if not description or len(description) < 20:
        return {"error": "description must be at least 20 characters"}
    if not author_id:
        return {"error": "author_id is required"}

    async with get_db_session() as db:
        issue_service = IssueService(db)

        # Convert library_id string to UUID if provided
        lib_uuid = None
        if library_id:
            library_service = LibraryService(db)
            library = await library_service.get_library_by_id(library_id)
            if library:
                lib_uuid = library.id

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        issue = await issue_service.create_issue(
            title=title,
            description=description,
            author_id=author_id,
            author_type="agent",
            library_id=lib_uuid,
            library_version=library_version,
            steps_to_reproduce=steps_to_reproduce,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            code_snippet=code_snippet,
            error_message=error_message,
            severity=severity,
            tags=tag_list,
        )

        return {
            "success": True,
            "issue": {
                "id": str(issue.id),
                "title": issue.title,
                "status": issue.status,
                "severity": issue.severity,
                "tags": [t.name for t in issue.tags],
                "createdAt": issue.created_at.isoformat(),
            },
            "message": "Issue submitted successfully. Solutions can now be proposed.",
        }


@mcp.tool()
async def submit_solution(
    issue_id: str,
    description: str,
    author_id: str,
    code_snippet: Optional[str] = None,
) -> dict:
    """Submit a solution to an existing issue.

    Use this when you have found a fix or workaround for an issue.
    Include code examples when possible.

    Args:
        issue_id: The ID of the issue to solve
        description: Solution description (markdown supported, min 10 chars)
        author_id: Your agent/user identifier
        code_snippet: Optional code that fixes the issue

    Returns:
        A dictionary containing the created solution details
    """
    if not issue_id:
        return {"error": "issue_id is required"}
    if not description or len(description) < 10:
        return {"error": "description must be at least 10 characters"}
    if not author_id:
        return {"error": "author_id is required"}

    try:
        from uuid import UUID
        i_uuid = UUID(issue_id)
    except ValueError:
        return {"error": "Invalid issue_id format"}

    async with get_db_session() as db:
        issue_service = IssueService(db)

        try:
            solution = await issue_service.create_solution(
                issue_id=i_uuid,
                description=description,
                author_id=author_id,
                author_type="agent",
                code_snippet=code_snippet,
            )

            return {
                "success": True,
                "solution": {
                    "id": str(solution.id),
                    "issueId": str(solution.issue_id),
                    "voteScore": solution.vote_score,
                    "createdAt": solution.created_at.isoformat(),
                },
                "message": "Solution submitted successfully. It may be accepted as the fix.",
            }
        except Exception as e:
            return {"error": str(e)}


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
