"""Q&A service - Questions, Answers, Tags, Votes."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from docvector.core import DocVectorException, get_logger
from docvector.db.repositories import (
    AnswerRepository,
    CommentRepository,
    QuestionRepository,
    TagRepository,
    VoteRepository,
)
from docvector.models import Answer, Comment, Question, Tag, Vote

logger = get_logger(__name__)


class QAService:
    """Service for Q&A operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.question_repo = QuestionRepository(session)
        self.answer_repo = AnswerRepository(session)
        self.comment_repo = CommentRepository(session)
        self.tag_repo = TagRepository(session)
        self.vote_repo = VoteRepository(session)

    # ============ Tag Operations ============

    async def create_tag(
        self,
        name: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Tag:
        """Create a new tag."""
        logger.info("Creating tag", name=name)

        existing = await self.tag_repo.get_by_name(name)
        if existing:
            raise DocVectorException(
                code="TAG_EXISTS",
                message=f"Tag '{name}' already exists",
                details={"name": name},
            )

        tag = Tag(name=name, description=description, category=category)
        tag = await self.tag_repo.create(tag)
        await self.session.commit()

        logger.info("Tag created", tag_id=str(tag.id), name=name)
        return tag

    async def get_tag(self, tag_id: UUID) -> Tag:
        """Get tag by ID."""
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            raise DocVectorException(
                code="TAG_NOT_FOUND",
                message="Tag not found",
                details={"tag_id": str(tag_id)},
            )
        return tag

    async def list_tags(self, limit: int = 100, offset: int = 0) -> List[Tag]:
        """List all tags."""
        return await self.tag_repo.list_all(limit=limit, offset=offset)

    async def search_tags(self, query: str, limit: int = 20) -> List[Tag]:
        """Search tags by name."""
        return await self.tag_repo.search_by_name(query, limit=limit)

    # ============ Question Operations ============

    async def create_question(
        self,
        title: str,
        body: str,
        author_id: str,
        author_type: str = "agent",
        library_id: Optional[UUID] = None,
        library_name: Optional[str] = None,
        library_version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
        # External source fields
        source: str = "internal",
        source_id: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> Question:
        """Create a new question.

        Args:
            title: Question title
            body: Question body (markdown)
            author_id: Author identifier
            author_type: 'agent', 'user', or 'external'
            library_id: Associated library UUID
            library_name: Library name (denormalized for search)
            library_version: Library version
            tags: List of tag names
            metadata: Additional metadata dict
            source: Source platform ('internal', 'stackoverflow', 'github', 'discourse')
            source_id: Original ID from external source
            source_url: Link to original question
        """
        logger.info("Creating question", title=title[:50], author_id=author_id, source=source)

        question = Question(
            title=title,
            body=body,
            author_id=author_id,
            author_type=author_type,
            library_id=library_id,
            library_name=library_name,
            library_version=library_version,
            source=source,
            source_id=source_id,
            source_url=source_url,
            metadata_=metadata or {},
        )

        # Handle tags
        if tags:
            for tag_name in tags:
                tag = await self.tag_repo.get_or_create(tag_name)
                question.tags.append(tag)
                await self.tag_repo.increment_usage(tag.id)

        question = await self.question_repo.create(question)
        await self.session.commit()

        logger.info("Question created", question_id=str(question.id), title=title[:50], source=source)
        return question

    async def get_question(self, question_id: UUID, increment_views: bool = False) -> Question:
        """Get question by ID."""
        question = await self.question_repo.get_by_id(question_id)
        if not question:
            raise DocVectorException(
                code="QUESTION_NOT_FOUND",
                message="Question not found",
                details={"question_id": str(question_id)},
            )

        if increment_views:
            await self.question_repo.increment_view_count(question_id)
            await self.session.commit()

        return question

    async def list_questions(
        self,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> tuple[List[Question], int]:
        """List questions with pagination."""
        questions = await self.question_repo.list_all(
            limit=limit,
            offset=offset,
            library_id=library_id,
            status=status,
            author_id=author_id,
        )
        total = await self.question_repo.count(
            library_id=library_id,
            status=status,
            author_id=author_id,
        )
        return questions, total

    async def update_question(
        self,
        question_id: UUID,
        title: Optional[str] = None,
        body: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Question:
        """Update a question."""
        question = await self.get_question(question_id)

        if title:
            question.title = title
        if body:
            question.body = body
        if status:
            question.status = status

        if tags is not None:
            # Decrement old tags
            for tag in question.tags:
                await self.tag_repo.decrement_usage(tag.id)

            # Clear and add new tags
            question.tags.clear()
            for tag_name in tags:
                tag = await self.tag_repo.get_or_create(tag_name)
                question.tags.append(tag)
                await self.tag_repo.increment_usage(tag.id)

        question.updated_at = datetime.now(timezone.utc)
        question = await self.question_repo.update(question)
        await self.session.commit()

        logger.info("Question updated", question_id=str(question_id))
        return question

    async def delete_question(self, question_id: UUID) -> bool:
        """Delete a question."""
        question = await self.get_question(question_id)

        # Decrement tag usage
        for tag in question.tags:
            await self.tag_repo.decrement_usage(tag.id)

        success = await self.question_repo.delete(question_id)
        if success:
            await self.session.commit()

        logger.info("Question deleted", question_id=str(question_id))
        return success

    async def search_questions(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        library_id: Optional[UUID] = None,
    ) -> List[Question]:
        """Search questions by text."""
        return await self.question_repo.search_by_text(
            query=query,
            limit=limit,
            offset=offset,
            library_id=library_id,
        )

    # ============ Answer Operations ============

    async def create_answer(
        self,
        question_id: UUID,
        body: str,
        author_id: str,
        author_type: str = "agent",
        metadata: Optional[dict] = None,
        # External source fields
        source: str = "internal",
        source_id: Optional[str] = None,
        source_url: Optional[str] = None,
        is_accepted: bool = False,
    ) -> Answer:
        """Create a new answer.

        Args:
            question_id: Question UUID to answer
            body: Answer body (markdown)
            author_id: Author identifier
            author_type: 'agent', 'user', or 'external'
            metadata: Additional metadata dict
            source: Source platform ('internal', 'stackoverflow', 'github', 'discourse')
            source_id: Original ID from external source
            source_url: Link to original answer
            is_accepted: Whether this is the accepted answer (for imports)
        """
        # Verify question exists
        question = await self.get_question(question_id)

        logger.info("Creating answer", question_id=str(question_id), author_id=author_id, source=source)

        answer = Answer(
            question_id=question_id,
            body=body,
            author_id=author_id,
            author_type=author_type,
            source=source,
            source_id=source_id,
            source_url=source_url,
            is_accepted=is_accepted,
            metadata_=metadata or {},
        )

        answer = await self.answer_repo.create(answer)
        await self.question_repo.update_answer_count(question_id, 1)

        # If this is an accepted answer, update the question
        if is_accepted:
            await self.question_repo.set_accepted_answer(question_id, answer.id)

        await self.session.commit()

        logger.info("Answer created", answer_id=str(answer.id), question_id=str(question_id), source=source)
        return answer

    async def get_answer(self, answer_id: UUID) -> Answer:
        """Get answer by ID."""
        answer = await self.answer_repo.get_by_id(answer_id)
        if not answer:
            raise DocVectorException(
                code="ANSWER_NOT_FOUND",
                message="Answer not found",
                details={"answer_id": str(answer_id)},
            )
        return answer

    async def list_answers(
        self,
        question_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Answer], int]:
        """List answers for a question."""
        answers = await self.answer_repo.list_by_question(
            question_id=question_id,
            limit=limit,
            offset=offset,
        )
        total = await self.answer_repo.count_by_question(question_id)
        return answers, total

    async def update_answer(
        self,
        answer_id: UUID,
        body: Optional[str] = None,
    ) -> Answer:
        """Update an answer."""
        answer = await self.get_answer(answer_id)

        if body:
            answer.body = body

        answer.updated_at = datetime.now(timezone.utc)
        answer = await self.answer_repo.update(answer)
        await self.session.commit()

        logger.info("Answer updated", answer_id=str(answer_id))
        return answer

    async def delete_answer(self, answer_id: UUID) -> bool:
        """Delete an answer."""
        answer = await self.get_answer(answer_id)
        question_id = answer.question_id

        # If this was the accepted answer, clear it
        question = await self.get_question(question_id)
        if question.accepted_answer_id == answer_id:
            await self.question_repo.set_accepted_answer(question_id, None)

        success = await self.answer_repo.delete(answer_id)
        if success:
            await self.question_repo.update_answer_count(question_id, -1)
            await self.session.commit()

        logger.info("Answer deleted", answer_id=str(answer_id))
        return success

    async def accept_answer(self, question_id: UUID, answer_id: UUID) -> Answer:
        """Accept an answer as the solution."""
        question = await self.get_question(question_id)
        answer = await self.get_answer(answer_id)

        if answer.question_id != question_id:
            raise DocVectorException(
                code="ANSWER_NOT_FOR_QUESTION",
                message="Answer does not belong to this question",
                details={"question_id": str(question_id), "answer_id": str(answer_id)},
            )

        # Clear any previously accepted answer
        await self.answer_repo.clear_accepted_for_question(question_id)

        # Accept this answer
        await self.answer_repo.set_accepted(answer_id, True)
        await self.question_repo.set_accepted_answer(question_id, answer_id)
        await self.session.commit()

        # Refresh answer
        answer = await self.get_answer(answer_id)
        logger.info("Answer accepted", answer_id=str(answer_id), question_id=str(question_id))
        return answer

    async def unaccept_answer(self, question_id: UUID) -> None:
        """Remove accepted status from any answer."""
        question = await self.get_question(question_id)

        await self.answer_repo.clear_accepted_for_question(question_id)
        await self.question_repo.set_accepted_answer(question_id, None)
        await self.session.commit()

        logger.info("Answer unaccepted", question_id=str(question_id))

    # ============ Vote Operations ============

    async def vote(
        self,
        target_type: str,
        target_id: UUID,
        voter_id: str,
        voter_type: str,
        value: int,
    ) -> Vote:
        """Cast a vote on a question or answer."""
        # Validate target exists
        if target_type == "question":
            await self.get_question(target_id)
        elif target_type == "answer":
            await self.get_answer(target_id)
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
        if target_type == "question":
            question = await self.question_repo.get_by_id(target_id)
            if question:
                question.vote_score = new_score
                await self.question_repo.update(question)
        elif target_type == "answer":
            answer = await self.answer_repo.get_by_id(target_id)
            if answer:
                answer.vote_score = new_score
                await self.answer_repo.update(answer)

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
            if target_type == "question":
                question = await self.question_repo.get_by_id(target_id)
                if question:
                    question.vote_score = new_score
                    await self.question_repo.update(question)
            elif target_type == "answer":
                answer = await self.answer_repo.get_by_id(target_id)
                if answer:
                    answer.vote_score = new_score
                    await self.answer_repo.update(answer)
            elif target_type == "comment":
                await self.comment_repo.update_vote_score(target_id, new_score)

            await self.session.commit()
            logger.info("Vote removed", target_type=target_type, target_id=str(target_id))

        return success

    # ============ Comment Operations ============

    async def create_comment(
        self,
        body: str,
        author_id: str,
        author_type: str = "agent",
        question_id: Optional[UUID] = None,
        answer_id: Optional[UUID] = None,
        parent_comment_id: Optional[UUID] = None,
        source: str = "internal",
        source_id: Optional[str] = None,
    ) -> Comment:
        """Create a new comment on a question or answer."""
        # Validate that exactly one parent is specified
        parent_count = sum([
            question_id is not None,
            answer_id is not None,
            parent_comment_id is not None,
        ])
        if parent_count != 1:
            raise DocVectorException(
                code="INVALID_COMMENT_PARENT",
                message="Comment must have exactly one parent (question_id, answer_id, or parent_comment_id)",
                details={},
            )

        # Validate parent exists
        if question_id:
            await self.get_question(question_id)
        elif answer_id:
            await self.get_answer(answer_id)
        elif parent_comment_id:
            await self.get_comment(parent_comment_id)

        logger.info(
            "Creating comment",
            author_id=author_id,
            question_id=str(question_id) if question_id else None,
            answer_id=str(answer_id) if answer_id else None,
        )

        comment = Comment(
            body=body,
            author_id=author_id,
            author_type=author_type,
            question_id=question_id,
            answer_id=answer_id,
            parent_comment_id=parent_comment_id,
            source=source,
            source_id=source_id,
        )

        comment = await self.comment_repo.create(comment)
        await self.session.commit()

        logger.info("Comment created", comment_id=str(comment.id))
        return comment

    async def get_comment(self, comment_id: UUID) -> Comment:
        """Get comment by ID."""
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            raise DocVectorException(
                code="COMMENT_NOT_FOUND",
                message="Comment not found",
                details={"comment_id": str(comment_id)},
            )
        return comment

    async def list_question_comments(
        self,
        question_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[Comment], int]:
        """List comments for a question."""
        comments = await self.comment_repo.list_by_question(
            question_id=question_id,
            limit=limit,
            offset=offset,
        )
        total = await self.comment_repo.count_by_question(question_id)
        return comments, total

    async def list_answer_comments(
        self,
        answer_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[Comment], int]:
        """List comments for an answer."""
        comments = await self.comment_repo.list_by_answer(
            answer_id=answer_id,
            limit=limit,
            offset=offset,
        )
        total = await self.comment_repo.count_by_answer(answer_id)
        return comments, total

    async def delete_comment(self, comment_id: UUID) -> bool:
        """Delete a comment."""
        success = await self.comment_repo.delete(comment_id)
        if success:
            await self.session.commit()
            logger.info("Comment deleted", comment_id=str(comment_id))
        return success
