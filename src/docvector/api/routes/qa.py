"""Q&A API routes - Questions, Answers, Tags, Votes."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from docvector.api.dependencies import get_session
from docvector.api.schemas import (
    AnswerCreate,
    AnswerListResponse,
    AnswerResponse,
    AnswerUpdate,
    QuestionCreate,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdate,
    TagCreate,
    TagResponse,
    VoteCreate,
    VoteResponse,
)
from docvector.core import DocVectorException, get_logger
from docvector.services import QAService

logger = get_logger(__name__)

router = APIRouter()


# ============ Tag Routes ============


@router.post("/tags", response_model=TagResponse, status_code=201)
async def create_tag(
    request: TagCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new tag."""
    try:
        service = QAService(session)
        tag = await service.create_tag(
            name=request.name,
            description=request.description,
            category=request.category,
        )
        return TagResponse.model_validate(tag)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to create tag", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tags", response_model=List[TagResponse])
async def list_tags(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List all tags."""
    try:
        service = QAService(session)
        tags = await service.list_tags(limit=limit, offset=offset)
        return [TagResponse.model_validate(t) for t in tags]
    except Exception as e:
        logger.error("Failed to list tags", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tags/search", response_model=List[TagResponse])
async def search_tags(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Search tags by name prefix."""
    try:
        service = QAService(session)
        tags = await service.search_tags(query=q, limit=limit)
        return [TagResponse.model_validate(t) for t in tags]
    except Exception as e:
        logger.error("Failed to search tags", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============ Question Routes ============


@router.post("/questions", response_model=QuestionResponse, status_code=201)
async def create_question(
    request: QuestionCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new question."""
    try:
        service = QAService(session)
        question = await service.create_question(
            title=request.title,
            body=request.body,
            author_id=request.author_id,
            author_type=request.author_type,
            library_id=request.library_id,
            library_version=request.library_version,
            tags=request.tags,
            metadata=request.metadata,
        )
        return QuestionResponse.model_validate(question)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to create question", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/questions", response_model=QuestionListResponse)
async def list_questions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    library_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(open|answered|closed)$"),
    author_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List questions with optional filters."""
    try:
        service = QAService(session)
        questions, total = await service.list_questions(
            limit=limit,
            offset=offset,
            library_id=library_id,
            status=status,
            author_id=author_id,
        )
        return QuestionListResponse(
            questions=[QuestionResponse.model_validate(q) for q in questions],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error("Failed to list questions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/questions/search", response_model=QuestionListResponse)
async def search_questions(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    library_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_session),
):
    """Search questions by text."""
    try:
        service = QAService(session)
        questions = await service.search_questions(
            query=q,
            limit=limit,
            offset=offset,
            library_id=library_id,
        )
        return QuestionListResponse(
            questions=[QuestionResponse.model_validate(q) for q in questions],
            total=len(questions),  # Simple count for search
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error("Failed to search questions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get a question by ID."""
    try:
        service = QAService(session)
        question = await service.get_question(question_id, increment_views=True)
        return QuestionResponse.model_validate(question)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to get question", error=str(e), question_id=str(question_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: UUID,
    request: QuestionUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a question."""
    try:
        service = QAService(session)
        question = await service.update_question(
            question_id=question_id,
            title=request.title,
            body=request.body,
            status=request.status,
            tags=request.tags,
        )
        return QuestionResponse.model_validate(question)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to update question", error=str(e), question_id=str(question_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(
    question_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a question."""
    try:
        service = QAService(session)
        success = await service.delete_question(question_id)
        if not success:
            raise HTTPException(status_code=404, detail="Question not found")
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete question", error=str(e), question_id=str(question_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============ Answer Routes ============


@router.post("/questions/{question_id}/answers", response_model=AnswerResponse, status_code=201)
async def create_answer(
    question_id: UUID,
    request: AnswerCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new answer for a question."""
    try:
        service = QAService(session)
        answer = await service.create_answer(
            question_id=question_id,
            body=request.body,
            author_id=request.author_id,
            author_type=request.author_type,
            metadata=request.metadata,
        )
        return AnswerResponse.model_validate(answer)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to create answer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/questions/{question_id}/answers", response_model=AnswerListResponse)
async def list_answers(
    question_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List answers for a question."""
    try:
        service = QAService(session)
        answers, total = await service.list_answers(
            question_id=question_id,
            limit=limit,
            offset=offset,
        )
        return AnswerListResponse(
            answers=[AnswerResponse.model_validate(a) for a in answers],
            total=total,
        )
    except Exception as e:
        logger.error("Failed to list answers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/answers/{answer_id}", response_model=AnswerResponse)
async def get_answer(
    answer_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get an answer by ID."""
    try:
        service = QAService(session)
        answer = await service.get_answer(answer_id)
        return AnswerResponse.model_validate(answer)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to get answer", error=str(e), answer_id=str(answer_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/answers/{answer_id}", response_model=AnswerResponse)
async def update_answer(
    answer_id: UUID,
    request: AnswerUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an answer."""
    try:
        service = QAService(session)
        answer = await service.update_answer(
            answer_id=answer_id,
            body=request.body,
        )
        return AnswerResponse.model_validate(answer)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to update answer", error=str(e), answer_id=str(answer_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/answers/{answer_id}", status_code=204)
async def delete_answer(
    answer_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete an answer."""
    try:
        service = QAService(session)
        success = await service.delete_answer(answer_id)
        if not success:
            raise HTTPException(status_code=404, detail="Answer not found")
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete answer", error=str(e), answer_id=str(answer_id))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/questions/{question_id}/accept/{answer_id}", response_model=AnswerResponse)
async def accept_answer(
    question_id: UUID,
    answer_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Accept an answer as the solution."""
    try:
        service = QAService(session)
        answer = await service.accept_answer(question_id, answer_id)
        return AnswerResponse.model_validate(answer)
    except DocVectorException as e:
        raise HTTPException(status_code=400, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to accept answer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/questions/{question_id}/accept", status_code=204)
async def unaccept_answer(
    question_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Remove accepted status from any answer."""
    try:
        service = QAService(session)
        await service.unaccept_answer(question_id)
    except DocVectorException as e:
        raise HTTPException(status_code=404, detail=e.to_dict()) from e
    except Exception as e:
        logger.error("Failed to unaccept answer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============ Vote Routes ============


@router.post("/votes", response_model=VoteResponse, status_code=201)
async def create_vote(
    request: VoteCreate,
    session: AsyncSession = Depends(get_session),
):
    """Cast a vote on a question or answer."""
    try:
        service = QAService(session)
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
        service = QAService(session)
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
