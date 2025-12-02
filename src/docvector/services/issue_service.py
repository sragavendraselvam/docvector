"""Issue service - Issues and Solutions."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from docvector.core import DocVectorException, get_logger
from docvector.db.repositories import (
    IssueRepository,
    SolutionRepository,
    TagRepository,
    VoteRepository,
)
from docvector.models import Issue, Solution, Vote

logger = get_logger(__name__)


class IssueService:
    """Service for Issue operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.issue_repo = IssueRepository(session)
        self.solution_repo = SolutionRepository(session)
        self.tag_repo = TagRepository(session)
        self.vote_repo = VoteRepository(session)

    # ============ Issue Operations ============

    async def create_issue(
        self,
        title: str,
        description: str,
        author_id: str,
        author_type: str = "agent",
        library_id: Optional[UUID] = None,
        library_version: Optional[str] = None,
        steps_to_reproduce: Optional[str] = None,
        expected_behavior: Optional[str] = None,
        actual_behavior: Optional[str] = None,
        code_snippet: Optional[str] = None,
        error_message: Optional[str] = None,
        environment: Optional[dict] = None,
        severity: Optional[str] = None,
        external_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Issue:
        """Create a new issue."""
        logger.info("Creating issue", title=title[:50], author_id=author_id)

        issue = Issue(
            title=title,
            description=description,
            author_id=author_id,
            author_type=author_type,
            library_id=library_id,
            library_version=library_version,
            steps_to_reproduce=steps_to_reproduce,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            code_snippet=code_snippet,
            error_message=error_message,
            environment=environment,
            severity=severity,
            external_url=external_url,
            metadata_=metadata or {},
        )

        # Handle tags
        if tags:
            for tag_name in tags:
                tag = await self.tag_repo.get_or_create(tag_name)
                issue.tags.append(tag)
                await self.tag_repo.increment_usage(tag.id)

        issue = await self.issue_repo.create(issue)
        await self.session.commit()

        logger.info("Issue created", issue_id=str(issue.id), title=title[:50])
        return issue

    async def get_issue(self, issue_id: UUID, increment_views: bool = False) -> Issue:
        """Get issue by ID."""
        issue = await self.issue_repo.get_by_id(issue_id)
        if not issue:
            raise DocVectorException(
                code="ISSUE_NOT_FOUND",
                message="Issue not found",
                details={"issue_id": str(issue_id)},
            )

        if increment_views:
            await self.issue_repo.increment_view_count(issue_id)
            await self.session.commit()

        return issue

    async def list_issues(
        self,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> tuple[List[Issue], int]:
        """List issues with pagination."""
        issues = await self.issue_repo.list_all(
            limit=limit,
            offset=offset,
            library_id=library_id,
            status=status,
            severity=severity,
            author_id=author_id,
        )
        total = await self.issue_repo.count(
            library_id=library_id,
            status=status,
            severity=severity,
            author_id=author_id,
        )
        return issues, total

    async def update_issue(
        self,
        issue_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        steps_to_reproduce: Optional[str] = None,
        expected_behavior: Optional[str] = None,
        actual_behavior: Optional[str] = None,
        code_snippet: Optional[str] = None,
        error_message: Optional[str] = None,
        environment: Optional[dict] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Issue:
        """Update an issue."""
        issue = await self.get_issue(issue_id)

        if title:
            issue.title = title
        if description:
            issue.description = description
        if steps_to_reproduce is not None:
            issue.steps_to_reproduce = steps_to_reproduce
        if expected_behavior is not None:
            issue.expected_behavior = expected_behavior
        if actual_behavior is not None:
            issue.actual_behavior = actual_behavior
        if code_snippet is not None:
            issue.code_snippet = code_snippet
        if error_message is not None:
            issue.error_message = error_message
        if environment is not None:
            issue.environment = environment
        if status:
            issue.status = status
        if severity:
            issue.severity = severity

        if tags is not None:
            # Decrement old tags
            for tag in issue.tags:
                await self.tag_repo.decrement_usage(tag.id)

            # Clear and add new tags
            issue.tags.clear()
            for tag_name in tags:
                tag = await self.tag_repo.get_or_create(tag_name)
                issue.tags.append(tag)
                await self.tag_repo.increment_usage(tag.id)

        issue.updated_at = datetime.now(timezone.utc)
        issue = await self.issue_repo.update(issue)
        await self.session.commit()

        logger.info("Issue updated", issue_id=str(issue_id))
        return issue

    async def delete_issue(self, issue_id: UUID) -> bool:
        """Delete an issue."""
        issue = await self.get_issue(issue_id)

        # Decrement tag usage
        for tag in issue.tags:
            await self.tag_repo.decrement_usage(tag.id)

        success = await self.issue_repo.delete(issue_id)
        if success:
            await self.session.commit()

        logger.info("Issue deleted", issue_id=str(issue_id))
        return success

    async def confirm_reproduction(self, issue_id: UUID) -> Issue:
        """Confirm that an issue can be reproduced."""
        issue = await self.get_issue(issue_id)
        await self.issue_repo.increment_reproduction_count(issue_id)
        await self.session.commit()

        # Refresh issue
        issue = await self.get_issue(issue_id)
        logger.info("Issue reproduction confirmed", issue_id=str(issue_id))
        return issue

    async def search_issues(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Issue]:
        """Search issues by text."""
        return await self.issue_repo.search_by_text(
            query=query,
            limit=limit,
            offset=offset,
            library_id=library_id,
            status=status,
            severity=severity,
        )

    # ============ Solution Operations ============

    async def create_solution(
        self,
        issue_id: UUID,
        description: str,
        author_id: str,
        author_type: str = "agent",
        code_snippet: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Solution:
        """Create a new solution."""
        # Verify issue exists
        issue = await self.get_issue(issue_id)

        logger.info("Creating solution", issue_id=str(issue_id), author_id=author_id)

        solution = Solution(
            issue_id=issue_id,
            description=description,
            author_id=author_id,
            author_type=author_type,
            code_snippet=code_snippet,
            metadata_=metadata or {},
        )

        solution = await self.solution_repo.create(solution)
        await self.issue_repo.update_solution_count(issue_id, 1)
        await self.session.commit()

        logger.info("Solution created", solution_id=str(solution.id), issue_id=str(issue_id))
        return solution

    async def get_solution(self, solution_id: UUID) -> Solution:
        """Get solution by ID."""
        solution = await self.solution_repo.get_by_id(solution_id)
        if not solution:
            raise DocVectorException(
                code="SOLUTION_NOT_FOUND",
                message="Solution not found",
                details={"solution_id": str(solution_id)},
            )
        return solution

    async def list_solutions(
        self,
        issue_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Solution], int]:
        """List solutions for an issue."""
        solutions = await self.solution_repo.list_by_issue(
            issue_id=issue_id,
            limit=limit,
            offset=offset,
        )
        total = await self.solution_repo.count_by_issue(issue_id)
        return solutions, total

    async def update_solution(
        self,
        solution_id: UUID,
        description: Optional[str] = None,
        code_snippet: Optional[str] = None,
    ) -> Solution:
        """Update a solution."""
        solution = await self.get_solution(solution_id)

        if description:
            solution.description = description
        if code_snippet is not None:
            solution.code_snippet = code_snippet

        solution.updated_at = datetime.now(timezone.utc)
        solution = await self.solution_repo.update(solution)
        await self.session.commit()

        logger.info("Solution updated", solution_id=str(solution_id))
        return solution

    async def delete_solution(self, solution_id: UUID) -> bool:
        """Delete a solution."""
        solution = await self.get_solution(solution_id)
        issue_id = solution.issue_id

        # If this was the accepted solution, clear it
        issue = await self.get_issue(issue_id)
        if issue.accepted_solution_id == solution_id:
            await self.issue_repo.set_accepted_solution(issue_id, None)

        success = await self.solution_repo.delete(solution_id)
        if success:
            await self.issue_repo.update_solution_count(issue_id, -1)
            await self.session.commit()

        logger.info("Solution deleted", solution_id=str(solution_id))
        return success

    async def accept_solution(self, issue_id: UUID, solution_id: UUID) -> Solution:
        """Accept a solution as the fix."""
        issue = await self.get_issue(issue_id)
        solution = await self.get_solution(solution_id)

        if solution.issue_id != issue_id:
            raise DocVectorException(
                code="SOLUTION_NOT_FOR_ISSUE",
                message="Solution does not belong to this issue",
                details={"issue_id": str(issue_id), "solution_id": str(solution_id)},
            )

        # Clear any previously accepted solution
        await self.solution_repo.clear_accepted_for_issue(issue_id)

        # Accept this solution
        await self.solution_repo.set_accepted(solution_id, True)
        await self.issue_repo.set_accepted_solution(issue_id, solution_id)
        await self.session.commit()

        # Refresh solution
        solution = await self.get_solution(solution_id)
        logger.info("Solution accepted", solution_id=str(solution_id), issue_id=str(issue_id))
        return solution

    async def unaccept_solution(self, issue_id: UUID) -> None:
        """Remove accepted status from any solution."""
        issue = await self.get_issue(issue_id)

        await self.solution_repo.clear_accepted_for_issue(issue_id)
        await self.issue_repo.set_accepted_solution(issue_id, None)
        await self.session.commit()

        logger.info("Solution unaccepted", issue_id=str(issue_id))

    async def solution_feedback(
        self,
        solution_id: UUID,
        works: bool,
    ) -> Solution:
        """Record feedback on whether a solution worked."""
        solution = await self.get_solution(solution_id)

        if works:
            await self.solution_repo.increment_works_count(solution_id)
        else:
            await self.solution_repo.increment_doesnt_work_count(solution_id)

        await self.session.commit()

        # Refresh solution
        solution = await self.get_solution(solution_id)
        logger.info("Solution feedback recorded", solution_id=str(solution_id), works=works)
        return solution

    # ============ Vote Operations ============

    async def vote(
        self,
        target_type: str,
        target_id: UUID,
        voter_id: str,
        voter_type: str,
        value: int,
    ) -> Vote:
        """Cast a vote on an issue or solution."""
        # Validate target exists
        if target_type == "issue":
            await self.get_issue(target_id)
        elif target_type == "solution":
            await self.get_solution(target_id)
        else:
            raise DocVectorException(
                code="INVALID_TARGET_TYPE",
                message=f"Invalid target type: {target_type}",
                details={"target_type": target_type},
            )

        # Validate value
        if value not in (-1, 1):
            raise DocVectorException(
                code="INVALID_VOTE_VALUE",
                message="Vote value must be 1 (upvote) or -1 (downvote)",
                details={"value": value},
            )

        logger.info("Casting vote", target_type=target_type, target_id=str(target_id), value=value)

        vote = Vote(
            target_type=target_type,
            target_id=target_id,
            voter_id=voter_id,
            voter_type=voter_type,
            value=value,
        )

        vote = await self.vote_repo.upsert(vote)

        # Update vote score on target
        new_score = await self.vote_repo.get_vote_score(target_type, target_id)
        if target_type == "issue":
            issue = await self.issue_repo.get_by_id(target_id)
            if issue:
                issue.vote_score = new_score
                await self.issue_repo.update(issue)
        elif target_type == "solution":
            solution = await self.solution_repo.get_by_id(target_id)
            if solution:
                solution.vote_score = new_score
                await self.solution_repo.update(solution)

        await self.session.commit()

        logger.info("Vote cast", vote_id=str(vote.id), new_score=new_score)
        return vote

    async def remove_vote(
        self,
        target_type: str,
        target_id: UUID,
        voter_id: str,
    ) -> bool:
        """Remove a vote."""
        success = await self.vote_repo.delete(voter_id, target_type, target_id)

        if success:
            # Update vote score on target
            new_score = await self.vote_repo.get_vote_score(target_type, target_id)
            if target_type == "issue":
                issue = await self.issue_repo.get_by_id(target_id)
                if issue:
                    issue.vote_score = new_score
                    await self.issue_repo.update(issue)
            elif target_type == "solution":
                solution = await self.solution_repo.get_by_id(target_id)
                if solution:
                    solution.vote_score = new_score
                    await self.solution_repo.update(solution)

            await self.session.commit()
            logger.info("Vote removed", target_type=target_type, target_id=str(target_id))

        return success
