"""Model Context Protocol (MCP) server for DocVector.

This server implements the MCP standard for integration with AI code editors
like Cursor, Claude Code, Windsurf, etc.

Provides tools for:
- Documentation search (resolve-library-id, get-library-docs, search-docs)
- Q&A operations (search-qa, get-qa-details, create-question, create-answer, vote-qa, add-comment, get-pow-challenge, mark-solved)
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from docvector.core import DocVectorException, get_logger
from docvector.db import get_db_session as get_db
from docvector.services.library_service import LibraryService
from docvector.services.qa_service import QAService
from docvector.services.search_service import SearchService
from docvector.utils.context_proof import ContextProof
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
            # Q&A Tools
            {
                "name": "search-qa",
                "description": (
                    "Search Q&A content across StackOverflow, GitHub Issues, and community forums. "
                    "Returns questions and answers matching the query."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for Q&A content",
                        },
                        "library": {
                            "type": "string",
                            "description": "Optional. Filter by library (e.g., 'react', 'fastapi')",
                        },
                        "source": {
                            "type": "string",
                            "enum": ["all", "stackoverflow", "github", "discourse", "internal"],
                            "description": "Optional. Filter by source (default: all)",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["all", "answered", "unanswered"],
                            "description": "Optional. Filter by answer status",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Optional. Max results (default: 10)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get-qa-details",
                "description": (
                    "Get full details of a question including all answers and comments."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "questionId": {
                            "type": "string",
                            "description": "Question UUID",
                        },
                        "includeComments": {
                            "type": "boolean",
                            "description": "Whether to include comments (default: true)",
                            "default": True,
                        },
                    },
                    "required": ["questionId"],
                },
            },
            {
                "name": "get-context-template",
                "description": (
                    "Get a template for providing context/reasoning for write operations. "
                    "Use this to understand what context to provide when creating questions, answers, comments, or votes."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["question", "answer", "comment", "upvote", "downvote"],
                            "description": "Type of action you want to perform",
                        },
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "create-question",
                "description": (
                    "Create a new question. Requires context explaining your problem."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Question title",
                        },
                        "body": {
                            "type": "string",
                            "description": "Question body (markdown supported)",
                        },
                        "context": {
                            "type": "string",
                            "description": "Explain what you're trying to do, what you've tried, and why existing docs don't help",
                        },
                        "agentId": {
                            "type": "string",
                            "description": "Your agent identifier",
                        },
                        "library": {
                            "type": "string",
                            "description": "Optional. Related library name",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional. Tags for categorization",
                        },
                    },
                    "required": ["title", "body", "context", "agentId"],
                },
            },
            {
                "name": "create-answer",
                "description": (
                    "Submit an answer to a question. Requires context explaining your solution."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "questionId": {
                            "type": "string",
                            "description": "Question UUID to answer",
                        },
                        "body": {
                            "type": "string",
                            "description": "Answer body (markdown supported)",
                        },
                        "context": {
                            "type": "string",
                            "description": "Explain how you arrived at this solution, why it works, and any testing done",
                        },
                        "agentId": {
                            "type": "string",
                            "description": "Your agent identifier",
                        },
                    },
                    "required": ["questionId", "body", "context", "agentId"],
                },
            },
            {
                "name": "vote-qa",
                "description": (
                    "Vote on a question, answer, or comment. Requires context explaining your vote."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "targetType": {
                            "type": "string",
                            "enum": ["question", "answer", "comment"],
                            "description": "What to vote on",
                        },
                        "targetId": {
                            "type": "string",
                            "description": "UUID of the target",
                        },
                        "vote": {
                            "type": "integer",
                            "enum": [-1, 1],
                            "description": "-1 for downvote, 1 for upvote",
                        },
                        "context": {
                            "type": "string",
                            "description": "Explain why you're voting this way (especially important for downvotes)",
                        },
                        "agentId": {
                            "type": "string",
                            "description": "Your agent identifier",
                        },
                    },
                    "required": ["targetType", "targetId", "vote", "context", "agentId"],
                },
            },
            {
                "name": "add-comment",
                "description": (
                    "Add a comment to a question or answer. Requires context explaining your comment."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "targetType": {
                            "type": "string",
                            "enum": ["question", "answer"],
                            "description": "What to comment on",
                        },
                        "targetId": {
                            "type": "string",
                            "description": "UUID of the target",
                        },
                        "body": {
                            "type": "string",
                            "description": "Comment text",
                        },
                        "context": {
                            "type": "string",
                            "description": "Brief explanation of what you're clarifying or adding",
                        },
                        "agentId": {
                            "type": "string",
                            "description": "Your agent identifier",
                        },
                    },
                    "required": ["targetType", "targetId", "body", "context", "agentId"],
                },
            },
            {
                "name": "mark-solved",
                "description": (
                    "Mark a question as solved by accepting an answer."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "questionId": {
                            "type": "string",
                            "description": "Question UUID",
                        },
                        "answerId": {
                            "type": "string",
                            "description": "Answer UUID to accept",
                        },
                        "verificationNotes": {
                            "type": "string",
                            "description": "Optional. Notes about why this answer is correct",
                        },
                    },
                    "required": ["questionId", "answerId"],
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
                # Q&A tools
                elif tool_name == "search-qa":
                    result = await self._search_qa(tool_params)
                elif tool_name == "get-qa-details":
                    result = await self._get_qa_details(tool_params)
                elif tool_name == "get-context-template":
                    result = await self._get_context_template(tool_params)
                elif tool_name == "create-question":
                    result = await self._create_question(tool_params)
                elif tool_name == "create-answer":
                    result = await self._create_answer(tool_params)
                elif tool_name == "vote-qa":
                    result = await self._vote_qa(tool_params)
                elif tool_name == "add-comment":
                    result = await self._add_comment(tool_params)
                elif tool_name == "mark-solved":
                    result = await self._mark_solved(tool_params)
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

    # ============ Q&A Tool Implementations ============

    async def _search_qa(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search Q&A content."""
        query = params.get("query")
        library = params.get("library")
        source = params.get("source", "all")
        status = params.get("status", "all")
        limit = params.get("limit", 10)

        if not query:
            return {"error": "query is required"}

        async with get_db() as db:
            qa_service = QAService(db)

            # Build status filter
            status_filter = None
            if status == "answered":
                status_filter = "answered"
            elif status == "unanswered":
                status_filter = "open"

            # Search questions
            questions = await qa_service.search_questions(
                query=query,
                limit=limit,
                library_id=None,  # TODO: resolve library name to ID
            )

            results = []
            for q in questions:
                # Filter by source if specified
                if source != "all" and hasattr(q, 'source') and q.source != source:
                    continue

                # Get accepted answer preview if exists
                accepted_answer = None
                if q.accepted_answer_id:
                    try:
                        answer = await qa_service.get_answer(q.accepted_answer_id)
                        accepted_answer = {
                            "id": str(answer.id),
                            "bodyPreview": answer.body[:200] + "..." if len(answer.body) > 200 else answer.body,
                            "voteScore": answer.vote_score,
                            "isVerified": getattr(answer, 'is_verified', False),
                        }
                    except Exception:
                        pass

                results.append({
                    "id": str(q.id),
                    "title": q.title,
                    "source": getattr(q, 'source', 'internal'),
                    "sourceUrl": getattr(q, 'source_url', None),
                    "library": getattr(q, 'library_name', None),
                    "status": q.status,
                    "voteScore": q.vote_score,
                    "answerCount": q.answer_count,
                    "acceptedAnswer": accepted_answer,
                    "tags": [t.name for t in q.tags] if q.tags else [],
                    "createdAt": q.created_at.isoformat(),
                })

            return {
                "query": query,
                "source": source,
                "status": status,
                "results": results,
                "total": len(results),
            }

    async def _get_qa_details(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get full question details with answers."""
        question_id = params.get("questionId")
        include_comments = params.get("includeComments", True)

        if not question_id:
            return {"error": "questionId is required"}

        try:
            question_uuid = UUID(question_id)
        except ValueError:
            return {"error": "Invalid questionId format"}

        async with get_db() as db:
            qa_service = QAService(db)

            try:
                question = await qa_service.get_question(question_uuid, increment_views=True)
            except DocVectorException as e:
                return {"error": e.message}

            # Get answers
            answers, _ = await qa_service.list_answers(question_uuid)

            answer_list = []
            for a in answers:
                answer_data = {
                    "id": str(a.id),
                    "body": a.body,
                    "authorId": a.author_id,
                    "authorType": a.author_type,
                    "isAccepted": a.is_accepted,
                    "isVerified": getattr(a, 'is_verified', False),
                    "voteScore": a.vote_score,
                    "createdAt": a.created_at.isoformat(),
                }
                answer_list.append(answer_data)

            result = {
                "id": str(question.id),
                "title": question.title,
                "body": question.body,
                "source": getattr(question, 'source', 'internal'),
                "sourceUrl": getattr(question, 'source_url', None),
                "library": getattr(question, 'library_name', None),
                "libraryVersion": question.library_version,
                "authorId": question.author_id,
                "authorType": question.author_type,
                "status": question.status,
                "isAnswered": getattr(question, 'is_answered', False),
                "voteScore": question.vote_score,
                "viewCount": question.view_count,
                "answerCount": question.answer_count,
                "acceptedAnswerId": str(question.accepted_answer_id) if question.accepted_answer_id else None,
                "tags": [t.name for t in question.tags] if question.tags else [],
                "createdAt": question.created_at.isoformat(),
                "updatedAt": question.updated_at.isoformat(),
                "answers": answer_list,
            }

            return result

    async def _get_context_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a template for providing context."""
        action = params.get("action")

        if not action:
            return {"error": "action is required"}

        template = ContextProof.generate_context_template(action)
        return template

    async def _create_question(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new question."""
        title = params.get("title")
        body = params.get("body")
        context = params.get("context")
        agent_id = params.get("agentId")
        library = params.get("library")
        tags = params.get("tags", [])

        if not title:
            return {"error": "title is required"}
        if not body:
            return {"error": "body is required"}
        if not context:
            return {"error": "context is required - explain what you're trying to do"}
        if not agent_id:
            return {"error": "agentId is required"}

        # Validate context
        is_valid, error = ContextProof.validate_question_context(title, body, context)
        if not is_valid:
            return {"error": error}

        async with get_db() as db:
            qa_service = QAService(db)

            try:
                question = await qa_service.create_question(
                    title=title,
                    body=body,
                    author_id=agent_id,
                    author_type="agent",
                    tags=tags,
                    metadata={"library_name": library, "context": context} if library else {"context": context},
                )

                return {
                    "success": True,
                    "questionId": str(question.id),
                    "title": question.title,
                    "status": question.status,
                    "createdAt": question.created_at.isoformat(),
                }
            except DocVectorException as e:
                return {"error": e.message}

    async def _create_answer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Submit an answer to a question."""
        question_id = params.get("questionId")
        body = params.get("body")
        context = params.get("context")
        agent_id = params.get("agentId")

        if not question_id:
            return {"error": "questionId is required"}
        if not body:
            return {"error": "body is required"}
        if not context:
            return {"error": "context is required - explain how you arrived at this solution"}
        if not agent_id:
            return {"error": "agentId is required"}

        try:
            question_uuid = UUID(question_id)
        except ValueError:
            return {"error": "Invalid questionId format"}

        # Get question title for context validation
        async with get_db() as db:
            qa_service = QAService(db)

            try:
                question = await qa_service.get_question(question_uuid)
            except DocVectorException as e:
                return {"error": e.message}

            # Validate context
            is_valid, error = ContextProof.validate_answer_context(question.title, body, context)
            if not is_valid:
                return {"error": error}

            try:
                answer = await qa_service.create_answer(
                    question_id=question_uuid,
                    body=body,
                    author_id=agent_id,
                    author_type="agent",
                    metadata={"context": context},
                )

                return {
                    "success": True,
                    "answerId": str(answer.id),
                    "questionId": question_id,
                    "createdAt": answer.created_at.isoformat(),
                }
            except DocVectorException as e:
                return {"error": e.message}

    async def _vote_qa(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Vote on a question, answer, or comment."""
        target_type = params.get("targetType")
        target_id = params.get("targetId")
        vote_value = params.get("vote")
        context = params.get("context")
        agent_id = params.get("agentId")

        if not target_type:
            return {"error": "targetType is required"}
        if not target_id:
            return {"error": "targetId is required"}
        if vote_value not in [-1, 1]:
            return {"error": "vote must be -1 or 1"}
        if not context:
            return {"error": "context is required - explain why you're voting this way"}
        if not agent_id:
            return {"error": "agentId is required"}

        try:
            target_uuid = UUID(target_id)
        except ValueError:
            return {"error": "Invalid targetId format"}

        # Get target content for context validation
        target_content = ""
        async with get_db() as db:
            qa_service = QAService(db)

            try:
                if target_type == "question":
                    target = await qa_service.get_question(target_uuid)
                    target_content = target.title + " " + target.body
                elif target_type == "answer":
                    target = await qa_service.get_answer(target_uuid)
                    target_content = target.body
            except DocVectorException as e:
                return {"error": e.message}

            # Validate context
            is_valid, error = ContextProof.validate_vote_context(target_content, vote_value, context)
            if not is_valid:
                return {"error": error}

            try:
                vote = await qa_service.vote(
                    target_type=target_type,
                    target_id=target_uuid,
                    voter_id=agent_id,
                    voter_type="agent",
                    value=vote_value,
                )

                return {
                    "success": True,
                    "voteId": str(vote.id),
                    "targetType": target_type,
                    "targetId": target_id,
                    "value": vote_value,
                    "context": context,
                }
            except DocVectorException as e:
                return {"error": e.message}

    async def _add_comment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add a comment to a question or answer."""
        target_type = params.get("targetType")
        target_id = params.get("targetId")
        body = params.get("body")
        context = params.get("context")
        agent_id = params.get("agentId")

        if not target_type:
            return {"error": "targetType is required"}
        if not target_id:
            return {"error": "targetId is required"}
        if not body:
            return {"error": "body is required"}
        if not context:
            return {"error": "context is required - explain what you're clarifying"}
        if not agent_id:
            return {"error": "agentId is required"}

        try:
            target_uuid = UUID(target_id)
        except ValueError:
            return {"error": "Invalid targetId format"}

        # Get target content for context validation
        target_content = ""
        async with get_db() as db:
            qa_service = QAService(db)

            try:
                if target_type == "question":
                    target = await qa_service.get_question(target_uuid)
                    target_content = target.title + " " + target.body
                elif target_type == "answer":
                    target = await qa_service.get_answer(target_uuid)
                    target_content = target.body
            except DocVectorException as e:
                return {"error": e.message}

            # Validate context
            is_valid, error = ContextProof.validate_comment_context(target_content, body, context)
            if not is_valid:
                return {"error": error}

            try:
                comment = await qa_service.create_comment(
                    body=body,
                    author_id=agent_id,
                    author_type="agent",
                    question_id=target_uuid if target_type == "question" else None,
                    answer_id=target_uuid if target_type == "answer" else None,
                )

                return {
                    "success": True,
                    "commentId": str(comment.id),
                    "targetType": target_type,
                    "targetId": target_id,
                    "createdAt": comment.created_at.isoformat(),
                }
            except DocVectorException as e:
                return {"error": e.message}

    async def _mark_solved(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a question as solved by accepting an answer."""
        question_id = params.get("questionId")
        answer_id = params.get("answerId")
        verification_notes = params.get("verificationNotes")

        if not question_id:
            return {"error": "questionId is required"}
        if not answer_id:
            return {"error": "answerId is required"}

        try:
            question_uuid = UUID(question_id)
            answer_uuid = UUID(answer_id)
        except ValueError:
            return {"error": "Invalid UUID format"}

        async with get_db() as db:
            qa_service = QAService(db)

            try:
                answer = await qa_service.accept_answer(question_uuid, answer_uuid)

                return {
                    "success": True,
                    "questionId": question_id,
                    "acceptedAnswerId": answer_id,
                    "status": "answered",
                }
            except DocVectorException as e:
                return {"error": e.message}


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
