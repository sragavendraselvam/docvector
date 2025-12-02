"""Issue API schemas - Issues and Solutions."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .qa import TagResponse


# ============ Issue Schemas ============


class IssueCreate(BaseModel):
    """Create issue request."""

    title: str = Field(..., min_length=10, max_length=500, description="Issue title")
    description: str = Field(..., min_length=20, description="Issue description (markdown supported)")
    library_id: Optional[UUID] = Field(None, description="Associated library ID")
    library_version: Optional[str] = Field(None, max_length=50, description="Library version")

    # Reproduction details
    steps_to_reproduce: Optional[str] = Field(None, description="Steps to reproduce the issue")
    expected_behavior: Optional[str] = Field(None, description="What should happen")
    actual_behavior: Optional[str] = Field(None, description="What actually happens")
    code_snippet: Optional[str] = Field(None, description="Code that reproduces the issue")
    error_message: Optional[str] = Field(None, description="Error message if any")

    # Environment
    environment: Optional[Dict] = Field(None, description="Environment info (OS, runtime, etc.)")

    # Author
    author_id: str = Field(..., min_length=1, max_length=255, description="Author identifier")
    author_type: str = Field(
        "agent",
        pattern="^(agent|user)$",
        description="Author type: agent or user",
    )

    # Classification
    severity: Optional[str] = Field(
        None,
        pattern="^(critical|major|minor|trivial)$",
        description="Issue severity",
    )
    tags: Optional[List[str]] = Field(None, description="Tag names to associate")

    # External reference
    external_url: Optional[str] = Field(None, max_length=2048, description="Related external URL (GitHub issue, etc.)")

    metadata: Optional[Dict] = Field(default_factory=dict, description="Additional metadata")


class IssueUpdate(BaseModel):
    """Update issue request."""

    title: Optional[str] = Field(None, min_length=10, max_length=500)
    description: Optional[str] = Field(None, min_length=20)
    steps_to_reproduce: Optional[str] = None
    expected_behavior: Optional[str] = None
    actual_behavior: Optional[str] = None
    code_snippet: Optional[str] = None
    error_message: Optional[str] = None
    environment: Optional[Dict] = None
    status: Optional[str] = Field(
        None,
        pattern="^(open|confirmed|resolved|closed|duplicate)$",
    )
    severity: Optional[str] = Field(
        None,
        pattern="^(critical|major|minor|trivial)$",
    )
    tags: Optional[List[str]] = None


class IssueResponse(BaseModel):
    """Issue response."""

    id: UUID
    title: str
    description: str
    description_html: Optional[str] = None
    library_id: Optional[UUID] = None
    library_version: Optional[str] = None

    # Reproduction details
    steps_to_reproduce: Optional[str] = None
    expected_behavior: Optional[str] = None
    actual_behavior: Optional[str] = None
    code_snippet: Optional[str] = None
    error_message: Optional[str] = None
    environment: Optional[Dict] = None

    # Author
    author_id: str
    author_type: str

    # Status and scoring
    status: str
    severity: Optional[str] = None
    vote_score: int
    view_count: int
    solution_count: int
    accepted_solution_id: Optional[UUID] = None

    # Reproducibility
    is_reproducible: Optional[bool] = None
    reproduction_count: int

    # External
    external_url: Optional[str] = None
    external_id: Optional[str] = None

    # Tags
    tags: List[TagResponse] = Field(default_factory=list)

    metadata: Dict = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class IssueListResponse(BaseModel):
    """Paginated issue list response."""

    issues: List[IssueResponse]
    total: int
    limit: int
    offset: int


# ============ Solution Schemas ============


class SolutionCreate(BaseModel):
    """Create solution request."""

    issue_id: UUID = Field(..., description="Issue ID to solve")
    description: str = Field(..., min_length=10, description="Solution description (markdown supported)")
    code_snippet: Optional[str] = Field(None, description="Code that fixes the issue")
    author_id: str = Field(..., min_length=1, max_length=255, description="Author identifier")
    author_type: str = Field(
        "agent",
        pattern="^(agent|user)$",
        description="Author type: agent or user",
    )
    metadata: Optional[Dict] = Field(default_factory=dict, description="Additional metadata")


class SolutionUpdate(BaseModel):
    """Update solution request."""

    description: Optional[str] = Field(None, min_length=10)
    code_snippet: Optional[str] = None


class SolutionResponse(BaseModel):
    """Solution response."""

    id: UUID
    issue_id: UUID
    description: str
    description_html: Optional[str] = None
    code_snippet: Optional[str] = None
    author_id: str
    author_type: str
    is_accepted: bool
    vote_score: int
    validation_status: Optional[str] = None
    validation_details: Optional[Dict] = None
    works_count: int
    doesnt_work_count: int
    metadata: Dict = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class SolutionListResponse(BaseModel):
    """Solution list response."""

    solutions: List[SolutionResponse]
    total: int


# ============ Feedback Schemas ============


class SolutionFeedback(BaseModel):
    """Feedback on whether a solution worked."""

    solution_id: UUID = Field(..., description="Solution ID")
    works: bool = Field(..., description="Did this solution work for you?")
    voter_id: str = Field(..., min_length=1, max_length=255, description="Voter identifier")


# ============ Search Schemas ============


class IssueSearchRequest(BaseModel):
    """Search issues request."""

    query: str = Field(..., min_length=1, description="Search query")
    search_type: str = Field(
        "all",
        pattern="^(all|issues|solutions)$",
        description="What to search: all, issues, solutions",
    )
    library_id: Optional[UUID] = Field(None, description="Filter by library")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    status: Optional[str] = Field(None, description="Filter by status")
    severity: Optional[str] = Field(None, description="Filter by severity")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class IssueSearchResult(BaseModel):
    """Single issue search result."""

    id: UUID
    type: str  # issue or solution
    title: Optional[str] = None  # Only for issues
    description: str
    score: float
    vote_score: int
    status: Optional[str] = None  # Only for issues
    severity: Optional[str] = None  # Only for issues
    author_id: str
    created_at: datetime


class IssueSearchResponse(BaseModel):
    """Issue search response."""

    query: str
    results: List[IssueSearchResult]
    total: int
