"""Issue repositories - Issue and Solution."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from docvector.models import Issue, Solution, issue_tags


class IssueRepository:
    """Repository for Issue model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, issue: Issue) -> Issue:
        """Create a new issue."""
        self.session.add(issue)
        await self.session.flush()
        await self.session.refresh(issue)
        return issue

    async def get_by_id(self, issue_id: UUID) -> Optional[Issue]:
        """Get issue by ID with tags loaded."""
        result = await self.session.execute(
            select(Issue).options(selectinload(Issue.tags)).where(Issue.id == issue_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> List[Issue]:
        """List issues with optional filters."""
        query = select(Issue).options(selectinload(Issue.tags))

        conditions = []
        if library_id:
            conditions.append(Issue.library_id == library_id)
        if status:
            conditions.append(Issue.status == status)
        if severity:
            conditions.append(Issue.severity == severity)
        if author_id:
            conditions.append(Issue.author_id == author_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Issue.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> int:
        """Count issues with optional filters."""
        query = select(func.count(Issue.id))

        conditions = []
        if library_id:
            conditions.append(Issue.library_id == library_id)
        if status:
            conditions.append(Issue.status == status)
        if severity:
            conditions.append(Issue.severity == severity)
        if author_id:
            conditions.append(Issue.author_id == author_id)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def update(self, issue: Issue) -> Issue:
        """Update issue."""
        await self.session.flush()
        await self.session.refresh(issue)
        return issue

    async def delete(self, issue_id: UUID) -> bool:
        """Delete issue."""
        issue = await self.get_by_id(issue_id)
        if issue:
            await self.session.delete(issue)
            await self.session.flush()
            return True
        return False

    async def increment_view_count(self, issue_id: UUID) -> None:
        """Increment view count."""
        await self.session.execute(
            update(Issue).where(Issue.id == issue_id).values(view_count=Issue.view_count + 1)
        )

    async def update_solution_count(self, issue_id: UUID, delta: int) -> None:
        """Update solution count."""
        await self.session.execute(
            update(Issue)
            .where(Issue.id == issue_id)
            .values(solution_count=Issue.solution_count + delta)
        )

    async def set_accepted_solution(self, issue_id: UUID, solution_id: Optional[UUID]) -> None:
        """Set accepted solution and update status."""
        status = "resolved" if solution_id else "open"
        await self.session.execute(
            update(Issue)
            .where(Issue.id == issue_id)
            .values(accepted_solution_id=solution_id, status=status)
        )

    async def increment_reproduction_count(self, issue_id: UUID) -> None:
        """Increment reproduction count (someone else reproduced this issue)."""
        await self.session.execute(
            update(Issue)
            .where(Issue.id == issue_id)
            .values(
                reproduction_count=Issue.reproduction_count + 1,
                is_reproducible=True,
            )
        )

    async def search_by_text(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Issue]:
        """Simple text search on title, description, and error message."""
        search_query = select(Issue).options(selectinload(Issue.tags))

        conditions = [
            or_(
                Issue.title.ilike(f"%{query}%"),
                Issue.description.ilike(f"%{query}%"),
                Issue.error_message.ilike(f"%{query}%"),
            )
        ]

        if library_id:
            conditions.append(Issue.library_id == library_id)
        if status:
            conditions.append(Issue.status == status)
        if severity:
            conditions.append(Issue.severity == severity)

        search_query = (
            search_query.where(and_(*conditions))
            .order_by(Issue.vote_score.desc(), Issue.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(search_query)
        return list(result.scalars().all())


class SolutionRepository:
    """Repository for Solution model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, solution: Solution) -> Solution:
        """Create a new solution."""
        self.session.add(solution)
        await self.session.flush()
        await self.session.refresh(solution)
        return solution

    async def get_by_id(self, solution_id: UUID) -> Optional[Solution]:
        """Get solution by ID."""
        result = await self.session.execute(
            select(Solution).where(Solution.id == solution_id)
        )
        return result.scalar_one_or_none()

    async def list_by_issue(
        self,
        issue_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Solution]:
        """List solutions for an issue."""
        result = await self.session.execute(
            select(Solution)
            .where(Solution.issue_id == issue_id)
            .order_by(
                Solution.is_accepted.desc(),
                Solution.vote_score.desc(),
                Solution.works_count.desc(),
                Solution.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_issue(self, issue_id: UUID) -> int:
        """Count solutions for an issue."""
        result = await self.session.execute(
            select(func.count(Solution.id)).where(Solution.issue_id == issue_id)
        )
        return result.scalar() or 0

    async def update(self, solution: Solution) -> Solution:
        """Update solution."""
        await self.session.flush()
        await self.session.refresh(solution)
        return solution

    async def delete(self, solution_id: UUID) -> bool:
        """Delete solution."""
        solution = await self.get_by_id(solution_id)
        if solution:
            await self.session.delete(solution)
            await self.session.flush()
            return True
        return False

    async def set_accepted(self, solution_id: UUID, is_accepted: bool) -> None:
        """Set solution as accepted/not accepted."""
        await self.session.execute(
            update(Solution).where(Solution.id == solution_id).values(is_accepted=is_accepted)
        )

    async def clear_accepted_for_issue(self, issue_id: UUID) -> None:
        """Clear accepted status for all solutions of an issue."""
        await self.session.execute(
            update(Solution).where(Solution.issue_id == issue_id).values(is_accepted=False)
        )

    async def increment_works_count(self, solution_id: UUID) -> None:
        """Increment 'this worked for me' count."""
        await self.session.execute(
            update(Solution)
            .where(Solution.id == solution_id)
            .values(works_count=Solution.works_count + 1)
        )

    async def increment_doesnt_work_count(self, solution_id: UUID) -> None:
        """Increment 'this didn't work for me' count."""
        await self.session.execute(
            update(Solution)
            .where(Solution.id == solution_id)
            .values(doesnt_work_count=Solution.doesnt_work_count + 1)
        )
