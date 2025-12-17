"""Issue API routes - Issues and Solutions."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from docvector.api.dependencies import get_session
from docvector.api.schemas import (
    IssueCreate,
    IssueListResponse,
    IssueResponse,
    IssueUpdate,
    SolutionCreate,
    SolutionFeedback,
    SolutionListResponse,
    SolutionResponse,
    SolutionUpdate,
    VoteCreate,
    VoteResponse,
)
from docvector.core import DocVectorException, get_logger
from docvector.services import IssueService

logger = get_logger(__name__)

router = APIRouter()


# ============ Issue Routes ============


@router.post("", response_model=IssueResponse, status_code=201)
async def create_issue(
    request: IssueCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new issue."""
    try:
        service = IssueService(session)
        issue = await service.create_issue(
            title=request.title,
            description=request.description,
            author_id=request.author_id,
            author_type=request.author_type,
            library_id=request.library_id,
            library_version=request.library_version,
            steps_to_reproduce=request.steps_to_reproduce,
            expected_behavior=request.expected_behavior,
            actual_behavior=request.actual_behavior,
            code_snippet=request.code_snippet,
            error_message=request.error_message,
            environment=request.environment,
            severity=request.severity,
            external_url=request.external_url,
            tags=request.tags,
            metadata=request.metadata,
        )
        return IssueResponse.model_validate(issue)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to create issue", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("", response_model=IssueListResponse)
async def list_issues(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    library_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(open|confirmed|resolved|closed|duplicate)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|major|minor|trivial)$"),
    author_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List issues with optional filters."""
    try:
        service = IssueService(session)
        issues, total = await service.list_issues(
            limit=limit,
            offset=offset,
            library_id=library_id,
            status=status,
            severity=severity,
            author_id=author_id,
        )
        return IssueListResponse(
            issues=[IssueResponse.model_validate(i) for i in issues],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error("Failed to list issues", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search", response_model=IssueListResponse)
async def search_issues(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    library_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(open|confirmed|resolved|closed|duplicate)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|major|minor|trivial)$"),
    session: AsyncSession = Depends(get_session),
):
    """Search issues by text."""
    try:
        service = IssueService(session)
        issues = await service.search_issues(
            query=q,
            limit=limit,
            offset=offset,
            library_id=library_id,
            status=status,
            severity=severity,
        )
        return IssueListResponse(
            issues=[IssueResponse.model_validate(i) for i in issues],
            total=len(issues),  # Simple count for search
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error("Failed to search issues", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get an issue by ID."""
    try:
        service = IssueService(session)
        issue = await service.get_issue(issue_id, increment_views=True)
        return IssueResponse.model_validate(issue)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to get issue", error=str(e), issue_id=str(issue_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: UUID,
    request: IssueUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an issue."""
    try:
        service = IssueService(session)
        issue = await service.update_issue(
            issue_id=issue_id,
            title=request.title,
            description=request.description,
            steps_to_reproduce=request.steps_to_reproduce,
            expected_behavior=request.expected_behavior,
            actual_behavior=request.actual_behavior,
            code_snippet=request.code_snippet,
            error_message=request.error_message,
            environment=request.environment,
            status=request.status,
            severity=request.severity,
            tags=request.tags,
        )
        return IssueResponse.model_validate(issue)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to update issue", error=str(e), issue_id=str(issue_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{issue_id}", status_code=204)
async def delete_issue(
    issue_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete an issue."""
    try:
        service = IssueService(session)
        success = await service.delete_issue(issue_id)
        if not success:
            raise HTTPException(status_code=404, detail="Issue not found")
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete issue", error=str(e), issue_id=str(issue_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{issue_id}/reproduce", response_model=IssueResponse)
async def confirm_reproduction(
    issue_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Confirm that an issue can be reproduced."""
    try:
        service = IssueService(session)
        issue = await service.confirm_reproduction(issue_id)
        return IssueResponse.model_validate(issue)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to confirm reproduction", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============ Solution Routes ============


@router.post("/{issue_id}/solutions", response_model=SolutionResponse, status_code=201)
async def create_solution(
    issue_id: UUID,
    request: SolutionCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new solution for an issue."""
    try:
        service = IssueService(session)
        solution = await service.create_solution(
            issue_id=issue_id,
            description=request.description,
            author_id=request.author_id,
            author_type=request.author_type,
            code_snippet=request.code_snippet,
            metadata=request.metadata,
        )
        return SolutionResponse.model_validate(solution)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to create solution", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{issue_id}/solutions", response_model=SolutionListResponse)
