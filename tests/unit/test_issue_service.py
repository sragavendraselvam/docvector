"""Tests for Issue service."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from docvector.models import Issue, Solution, Vote
from docvector.services.issue_service import IssueService


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def issue_service(mock_session):
    """Create an IssueService with mocked session."""
    return IssueService(mock_session)


class TestIssueOperations:
    """Tests for issue operations."""

    @pytest.mark.asyncio
    async def test_create_issue(self, issue_service, mock_session):
        """Test creating a new issue."""
        issue_id = uuid4()

        with patch.object(issue_service.issue_repo, 'create', new_callable=AsyncMock) as mock_create:
            mock_issue = MagicMock(spec=Issue)
            mock_issue.id = issue_id
            mock_issue.title = "Connection timeout error"
            mock_issue.description = "Getting timeout when connecting to database..."
            mock_issue.status = "open"
            mock_issue.tags = []
            mock_create.return_value = mock_issue

            result = await issue_service.create_issue(
                title="Connection timeout error",
                description="Getting timeout when connecting to database...",
                author_id="agent-123",
                severity="major",
            )

            assert result.title == "Connection timeout error"
            assert result.status == "open"
            mock_create.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_issue_with_reproduction_details(self, issue_service, mock_session):
        """Test creating an issue with reproduction details."""
        issue_id = uuid4()

        with patch.object(issue_service.issue_repo, 'create', new_callable=AsyncMock) as mock_create:
            mock_issue = MagicMock(spec=Issue)
            mock_issue.id = issue_id
            mock_issue.title = "Memory leak in worker"
            mock_issue.description = "Memory keeps growing..."
            mock_issue.steps_to_reproduce = "1. Start worker\n2. Wait 1 hour"
            mock_issue.expected_behavior = "Memory should be stable"
            mock_issue.actual_behavior = "Memory grows 100MB/hour"
            mock_issue.code_snippet = "worker.start()"
            mock_issue.error_message = None
            mock_issue.tags = []
            mock_create.return_value = mock_issue

            result = await issue_service.create_issue(
                title="Memory leak in worker",
                description="Memory keeps growing...",
                author_id="agent-123",
                steps_to_reproduce="1. Start worker\n2. Wait 1 hour",
                expected_behavior="Memory should be stable",
                actual_behavior="Memory grows 100MB/hour",
                code_snippet="worker.start()",
            )

            assert result.steps_to_reproduce is not None
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_issue_not_found(self, issue_service):
        """Test getting a non-existent issue raises error."""
        issue_id = uuid4()

        with patch.object(issue_service.issue_repo, 'get_by_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            from docvector.core import DocVectorException
            with pytest.raises(DocVectorException) as exc_info:
                await issue_service.get_issue(issue_id)

            assert exc_info.value.code == "ISSUE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_list_issues_with_filters(self, issue_service):
        """Test listing issues with filters."""
        i1 = MagicMock(spec=Issue)
        i1.id = uuid4()
        i1.title = "Critical bug"
        i1.status = "open"
        i1.severity = "critical"
        i1.tags = []

        with patch.object(issue_service.issue_repo, 'list_all', new_callable=AsyncMock) as mock_list:
            with patch.object(issue_service.issue_repo, 'count', new_callable=AsyncMock) as mock_count:
                mock_list.return_value = [i1]
                mock_count.return_value = 1

                issues, total = await issue_service.list_issues(
                    limit=10,
                    offset=0,
                    status="open",
                    severity="critical",
                )

                assert len(issues) == 1
                assert total == 1
                mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_reproduction(self, issue_service, mock_session):
        """Test confirming issue reproduction."""
        issue_id = uuid4()

        mock_issue = MagicMock(spec=Issue)
        mock_issue.id = issue_id
        mock_issue.is_reproducible = True
        mock_issue.reproduction_count = 1
        mock_issue.tags = []

        with patch.object(issue_service.issue_repo, 'get_by_id', new_callable=AsyncMock) as mock_get:
            with patch.object(issue_service.issue_repo, 'increment_reproduction_count', new_callable=AsyncMock):
                mock_get.return_value = mock_issue

                result = await issue_service.confirm_reproduction(issue_id)

                assert result.is_reproducible is True


class TestSolutionOperations:
    """Tests for solution operations."""

    @pytest.mark.asyncio
    async def test_create_solution(self, issue_service, mock_session):
        """Test creating a new solution."""
        issue_id = uuid4()
        solution_id = uuid4()

        mock_issue = MagicMock(spec=Issue)
        mock_issue.id = issue_id
        mock_issue.tags = []

        with patch.object(issue_service.issue_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_i:
            with patch.object(issue_service.solution_repo, 'create', new_callable=AsyncMock) as mock_create:
                with patch.object(issue_service.issue_repo, 'update_solution_count', new_callable=AsyncMock):
                    mock_get_i.return_value = mock_issue

                    mock_solution = MagicMock(spec=Solution)
                    mock_solution.id = solution_id
                    mock_solution.issue_id = issue_id
                    mock_solution.description = "Here's the fix..."
                    mock_solution.code_snippet = "fix_code()"
                    mock_create.return_value = mock_solution

                    result = await issue_service.create_solution(
                        issue_id=issue_id,
                        description="Here's the fix...",
                        author_id="agent-456",
                        code_snippet="fix_code()",
                    )

                    assert result.issue_id == issue_id
                    mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_solution(self, issue_service, mock_session):
        """Test accepting a solution."""
        issue_id = uuid4()
        solution_id = uuid4()

        mock_issue = MagicMock(spec=Issue)
        mock_issue.id = issue_id
        mock_issue.tags = []

        mock_solution = MagicMock(spec=Solution)
        mock_solution.id = solution_id
        mock_solution.issue_id = issue_id
        mock_solution.is_accepted = True

        with patch.object(issue_service.issue_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_i:
            with patch.object(issue_service.solution_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_s:
                with patch.object(issue_service.solution_repo, 'clear_accepted_for_issue', new_callable=AsyncMock):
                    with patch.object(issue_service.solution_repo, 'set_accepted', new_callable=AsyncMock):
                        with patch.object(issue_service.issue_repo, 'set_accepted_solution', new_callable=AsyncMock):
                            mock_get_i.return_value = mock_issue
                            mock_get_s.return_value = mock_solution

                            result = await issue_service.accept_solution(issue_id, solution_id)

                            assert result.is_accepted is True

    @pytest.mark.asyncio
    async def test_solution_feedback_works(self, issue_service, mock_session):
        """Test recording positive feedback on a solution."""
        solution_id = uuid4()

        mock_solution = MagicMock(spec=Solution)
        mock_solution.id = solution_id
        mock_solution.works_count = 1
        mock_solution.doesnt_work_count = 0

        with patch.object(issue_service.solution_repo, 'get_by_id', new_callable=AsyncMock) as mock_get:
            with patch.object(issue_service.solution_repo, 'increment_works_count', new_callable=AsyncMock) as mock_inc:
                mock_get.return_value = mock_solution

                result = await issue_service.solution_feedback(solution_id, works=True)

                assert result.works_count == 1
                mock_inc.assert_called_once_with(solution_id)

    @pytest.mark.asyncio
    async def test_solution_feedback_doesnt_work(self, issue_service, mock_session):
        """Test recording negative feedback on a solution."""
        solution_id = uuid4()

        mock_solution = MagicMock(spec=Solution)
        mock_solution.id = solution_id
        mock_solution.works_count = 0
        mock_solution.doesnt_work_count = 1

        with patch.object(issue_service.solution_repo, 'get_by_id', new_callable=AsyncMock) as mock_get:
            with patch.object(issue_service.solution_repo, 'increment_doesnt_work_count', new_callable=AsyncMock) as mock_inc:
                mock_get.return_value = mock_solution

                result = await issue_service.solution_feedback(solution_id, works=False)

                assert result.doesnt_work_count == 1
                mock_inc.assert_called_once_with(solution_id)


class TestIssueVoteOperations:
    """Tests for vote operations on issues and solutions."""

    @pytest.mark.asyncio
    async def test_vote_on_issue(self, issue_service, mock_session):
        """Test voting on an issue."""
        issue_id = uuid4()
        vote_id = uuid4()

        mock_issue = MagicMock(spec=Issue)
        mock_issue.id = issue_id
        mock_issue.vote_score = 0
        mock_issue.tags = []

        mock_vote = MagicMock(spec=Vote)
        mock_vote.id = vote_id
        mock_vote.target_type = "issue"
        mock_vote.target_id = issue_id
        mock_vote.value = 1

        with patch.object(issue_service.issue_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_i:
            with patch.object(issue_service.vote_repo, 'upsert', new_callable=AsyncMock) as mock_upsert:
                with patch.object(issue_service.vote_repo, 'get_vote_score', new_callable=AsyncMock) as mock_score:
                    with patch.object(issue_service.issue_repo, 'update', new_callable=AsyncMock):
                        mock_get_i.return_value = mock_issue
                        mock_upsert.return_value = mock_vote
                        mock_score.return_value = 1

                        result = await issue_service.vote(
                            target_type="issue",
                            target_id=issue_id,
                            voter_id="agent-123",
                            voter_type="agent",
                            value=1,
                        )

                        assert result.value == 1

    @pytest.mark.asyncio
    async def test_vote_on_solution(self, issue_service, mock_session):
        """Test voting on a solution."""
        solution_id = uuid4()
        vote_id = uuid4()

        mock_solution = MagicMock(spec=Solution)
        mock_solution.id = solution_id
        mock_solution.vote_score = 0

        mock_vote = MagicMock(spec=Vote)
        mock_vote.id = vote_id
        mock_vote.target_type = "solution"
        mock_vote.target_id = solution_id
        mock_vote.value = -1

        with patch.object(issue_service.solution_repo, 'get_by_id', new_callable=AsyncMock) as mock_get_s:
            with patch.object(issue_service.vote_repo, 'upsert', new_callable=AsyncMock) as mock_upsert:
                with patch.object(issue_service.vote_repo, 'get_vote_score', new_callable=AsyncMock) as mock_score:
                    with patch.object(issue_service.solution_repo, 'update', new_callable=AsyncMock):
                        mock_get_s.return_value = mock_solution
                        mock_upsert.return_value = mock_vote
                        mock_score.return_value = -1

                        result = await issue_service.vote(
                            target_type="solution",
                            target_id=solution_id,
                            voter_id="agent-123",
                            voter_type="agent",
                            value=-1,
                        )

                        assert result.value == -1

    @pytest.mark.asyncio
    async def test_invalid_target_type_raises_error(self, issue_service):
        """Test that invalid target type raises error."""
        from docvector.core import DocVectorException
        with pytest.raises(DocVectorException) as exc_info:
            await issue_service.vote(
                target_type="invalid",
                target_id=uuid4(),
                voter_id="agent-123",
                voter_type="agent",
                value=1,
            )

        assert exc_info.value.code == "INVALID_TARGET_TYPE"
