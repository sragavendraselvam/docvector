"""Q&A repositories - Question, Answer, Comment, Tag, Vote."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from docvector.models import Answer, Comment, Question, Tag, Vote, question_tags


class TagRepository:
    """Repository for Tag model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tag: Tag) -> Tag:
        """Create a new tag."""
        self.session.add(tag)
        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def get_by_id(self, tag_id: UUID) -> Optional[Tag]:
        """Get tag by ID."""
        result = await self.session.execute(select(Tag).where(Tag.id == tag_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Tag]:
        """Get tag by name."""
        result = await self.session.execute(select(Tag).where(Tag.name == name))
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str, category: Optional[str] = None) -> Tag:
        """Get existing tag or create new one."""
        tag = await self.get_by_name(name)
        if tag:
            return tag
        tag = Tag(name=name, category=category)
        return await self.create(tag)

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Tag]:
        """List all tags ordered by usage."""
        result = await self.session.execute(
            select(Tag).order_by(Tag.usage_count.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def search_by_name(self, query: str, limit: int = 20) -> List[Tag]:
        """Search tags by name prefix."""
        result = await self.session.execute(
            select(Tag)
            .where(Tag.name.ilike(f"{query}%"))
            .order_by(Tag.usage_count.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_usage(self, tag_id: UUID) -> None:
        """Increment tag usage count."""
        await self.session.execute(
            update(Tag).where(Tag.id == tag_id).values(usage_count=Tag.usage_count + 1)
        )

    async def decrement_usage(self, tag_id: UUID) -> None:
        """Decrement tag usage count."""
        await self.session.execute(
            update(Tag)
            .where(Tag.id == tag_id)
            .values(usage_count=func.greatest(Tag.usage_count - 1, 0))
        )


class QuestionRepository:
    """Repository for Question model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, question: Question) -> Question:
        """Create a new question."""
        self.session.add(question)
        await self.session.flush()
        await self.session.refresh(question)
        return question

    async def get_by_id(self, question_id: UUID) -> Optional[Question]:
        """Get question by ID with tags loaded."""
        result = await self.session.execute(
            select(Question)
            .options(selectinload(Question.tags))
            .where(Question.id == question_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> List[Question]:
        """List questions with optional filters."""
        query = select(Question).options(selectinload(Question.tags))

        conditions = []
        if library_id:
            conditions.append(Question.library_id == library_id)
        if status:
            conditions.append(Question.status == status)
        if author_id:
            conditions.append(Question.author_id == author_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Question.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> int:
        """Count questions with optional filters."""
        query = select(func.count(Question.id))

        conditions = []
        if library_id:
            conditions.append(Question.library_id == library_id)
        if status:
            conditions.append(Question.status == status)
        if author_id:
            conditions.append(Question.author_id == author_id)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def update(self, question: Question) -> Question:
        """Update question."""
        await self.session.flush()
        await self.session.refresh(question)
        return question

    async def delete(self, question_id: UUID) -> bool:
        """Delete question."""
        question = await self.get_by_id(question_id)
        if question:
            await self.session.delete(question)
            await self.session.flush()
            return True
        return False

    async def increment_view_count(self, question_id: UUID) -> None:
        """Increment view count."""
        await self.session.execute(
            update(Question)
            .where(Question.id == question_id)
            .values(view_count=Question.view_count + 1)
        )

    async def update_answer_count(self, question_id: UUID, delta: int) -> None:
        """Update answer count."""
        await self.session.execute(
            update(Question)
            .where(Question.id == question_id)
            .values(answer_count=Question.answer_count + delta)
        )

    async def set_accepted_answer(self, question_id: UUID, answer_id: Optional[UUID]) -> None:
        """Set accepted answer and update status."""
        status = "answered" if answer_id else "open"
        await self.session.execute(
            update(Question)
            .where(Question.id == question_id)
            .values(accepted_answer_id=answer_id, status=status)
        )

    async def search_by_text(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
    ) -> List[Question]:
        """Simple text search on title and body."""
        search_query = select(Question).options(selectinload(Question.tags))

        conditions = [
            or_(
                Question.title.ilike(f"%{query}%"),
                Question.body.ilike(f"%{query}%"),
            )
        ]

        if library_id:
            conditions.append(Question.library_id == library_id)

        search_query = (
            search_query.where(and_(*conditions))
            .order_by(Question.vote_score.desc(), Question.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(search_query)
        return list(result.scalars().all())


class AnswerRepository:
    """Repository for Answer model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, answer: Answer) -> Answer:
        """Create a new answer."""
        self.session.add(answer)
        await self.session.flush()
        await self.session.refresh(answer)
        return answer

    async def get_by_id(self, answer_id: UUID) -> Optional[Answer]:
        """Get answer by ID."""
        result = await self.session.execute(select(Answer).where(Answer.id == answer_id))
        return result.scalar_one_or_none()

    async def list_by_question(
        self,
        question_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Answer]:
        """List answers for a question."""
        result = await self.session.execute(
            select(Answer)
            .where(Answer.question_id == question_id)
            .order_by(Answer.is_accepted.desc(), Answer.vote_score.desc(), Answer.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_question(self, question_id: UUID) -> int:
        """Count answers for a question."""
        result = await self.session.execute(
            select(func.count(Answer.id)).where(Answer.question_id == question_id)
        )
        return result.scalar() or 0

    async def update(self, answer: Answer) -> Answer:
        """Update answer."""
        await self.session.flush()
        await self.session.refresh(answer)
        return answer

    async def delete(self, answer_id: UUID) -> bool:
        """Delete answer."""
        answer = await self.get_by_id(answer_id)
        if answer:
            await self.session.delete(answer)
            await self.session.flush()
            return True
        return False

    async def set_accepted(self, answer_id: UUID, is_accepted: bool) -> None:
        """Set answer as accepted/not accepted."""
        await self.session.execute(
            update(Answer).where(Answer.id == answer_id).values(is_accepted=is_accepted)
        )

    async def clear_accepted_for_question(self, question_id: UUID) -> None:
        """Clear accepted status for all answers of a question."""
        await self.session.execute(
            update(Answer)
            .where(Answer.question_id == question_id)
            .values(is_accepted=False)
        )


class VoteRepository:
    """Repository for Vote model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, vote: Vote) -> Vote:
        """Create a new vote."""
        self.session.add(vote)
        await self.session.flush()
        await self.session.refresh(vote)
        return vote

    async def get_by_voter_and_target(
        self,
        voter_id: str,
        target_type: str,
        target_id: UUID,
    ) -> Optional[Vote]:
        """Get vote by voter and target."""
        result = await self.session.execute(
            select(Vote).where(
                and_(
                    Vote.voter_id == voter_id,
                    Vote.target_type == target_type,
                    Vote.target_id == target_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, vote: Vote) -> Vote:
        """Create or update a vote."""
        existing = await self.get_by_voter_and_target(
            vote.voter_id, vote.target_type, vote.target_id
        )
        if existing:
            existing.value = vote.value
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(vote)

    async def delete(
        self,
        voter_id: str,
        target_type: str,
        target_id: UUID,
    ) -> bool:
        """Delete a vote."""
        vote = await self.get_by_voter_and_target(voter_id, target_type, target_id)
        if vote:
            await self.session.delete(vote)
            await self.session.flush()
            return True
        return False

    async def get_vote_score(self, target_type: str, target_id: UUID) -> int:
        """Calculate total vote score for a target."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Vote.value), 0)).where(
                and_(Vote.target_type == target_type, Vote.target_id == target_id)
            )
        )
        return result.scalar() or 0

    async def list_by_target(
        self,
        target_type: str,
        target_id: UUID,
    ) -> List[Vote]:
        """List all votes for a target."""
        result = await self.session.execute(
            select(Vote).where(
                and_(Vote.target_type == target_type, Vote.target_id == target_id)
            )
        )
        return list(result.scalars().all())


class CommentRepository:
    """Repository for Comment model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, comment: Comment) -> Comment:
        """Create a new comment."""
        self.session.add(comment)
        await self.session.flush()
        await self.session.refresh(comment)
        return comment

    async def get_by_id(self, comment_id: UUID) -> Optional[Comment]:
        """Get comment by ID."""
        result = await self.session.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def list_by_question(
        self,
        question_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Comment]:
        """List comments for a question."""
        result = await self.session.execute(
            select(Comment)
            .where(Comment.question_id == question_id)
            .order_by(Comment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_answer(
        self,
        answer_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Comment]:
        """List comments for an answer."""
        result = await self.session.execute(
            select(Comment)
            .where(Comment.answer_id == answer_id)
            .order_by(Comment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_replies(
        self,
        parent_comment_id: UUID,
        limit: int = 50,
    ) -> List[Comment]:
        """List replies to a comment."""
        result = await self.session.execute(
            select(Comment)
            .where(Comment.parent_comment_id == parent_comment_id)
            .order_by(Comment.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_question(self, question_id: UUID) -> int:
        """Count comments for a question."""
        result = await self.session.execute(
            select(func.count(Comment.id)).where(Comment.question_id == question_id)
        )
        return result.scalar() or 0

    async def count_by_answer(self, answer_id: UUID) -> int:
        """Count comments for an answer."""
        result = await self.session.execute(
            select(func.count(Comment.id)).where(Comment.answer_id == answer_id)
        )
        return result.scalar() or 0

    async def delete(self, comment_id: UUID) -> bool:
        """Delete a comment."""
        comment = await self.get_by_id(comment_id)
        if comment:
            await self.session.delete(comment)
            await self.session.flush()
            return True
        return False

    async def update_vote_score(self, comment_id: UUID, score: int) -> None:
        """Update comment vote score."""
        await self.session.execute(
            update(Comment).where(Comment.id == comment_id).values(vote_score=score)
        )
