"""GitHub Issues/Discussions indexer.

Imports issues and discussions from GitHub repositories as Q&A data.

Data Sources:
1. GitHub REST API: https://docs.github.com/en/rest/issues
2. GitHub GraphQL API: https://docs.github.com/en/graphql

Usage:
    # Import issues from a repository
    indexer = GitHubIndexer(qa_service, github_token="ghp_xxx")
    await indexer.import_issues("facebook/react", labels=["question", "bug"])

    # Import discussions (if enabled on repo)
    await indexer.import_discussions("vercel/next.js")
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import aiohttp

from docvector.core import get_logger
from docvector.services.qa_service import QAService

logger = get_logger(__name__)


class GitHubIndexer:
    """Import Q&A from GitHub Issues and Discussions."""

    REST_API_BASE = "https://api.github.com"
    GRAPHQL_API = "https://api.github.com/graphql"
    SOURCE = "github"

    def __init__(self, qa_service: QAService, github_token: Optional[str] = None):
        """Initialize indexer.

        Args:
            qa_service: QAService instance for creating questions/answers
            github_token: GitHub personal access token (required for higher rate limits)
        """
        self.qa_service = qa_service
        self.github_token = github_token
        self.stats = {
            "issues_imported": 0,
            "comments_imported": 0,
            "discussions_imported": 0,
            "errors": 0,
        }

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth if available."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DocVector-Indexer",
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    async def import_issues(
        self,
        repo: str,
        library_name: Optional[str] = None,
        labels: Optional[List[str]] = None,
        state: str = "closed",
        max_issues: int = 100,
        min_comments: int = 1,
        include_without_answers: bool = False,
    ) -> Dict:
        """Import issues from a GitHub repository.

        Args:
            repo: Repository in "owner/repo" format
            library_name: Library name (defaults to repo name)
            labels: Filter by labels (e.g., ["question", "answered"])
            state: Issue state filter ("open", "closed", "all")
            max_issues: Maximum number of issues to import
            min_comments: Minimum comments required (useful for filtering answered questions)
            include_without_answers: Include issues with no comments

        Returns:
            Stats dictionary
        """
        if library_name is None:
            library_name = repo.split("/")[-1]

        logger.info(
            "Starting GitHub issues import",
            repo=repo,
            library_name=library_name,
            labels=labels,
            state=state,
            max_issues=max_issues,
        )

        params = {
            "state": state,
            "sort": "comments",
            "direction": "desc",
            "per_page": min(100, max_issues),
        }

        if labels:
            params["labels"] = ",".join(labels)

        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
            page = 1
            imported = 0

            while imported < max_issues:
                params["page"] = page
                url = f"{self.REST_API_BASE}/repos/{repo}/issues"

                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            issues = await resp.json()

                            if not issues:
                                logger.info("No more issues to import", page=page)
                                break

                            for issue in issues:
                                # Skip pull requests (they have "pull_request" key)
                                if "pull_request" in issue:
                                    continue

                                # Filter by comments
                                if not include_without_answers and issue.get("comments", 0) < min_comments:
                                    continue

                                if imported >= max_issues:
                                    break

                                await self._import_issue(session, repo, issue, library_name)
                                imported += 1

                            page += 1
                            # Rate limiting
                            await asyncio.sleep(0.5)
                        elif resp.status == 403:
                            # Rate limited
                            reset_time = resp.headers.get("X-RateLimit-Reset")
                            logger.warning(
                                "Rate limited",
                                reset_time=reset_time,
                            )
                            self.stats["errors"] += 1
                            break
                        else:
                            logger.error("API request failed", status=resp.status, page=page)
                            self.stats["errors"] += 1
                            break

                except Exception as e:
                    logger.error("Error fetching issues", page=page, error=str(e))
                    self.stats["errors"] += 1
                    break

        logger.info("GitHub issues import complete", stats=self.stats)
        return self.stats

    async def _import_issue(
        self,
        session: aiohttp.ClientSession,
        repo: str,
        issue_data: Dict,
        library_name: str,
    ) -> None:
        """Import a single issue with its comments."""
        try:
            issue_number = issue_data["number"]
            title = issue_data.get("title", "")
            body = issue_data.get("body", "") or ""
            state = issue_data.get("state", "open")
            labels = [label["name"] for label in issue_data.get("labels", [])]
            created_at = issue_data.get("created_at", "")
            html_url = issue_data.get("html_url", f"https://github.com/{repo}/issues/{issue_number}")

            # Determine if this is a question based on labels
            question_labels = {"question", "help wanted", "support", "bug"}
            is_question = bool(set(labels) & question_labels) or True  # Default to treating as question

            # Check if closed as resolved
            is_answered = state == "closed" and issue_data.get("state_reason") != "not_planned"

            # Create as question
            question = await self.qa_service.create_question(
                title=title,
                body=body,
                author_id=f"gh_user_{issue_data.get('user', {}).get('login', 'unknown')}",
                author_type="external",
                library_name=library_name,
                tags=labels[:5],  # Limit to 5 tags
                source=self.SOURCE,
                source_id=f"{repo}#{issue_number}",
                source_url=html_url,
                metadata={
                    "repo": repo,
                    "issue_number": issue_number,
                    "state": state,
                    "created_at": created_at,
                    "is_question": is_question,
                    "reactions": issue_data.get("reactions", {}).get("total_count", 0),
                },
            )

            self.stats["issues_imported"] += 1
            logger.debug("Imported issue", repo=repo, number=issue_number, title=title[:50])

            # Import comments as answers
            if issue_data.get("comments", 0) > 0:
                await self._import_issue_comments(session, repo, issue_number, question.id)

        except Exception as e:
            logger.error(
                "Error importing issue",
                repo=repo,
                issue_number=issue_data.get("number"),
                error=str(e),
            )
            self.stats["errors"] += 1

    async def _import_issue_comments(
        self,
        session: aiohttp.ClientSession,
        repo: str,
        issue_number: int,
        question_uuid: UUID,
    ) -> None:
        """Import comments for an issue as answers."""
        url = f"{self.REST_API_BASE}/repos/{repo}/issues/{issue_number}/comments"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    comments = await resp.json()

                    for idx, comment in enumerate(comments):
                        comment_id = comment["id"]
                        body = comment.get("body", "") or ""
                        created_at = comment.get("created_at", "")
                        html_url = comment.get("html_url", "")

                        # First substantial comment might be the "answer"
                        # Later comments are regular comments
                        is_answer = idx == 0 and len(body) > 100

                        if is_answer:
                            await self.qa_service.create_answer(
                                question_id=question_uuid,
                                body=body,
                                author_id=f"gh_user_{comment.get('user', {}).get('login', 'unknown')}",
                                author_type="external",
                                source=self.SOURCE,
                                source_id=str(comment_id),
                                source_url=html_url,
                                is_accepted=False,  # GitHub doesn't have accepted answers
                                metadata={
                                    "created_at": created_at,
                                    "reactions": comment.get("reactions", {}).get("total_count", 0),
                                },
                            )
                        else:
                            # Import as comment
                            await self.qa_service.create_comment(
                                body=body,
                                author_id=f"gh_user_{comment.get('user', {}).get('login', 'unknown')}",
                                author_type="external",
                                question_id=question_uuid,
                                source=self.SOURCE,
                                source_id=str(comment_id),
                            )

                        self.stats["comments_imported"] += 1

        except Exception as e:
            logger.error(
                "Error importing comments",
                repo=repo,
                issue_number=issue_number,
                error=str(e),
            )
            self.stats["errors"] += 1

    async def import_discussions(
        self,
        repo: str,
        library_name: Optional[str] = None,
        category: Optional[str] = None,
        max_discussions: int = 100,
        only_answered: bool = True,
    ) -> Dict:
        """Import discussions from a GitHub repository using GraphQL API.

        Requires a repository with Discussions enabled.

        Args:
            repo: Repository in "owner/repo" format
            library_name: Library name (defaults to repo name)
            category: Filter by discussion category (e.g., "Q&A", "Help")
            max_discussions: Maximum discussions to import
            only_answered: Only import discussions marked as answered

        Returns:
            Stats dictionary
        """
        if not self.github_token:
            logger.error("GitHub token required for GraphQL API")
            return self.stats

        if library_name is None:
            library_name = repo.split("/")[-1]

        owner, repo_name = repo.split("/")

        logger.info(
            "Starting GitHub discussions import",
            repo=repo,
            library_name=library_name,
            category=category,
            max_discussions=max_discussions,
        )

        # GraphQL query for discussions
        query = """
        query($owner: String!, $repo: String!, $first: Int!, $after: String, $answered: Boolean) {
            repository(owner: $owner, name: $repo) {
                discussions(first: $first, after: $after, answered: $answered, orderBy: {field: CREATED_AT, direction: DESC}) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        id
                        number
                        title
                        body
                        url
                        createdAt
                        isAnswered
                        answer {
                            id
                            body
                            url
                            createdAt
                            author {
                                login
                            }
                        }
                        author {
                            login
                        }
                        category {
                            name
                        }
                        labels(first: 5) {
                            nodes {
                                name
                            }
                        }
                        comments(first: 10) {
                            nodes {
                                id
                                body
                                url
                                createdAt
                                author {
                                    login
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Content-Type": "application/json",
        }

        variables = {
            "owner": owner,
            "repo": repo_name,
            "first": min(50, max_discussions),
            "after": None,
            "answered": only_answered if only_answered else None,
        }

        async with aiohttp.ClientSession() as session:
            imported = 0

            while imported < max_discussions:
                try:
                    async with session.post(
                        self.GRAPHQL_API,
                        json={"query": query, "variables": variables},
                        headers=headers,
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()

                            if "errors" in result:
                                logger.error("GraphQL errors", errors=result["errors"])
                                self.stats["errors"] += 1
                                break

                            discussions_data = result.get("data", {}).get("repository", {}).get("discussions", {})
                            discussions = discussions_data.get("nodes", [])
                            page_info = discussions_data.get("pageInfo", {})

                            if not discussions:
                                break

                            for disc in discussions:
                                # Filter by category if specified
                                disc_category = disc.get("category", {}).get("name", "")
                                if category and disc_category.lower() != category.lower():
                                    continue

                                if imported >= max_discussions:
                                    break

                                await self._import_discussion(disc, repo, library_name)
                                imported += 1

                            if not page_info.get("hasNextPage"):
                                break

                            variables["after"] = page_info.get("endCursor")
                            await asyncio.sleep(0.5)
                        else:
                            logger.error("GraphQL request failed", status=resp.status)
                            self.stats["errors"] += 1
                            break

                except Exception as e:
                    logger.error("Error fetching discussions", error=str(e))
                    self.stats["errors"] += 1
                    break

        logger.info("GitHub discussions import complete", stats=self.stats)
        return self.stats

    async def _import_discussion(
        self,
        disc_data: Dict,
        repo: str,
        library_name: str,
    ) -> None:
        """Import a single discussion with its answer and comments."""
        try:
            disc_number = disc_data["number"]
            title = disc_data.get("title", "")
            body = disc_data.get("body", "") or ""
            url = disc_data.get("url", "")
            created_at = disc_data.get("createdAt", "")
            is_answered = disc_data.get("isAnswered", False)
            category = disc_data.get("category", {}).get("name", "")
            labels = [label["name"] for label in disc_data.get("labels", {}).get("nodes", [])]

            # Create question
            question = await self.qa_service.create_question(
                title=title,
                body=body,
                author_id=f"gh_user_{disc_data.get('author', {}).get('login', 'unknown')}",
                author_type="external",
                library_name=library_name,
                tags=labels + [category] if category else labels,
                source=self.SOURCE,
                source_id=f"{repo}/discussions#{disc_number}",
                source_url=url,
                metadata={
                    "repo": repo,
                    "discussion_number": disc_number,
                    "category": category,
                    "created_at": created_at,
                    "is_answered": is_answered,
                },
            )

            self.stats["discussions_imported"] += 1
            logger.debug("Imported discussion", repo=repo, number=disc_number, title=title[:50])

            # Import the accepted answer if exists
            answer_data = disc_data.get("answer")
            if answer_data:
                await self.qa_service.create_answer(
                    question_id=question.id,
                    body=answer_data.get("body", ""),
                    author_id=f"gh_user_{answer_data.get('author', {}).get('login', 'unknown')}",
                    author_type="external",
                    source=self.SOURCE,
                    source_id=answer_data.get("id", ""),
                    source_url=answer_data.get("url", ""),
                    is_accepted=True,
                    metadata={
                        "created_at": answer_data.get("createdAt", ""),
                    },
                )
                self.stats["comments_imported"] += 1

            # Import other comments
            for comment in disc_data.get("comments", {}).get("nodes", []):
                # Skip if this is the accepted answer
                if answer_data and comment.get("id") == answer_data.get("id"):
                    continue

                await self.qa_service.create_comment(
                    body=comment.get("body", ""),
                    author_id=f"gh_user_{comment.get('author', {}).get('login', 'unknown')}",
                    author_type="external",
                    question_id=question.id,
                    source=self.SOURCE,
                    source_id=comment.get("id", ""),
                )
                self.stats["comments_imported"] += 1

        except Exception as e:
            logger.error(
                "Error importing discussion",
                repo=repo,
                discussion_number=disc_data.get("number"),
                error=str(e),
            )
            self.stats["errors"] += 1