async def list_solutions(
    issue_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List solutions for an issue."""
    try:
        service = IssueService(session)
        solutions, total = await service.list_solutions(
            issue_id=issue_id,
            limit=limit,
            offset=offset,
        )
        return SolutionListResponse(
            solutions=[SolutionResponse.model_validate(s) for s in solutions],
            total=total,
        )
    except Exception as e:
        logger.error("Failed to list solutions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/solutions/{solution_id}", response_model=SolutionResponse)
async def get_solution(
    solution_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get a solution by ID."""
    try:
        service = IssueService(session)
        solution = await service.get_solution(solution_id)
        return SolutionResponse.model_validate(solution)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to get solution", error=str(e), solution_id=str(solution_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/solutions/{solution_id}", response_model=SolutionResponse)
async def update_solution(
    solution_id: UUID,
    request: SolutionUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a solution."""
    try:
        service = IssueService(session)
        solution = await service.update_solution(
            solution_id=solution_id,
            description=request.description,
            code_snippet=request.code_snippet,
        )
        return SolutionResponse.model_validate(solution)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to update solution", error=str(e), solution_id=str(solution_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/solutions/{solution_id}", status_code=204)
async def delete_solution(
    solution_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a solution."""
    try:
        service = IssueService(session)
        success = await service.delete_solution(solution_id)
        if not success:
            raise HTTPException(status_code=404, detail="Solution not found")
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete solution", error=str(e), solution_id=str(solution_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{issue_id}/accept/{solution_id}", response_model=SolutionResponse)
async def accept_solution(
    issue_id: UUID,
    solution_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Accept a solution as the fix."""
    try:
        service = IssueService(session)
        solution = await service.accept_solution(issue_id, solution_id)
        return SolutionResponse.model_validate(solution)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to accept solution", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{issue_id}/accept", status_code=204)
async def unaccept_solution(
    issue_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Remove accepted status from any solution."""
    try:
        service = IssueService(session)
        await service.unaccept_solution(issue_id)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to unaccept solution", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/solutions/{solution_id}/feedback", response_model=SolutionResponse)
async def solution_feedback(
    solution_id: UUID,
    request: SolutionFeedback,
    session: AsyncSession = Depends(get_session),
):
    """Record feedback on whether a solution worked."""
    try:
        service = IssueService(session)
        solution = await service.solution_feedback(
            solution_id=solution_id,
            works=request.works,
        )
        return SolutionResponse.model_validate(solution)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to record feedback", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============ Vote Routes ============


@router.post("/votes", response_model=VoteResponse, status_code=201)
async def create_vote(
    request: VoteCreate,
    session: AsyncSession = Depends(get_session),
):
    """Cast a vote on an issue or solution."""
    try:
        service = IssueService(session)
        vote = await service.vote(
            target_type=request.target_type,
            target_id=request.target_id,
            voter_id=request.voter_id,
            voter_type=request.voter_type,
            value=request.value,
        )
        return VoteResponse.model_validate(vote)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to create vote", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/votes/{target_type}/{target_id}", status_code=204)
async def delete_vote(
    target_type: str,
    target_id: UUID,
    voter_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
):
    """Remove a vote."""
    try:
        service = IssueService(session)
        success = await service.remove_vote(
            target_type=target_type,
            target_id=target_id,
            voter_id=voter_id,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Vote not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete vote", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
