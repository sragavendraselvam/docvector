"""Q&A API schemas - Questions, Answers, Tags."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============ Tag Schemas ============


class TagCreate(BaseModel):
    """Create tag request."""

    name: str = Field(..., min_length=1, max_length=100, description="Tag name")
    description: Optional[str] = Field(None, description="Tag description")
    category: Optional[str] = Field(
        None,
        max_length=50,
        description="Tag category (framework, language, topic, etc.)",
    )


class TagResponse(BaseModel):
    """Tag response."""

    id: UUID
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    usage_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Question Schemas ============


class QuestionCreate(BaseModel):
    """Create question request."""

    title: str = Field(..., min_length=10, max_length=500, description="Question title")
    body: str = Field(..., min_length=20, description="Question body (markdown supported)")
    library_id: Optional[UUID] = Field(None, description="Associated library ID")
    library_version: Optional[str] = Field(None, max_length=50, description="Library version")
    author_id: str = Field(..., min_length=1, max_length=255, description="Author identifier")
    author_type: str = Field(
        "agent",
        pattern="^(agent|user)$",
        description="Author type: agent or user",
    )
    tags: Optional[List[str]] = Field(None, description="Tag names to associate")
    metadata: Optional[Dict] = Field(default_factory=dict, description="Additional metadata")


class QuestionUpdate(BaseModel):
    """Update question request."""

    title: Optional[str] = Field(None, min_length=10, max_length=500)
    body: Optional[str] = Field(None, min_length=20)
    status: Optional[str] = Field(None, pattern="^(open|answered|closed)$")
    tags: Optional[List[str]] = None


class QuestionResponse(BaseModel):
    """Question response."""

    id: UUID
    title: str
    body: str
    body_html: Optional[str] = None
    library_id: Optional[UUID] = None
    library_version: Optional[str] = None
    author_id: str
    author_type: str
    status: str
    vote_score: int
    view_count: int
    answer_count: int
    accepted_answer_id: Optional[UUID] = None
    tags: List[TagResponse] = Field(default_factory=list)
    metadata: Dict = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class QuestionListResponse(BaseModel):
    """Paginated question list response."""

    questions: List[QuestionResponse]
    total: int
    limit: int
    offset: int


# ============ Answer Schemas ============


class AnswerCreate(BaseModel):
    """Create answer request."""

    question_id: UUID = Field(..., description="Question ID to answer")
    body: str = Field(..., min_length=10, description="Answer body (markdown supported)")
    author_id: str = Field(..., min_length=1, max_length=255, description="Author identifier")
    author_type: str = Field(
        "agent",
        pattern="^(agent|user)$",
        description="Author type: agent or user",
    )
    metadata: Optional[Dict] = Field(default_factory=dict, description="Additional metadata")


class AnswerUpdate(BaseModel):
    """Update answer request."""

    body: Optional[str] = Field(None, min_length=10)


class AnswerResponse(BaseModel):
    """Answer response."""

    id: UUID
    question_id: UUID
    body: str
    body_html: Optional[str] = None
    author_id: str
    author_type: str
    is_accepted: bool
    vote_score: int
    validation_status: Optional[str] = None
    validation_details: Optional[Dict] = None
    metadata: Dict = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class AnswerListResponse(BaseModel):
    """Answer list response."""

    answers: List[AnswerResponse]
    total: int


# ============ Vote Schemas ============


class VoteCreate(BaseModel):
    """Create vote request."""

    target_type: str = Field(
        ...,
        pattern="^(question|answer|issue|solution)$",
        description="What to vote on",
    )
    target_id: UUID = Field(..., description="ID of the item to vote on")
    voter_id: str = Field(..., min_length=1, max_length=255, description="Voter identifier")
    voter_type: str = Field(
        "agent",
        pattern="^(agent|user)$",
        description="Voter type: agent or user",
    )
    value: int = Field(..., ge=-1, le=1, description="Vote value: 1 (upvote) or -1 (downvote)")


class VoteResponse(BaseModel):
    """Vote response."""

    id: UUID
    target_type: str
    target_id: UUID
    voter_id: str
    voter_type: str
    value: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Search Schemas ============


class QASearchRequest(BaseModel):
    """Search Q&A content request."""

    query: str = Field(..., min_length=1, description="Search query")
    search_type: str = Field(
        "all",
        pattern="^(all|questions|answers)$",
        description="What to search: all, questions, answers",
    )
    library_id: Optional[UUID] = Field(None, description="Filter by library")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    status: Optional[str] = Field(None, description="Filter by status")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class QASearchResult(BaseModel):
    """Single Q&A search result."""

    id: UUID
    type: str  # question or answer
    title: Optional[str] = None  # Only for questions
    body: str
    score: float
    vote_score: int
    author_id: str
    created_at: datetime


class QASearchResponse(BaseModel):
    """Q&A search response."""

    query: str
    results: List[QASearchResult]
    total: int
