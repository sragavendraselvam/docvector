"""API schemas (Pydantic models)."""

from .common import HealthResponse
from .ingestion import IngestionResponse, IngestSourceRequest, IngestUrlRequest
from .issues import (
    IssueCreate,
    IssueListResponse,
    IssueResponse,
    IssueSearchRequest,
    IssueSearchResponse,
    IssueSearchResult,
    IssueUpdate,
    SolutionCreate,
    SolutionFeedback,
    SolutionListResponse,
    SolutionResponse,
    SolutionUpdate,
)
from .job import (
    CrawlSourceRequest,
    CrawlUrlRequest,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobStatsResponse,
)
from .qa import (
    AnswerCreate,
    AnswerListResponse,
    AnswerResponse,
    AnswerUpdate,
    QASearchRequest,
    QASearchResponse,
    QASearchResult,
    QuestionCreate,
    QuestionListResponse,
    QuestionResponse,
    QuestionUpdate,
    TagCreate,
    TagResponse,
    VoteCreate,
    VoteResponse,
)
from .search import SearchRequest, SearchResponse, SearchResultSchema
from .source import SourceCreate, SourceResponse, SourceUpdate

__all__ = [
    # Search
    "SearchRequest",
    "SearchResponse",
    "SearchResultSchema",
    # Source
    "SourceCreate",
    "SourceResponse",
    "SourceUpdate",
    # Common
    "HealthResponse",
    # Ingestion
    "IngestSourceRequest",
    "IngestUrlRequest",
    "IngestionResponse",
    # Jobs
    "JobCreate",
    "JobResponse",
    "JobListResponse",
    "JobStatsResponse",
    "CrawlSourceRequest",
    "CrawlUrlRequest",
    # Q&A - Tags
    "TagCreate",
    "TagResponse",
    # Q&A - Questions
    "QuestionCreate",
    "QuestionUpdate",
    "QuestionResponse",
    "QuestionListResponse",
    # Q&A - Answers
    "AnswerCreate",
    "AnswerUpdate",
    "AnswerResponse",
    "AnswerListResponse",
    # Q&A - Votes
    "VoteCreate",
    "VoteResponse",
    # Q&A - Search
    "QASearchRequest",
    "QASearchResponse",
    "QASearchResult",
    # Issues
    "IssueCreate",
    "IssueUpdate",
    "IssueResponse",
    "IssueListResponse",
    # Solutions
    "SolutionCreate",
    "SolutionUpdate",
    "SolutionResponse",
    "SolutionListResponse",
    "SolutionFeedback",
    # Issue Search
    "IssueSearchRequest",
    "IssueSearchResponse",
    "IssueSearchResult",
]
