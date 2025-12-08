"""Tests for Q&A service."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from docvector.models import Answer, Question, Tag, Vote
from docvector.services.qa_service import QAService


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def qa_service(mock_session):
    """Create a QAService with mocked session."""
    return QAService(mock_session)


class TestTagOperations:
    """Tests for tag operations."""

    @pytest.mark.asyncio
    async def test_create_tag(self, qa_service, mock_session):
        """Test creating a new tag."""
        tag_id = uuid4()

        with patch.object(qa_service.tag_repo, 'get_by_name', new_callable=AsyncMock) as mock_get:
            with patch.object(qa_service.tag_repo, 'create', new_callable=AsyncMock) as mock_create:
                mock_get.return_value = None
                mock_tag = MagicMock(spec=Tag)
                mock_tag.id = tag_id
                mock_tag.name = "python"
                mock_create.return_value = mock_tag

                result = await qa_service.create_tag(name="python", description="Python language")

                assert result.name == "python"
                mock_create.assert_called_once()
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_tag_raises_error(self, qa_service):
        """Test that creating a duplicate tag raises an error."""
        with patch.object(qa_service.tag_repo, 'get_by_name', new_callable=AsyncMock) as mock_get:
            mock_existing = MagicMock(spec=Tag)
            mock_existing.name = "python"
            mock_get.return_value = mock_existing

            from docvector.core import DocVectorException
            with pytest.raises(DocVectorException) as exc_info:
                await qa_service.create_tag(name="python")

            assert exc_info.value.code == "TAG_EXISTS"


class TestQuestionOperations:
    """Tests for question operations."""

    @pytest.mark.asyncio
    async def test_create_question(self, qa_service, mock_session):
        """Test creating a new question."""
        question_id = uuid4()

        with patch.object(qa_service.question_repo, 'create', new_callable=AsyncMock) as mock_create:
            mock_question = MagicMock(spec=Question)
            mock_question.id = question_id
            mock_question.title = "How to use async/await?"
            mock_question.body = "I'm trying to understand async/await in Python..."
            mock_question.tags = []
            mock_create.return_value = mock_question

            result = await qa_service.create_question(
                title="How to use async/await?",
                body="I'm trying to understand async/await in Python...",
                author_id="agent-123",
            )

            assert result.title == "How to use async/await?"
            mock_create.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_question_with_tags(self, qa_service, mock_session):
        """Test creating a question with tags."""
        question_id = uuid4()
        tag_id = uuid4()

        with patch.object(qa_service.tag_repo, 'get_or_create', new_callable=AsyncMock) as mock_get_tag:
            with patch.object(qa_service.tag_repo, 'increment_usage', new_callable=AsyncMock):
                with patch.object(qa_service.question_repo, 'create', new_callable=AsyncMock) as mock_create:
                    mock_tag = MagicMock(spec=Tag)
                    mock_tag.id = tag_id
                    mock_tag.name = "async"
                    mock_get_tag.return_value = mock_tag

                    mock_question = MagicMock(spec=Question)
                    mock_question.id = question_id
                    mock_question.title = "Async question"
                    mock_question.body = "Question body here..."
                    mock_question.tags = [mock_tag]
                    mock_create.return_value = mock_question

                    result = await qa_service.create_question(
                        title="Async question",
                        body="Question body here...",
                        author_id="agent-123",
                        tags=["async"],
                    )

                    assert len(result.tags) == 1
                    mock_get_tag.assert_called_once_with("async")

    @pytest.mark.asyncio
    async def test_get_question_not_found(self, qa_service):
        """Test getting a non-existent question raises error."""
        question_id = uuid4()

        with patch.object(qa_service.question_repo, 'get_by_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            from docvector.core import DocVectorException
            with pytest.raises(DocVectorException) as exc_info:
                await qa_service.get_question(question_id)

            assert exc_info.value.code == "QUESTION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_list_questions(self, qa_service):
        """Test listing questions."""
        q1 = MagicMock(spec=Question)
        q1.id = uuid4()
        q1.title = "Question 1"
        q1.tags = []

        q2 = MagicMock(spec=Question)
        q2.id = uuid4()
        q2.title = "Question 2"
        q2.tags = []

        with patch.object(qa_service.question_repo, 'list_all', new_callable=AsyncMock) as mock_list:
            with patch.object(qa_service.question_repo, 'count', new_callable=AsyncMock) as mock_count:
                mock_list.return_value = [q1, q2]
                mock_count.return_value = 2

                questions, total = await qa_service.list_questions(limit=10, offset=0)

                assert len(questions) == 2
                assert total == 2


class TestAnswerOperations:
    """Tests for answer operations."""

    @pytest.mark.asyncio
    async def test_create_answer(self, qa_service, mock_session):
        """Test creating a new answer."""
        question_id = uuid4()
        answer_id = uuid4()

        mock_question = MagicMock(spec=Question)
        mock_question.id = question_id
        mock_question.tags = []

        with patch.object(qa_service.question_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_q:
            with patch.object(qa_service.answer_repo, 'create', new_callable=AsyncMock) as mock_create:
                with patch.object(qa_service.question_repo, 'update_answer_count', new_callable=AsyncMock):
                    mock_get_q.return_value = mock_question

                    mock_answer = MagicMock(spec=Answer)
                    mock_answer.id = answer_id
                    mock_answer.question_id = question_id
                    mock_answer.body = "Here's the solution..."
                    mock_create.return_value = mock_answer

                    result = await qa_service.create_answer(
                        question_id=question_id,
                        body="Here's the solution...",
                        author_id="agent-456",
                    )

                    assert result.question_id == question_id
                    mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_answer(self, qa_service, mock_session):
        """Test accepting an answer."""
        question_id = uuid4()
        answer_id = uuid4()

        mock_question = MagicMock(spec=Question)
        mock_question.id = question_id
        mock_question.tags = []

        mock_answer = MagicMock(spec=Answer)
        mock_answer.id = answer_id
        mock_answer.question_id = question_id
        mock_answer.is_accepted = True

        with patch.object(qa_service.question_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_q:
            with patch.object(qa_service.answer_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_a:
                with patch.object(qa_service.answer_repo, 'clear_accepted_for_question', new_callable=AsyncMock):
                    with patch.object(qa_service.answer_repo, 'set_accepted', new_callable=AsyncMock):
                        with patch.object(qa_service.question_repo, 'set_accepted_answer', new_callable=AsyncMock):
                            mock_get_q.return_value = mock_question
                            mock_get_a.return_value = mock_answer

                            result = await qa_service.accept_answer(question_id, answer_id)

                            assert result.is_accepted is True


class TestVoteOperations:
    """Tests for vote operations."""

    @pytest.mark.asyncio
    async def test_vote_on_question(self, qa_service, mock_session):
        """Test voting on a question."""
        question_id = uuid4()
        vote_id = uuid4()

        mock_question = MagicMock(spec=Question)
        mock_question.id = question_id
        mock_question.vote_score = 0
        mock_question.tags = []

        mock_vote = MagicMock(spec=Vote)
        mock_vote.id = vote_id
        mock_vote.target_type = "question"
        mock_vote.target_id = question_id
        mock_vote.value = 1

        with patch.object(qa_service.question_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_q:
            with patch.object(qa_service.vote_repo, 'upsert', new_callable=AsyncMock) as mock_upsert:
                with patch.object(qa_service.vote_repo, 'get_vote_score', new_callable=AsyncMock) as mock_score:
                    with patch.object(qa_service.question_repo, 'update', new_callable=AsyncMock):
                        mock_get_q.return_value = mock_question
                        mock_upsert.return_value = mock_vote
                        mock_score.return_value = 1

                        result = await qa_service.vote(
                            target_type="question",
                            target_id=question_id,
                            voter_id="agent-123",
                            voter_type="agent",
                            value=1,
                        )

                        assert result.value == 1
                        mock_upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_vote_value_raises_error(self, qa_service):
        """Test that invalid vote value raises error."""
        question_id = uuid4()

        mock_question = MagicMock(spec=Question)
        mock_question.id = question_id
        mock_question.tags = []

        with patch.object(qa_service.question_repo, 'get_by_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_question

            from docvector.core import DocVectorException
            with pytest.raises(DocVectorException) as exc_info:
                await qa_service.vote(
                    target_type="question",
                    target_id=question_id,
                    voter_id="agent-123",
                    voter_type="agent",
                    value=5,  # Invalid value
                )

            assert exc_info.value.code == "INVALID_VOTE_VALUE"
