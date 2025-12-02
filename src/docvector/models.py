"""SQLAlchemy database models."""

from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import JSON, TypeDecorator


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Library(Base):
    """Library model - represents a software library/package."""

    __tablename__ = "libraries"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    library_id = Column(String(255), nullable=False, unique=True)  # e.g., "mongodb/docs", "vercel/next.js"
    name = Column(String(255), nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)
    homepage_url = Column(String(2048), nullable=True)
    repository_url = Column(String(2048), nullable=True)
    aliases = Column(PG_ARRAY(String), nullable=False, server_default="{}")  # Alternative names
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    sources = relationship("Source", back_populates="library")

    def __repr__(self) -> str:
        return f"<Library(id={self.id}, library_id={self.library_id}, name={self.name})>"


class Source(Base):
    """Source model - represents a documentation source."""

    __tablename__ = "sources"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(50), nullable=False)
    library_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("libraries.id", ondelete="SET NULL"), nullable=True
    )
    version = Column(String(50), nullable=True)  # Library version (e.g., "3.11", "18.2.0")
    config = Column(JSONB, nullable=False, server_default="{}")
    status = Column(String(50), nullable=False, server_default="active")
    sync_frequency = Column(String(50), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    library = relationship("Library", back_populates="sources")
    documents = relationship("Document", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Source(id={self.id}, name={self.name}, type={self.type}, version={self.version})>"


class Document(Base):
    """Document model - represents a single document from a source."""

    __tablename__ = "documents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    url = Column(String(2048), nullable=True)
    path = Column(String(1024), nullable=True)
    content_hash = Column(String(64), nullable=False)
    title = Column(String(512), nullable=True)
    content = Column(Text, nullable=True)
    content_length = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    language = Column(String(10), nullable=False, server_default="en")
    format = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, server_default="pending")
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, server_default="0")
    chunking_strategy = Column(String(50), server_default="semantic")
    fetched_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    author = Column(String(255), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    modified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    source = relationship("Source", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title={self.title}, status={self.status})>"


class Chunk(Base):
    """Chunk model - represents a chunk of a document."""

    __tablename__ = "chunks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_length = Column(Integer, nullable=False)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)

    # Context7-style features
    is_code_snippet = Column(Integer, nullable=False, server_default="0")  # Boolean (0/1)
    code_language = Column(String(50), nullable=True)  # Programming language
    topics = Column(PG_ARRAY(String), nullable=False, server_default="{}")  # Topic tags
    enrichment = Column(Text, nullable=True)  # LLM-generated explanation

    # Quality scores (0-1 range)
    relevance_score = Column(Float, nullable=True)  # Question relevance
    code_quality_score = Column(Float, nullable=True)  # Code quality
    formatting_score = Column(Float, nullable=True)  # Formatting quality
    metadata_score = Column(Float, nullable=True)  # Metadata richness
    initialization_score = Column(Float, nullable=True)  # Initialization guidance

    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    embedding_id = Column(String(255), nullable=True)
    embedding_model = Column(String(255), nullable=True)
    embedded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, document_id={self.document_id}, index={self.index})>"


# Junction tables for many-to-many relationships
question_tags = Table(
    "question_tags",
    Base.metadata,
    Column(
        "question_id",
        PG_UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

issue_tags = Table(
    "issue_tags",
    Base.metadata,
    Column(
        "issue_id",
        PG_UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tag(Base):
    """Tag model - reusable tags for categorizing questions and issues."""

    __tablename__ = "tags"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # framework, language, topic, etc.
    usage_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    questions = relationship("Question", secondary=question_tags, back_populates="tags")
    issues = relationship("Issue", secondary=issue_tags, back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name={self.name})>"


class Question(Base):
    """Question model - user/agent submitted questions about libraries."""

    __tablename__ = "questions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    body_html = Column(Text, nullable=True)  # Rendered markdown

    # External source tracking (StackOverflow, GitHub, Discourse, etc.)
    source = Column(String(50), nullable=False, server_default="internal")  # stackoverflow, github, discourse, internal
    source_id = Column(String(255), nullable=True)  # Original ID from external source
    source_url = Column(String(2048), nullable=True)  # Link to original

    # Library association
    library_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("libraries.id", ondelete="SET NULL"),
        nullable=True,
    )
    library_name = Column(String(255), nullable=True)  # Denormalized for search
    library_version = Column(String(50), nullable=True)

    # Author info (placeholder for future auth - using string identifier for now)
    author_id = Column(String(255), nullable=False)  # Agent ID or user ID
    author_type = Column(String(50), nullable=False, server_default="agent")  # agent, user, external

    # Status and scoring
    status = Column(String(50), nullable=False, server_default="open")  # open, answered, closed, duplicate
    is_answered = Column(Boolean, nullable=False, server_default="false")
    vote_score = Column(Integer, nullable=False, server_default="0")
    view_count = Column(Integer, nullable=False, server_default="0")
    answer_count = Column(Integer, nullable=False, server_default="0")
    accepted_answer_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # Embedding for semantic search
    embedding_id = Column(String(255), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    answered_at = Column(DateTime(timezone=True), nullable=True)

    # Unique constraint for external sources
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_questions_source"),
    )

    # Relationships
    library = relationship("Library", backref="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="question", cascade="all, delete-orphan", foreign_keys="Comment.question_id")
    tags = relationship("Tag", secondary=question_tags, back_populates="questions")

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, title={self.title[:50]}, status={self.status})>"


class Answer(Base):
    """Answer model - answers to questions."""

    __tablename__ = "answers"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    question_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    body = Column(Text, nullable=False)
    body_html = Column(Text, nullable=True)
    code_snippets = Column(JSONB, nullable=True, server_default="[]")  # Extracted code blocks

    # External source tracking
    source = Column(String(50), nullable=False, server_default="internal")
    source_id = Column(String(255), nullable=True)
    source_url = Column(String(2048), nullable=True)

    # Author info
    author_id = Column(String(255), nullable=False)
    author_type = Column(String(50), nullable=False, server_default="agent")

    # Status and scoring
    is_accepted = Column(Boolean, nullable=False, server_default="false")
    is_verified = Column(Boolean, nullable=False, server_default="false")  # Verified by author/community
    vote_score = Column(Integer, nullable=False, server_default="0")

    # Code validation (for AI-submitted answers)
    validation_status = Column(String(50), nullable=True)  # pending, validated, failed
    validation_details = Column(JSONB, nullable=True)
    verification_proof = Column(JSONB, nullable=True)  # How it was verified

    # Embedding for semantic search
    embedding_id = Column(String(255), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    question = relationship("Question", back_populates="answers")
    comments = relationship("Comment", back_populates="answer", cascade="all, delete-orphan", foreign_keys="Comment.answer_id")

    def __repr__(self) -> str:
        return f"<Answer(id={self.id}, question_id={self.question_id}, is_accepted={self.is_accepted})>"


class Comment(Base):
    """Comment model - comments on questions, answers, or other comments."""

    __tablename__ = "comments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Parent (can be question, answer, or another comment)
    question_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=True,
    )
    answer_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=True,
    )
    parent_comment_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
    )

    # External source tracking
    source = Column(String(50), nullable=False, server_default="internal")
    source_id = Column(String(255), nullable=True)

    # Content
    body = Column(Text, nullable=False)

    # Metrics
    vote_score = Column(Integer, nullable=False, server_default="0")

    # Author info
    author_id = Column(String(255), nullable=False)
    author_type = Column(String(50), nullable=False, server_default="agent")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    question = relationship("Question", back_populates="comments", foreign_keys=[question_id])
    answer = relationship("Answer", back_populates="comments", foreign_keys=[answer_id])
    parent = relationship("Comment", remote_side=[id], backref="replies")

    def __repr__(self) -> str:
        return f"<Comment(id={self.id}, author_id={self.author_id})>"


class Issue(Base):
    """Issue model - bug reports and problems with reproducible examples."""

    __tablename__ = "issues"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    description_html = Column(Text, nullable=True)

    # Library association
    library_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("libraries.id", ondelete="SET NULL"),
        nullable=True,
    )
    library_version = Column(String(50), nullable=True)

    # Reproduction details
    steps_to_reproduce = Column(Text, nullable=True)
    expected_behavior = Column(Text, nullable=True)
    actual_behavior = Column(Text, nullable=True)
    code_snippet = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Environment info
    environment = Column(JSONB, nullable=True)  # OS, runtime, dependencies

    # Author info
    author_id = Column(String(255), nullable=False)
    author_type = Column(String(50), nullable=False, server_default="agent")

    # Status and scoring
    status = Column(String(50), nullable=False, server_default="open")  # open, confirmed, resolved, closed, duplicate
    severity = Column(String(50), nullable=True)  # critical, major, minor, trivial
    vote_score = Column(Integer, nullable=False, server_default="0")
    view_count = Column(Integer, nullable=False, server_default="0")
    solution_count = Column(Integer, nullable=False, server_default="0")
    accepted_solution_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # Reproducibility validation
    is_reproducible = Column(Boolean, nullable=True)
    reproduction_count = Column(Integer, nullable=False, server_default="0")

    # Embedding for semantic search
    embedding_id = Column(String(255), nullable=True)

    # External references (GitHub issue, etc.)
    external_url = Column(String(2048), nullable=True)
    external_id = Column(String(255), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    library = relationship("Library", backref="issues")
    solutions = relationship("Solution", back_populates="issue", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=issue_tags, back_populates="issues")

    def __repr__(self) -> str:
        return f"<Issue(id={self.id}, title={self.title[:50]}, status={self.status})>"


class Solution(Base):
    """Solution model - solutions to issues."""

    __tablename__ = "solutions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    issue_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    description = Column(Text, nullable=False)
    description_html = Column(Text, nullable=True)
    code_snippet = Column(Text, nullable=True)

    # Author info
    author_id = Column(String(255), nullable=False)
    author_type = Column(String(50), nullable=False, server_default="agent")

    # Status and scoring
    is_accepted = Column(Boolean, nullable=False, server_default="false")
    vote_score = Column(Integer, nullable=False, server_default="0")

    # Validation (did this actually fix the issue?)
    validation_status = Column(String(50), nullable=True)  # pending, validated, failed
    validation_details = Column(JSONB, nullable=True)
    works_count = Column(Integer, nullable=False, server_default="0")  # "This worked for me"
    doesnt_work_count = Column(Integer, nullable=False, server_default="0")

    # Embedding for semantic search
    embedding_id = Column(String(255), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    issue = relationship("Issue", back_populates="solutions")

    def __repr__(self) -> str:
        return f"<Solution(id={self.id}, issue_id={self.issue_id}, is_accepted={self.is_accepted})>"


class Vote(Base):
    """Vote model - upvotes/downvotes on questions, answers, issues, solutions, comments."""

    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("voter_id", "target_type", "target_id", name="uq_votes_voter_target"),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # What is being voted on (polymorphic)
    target_type = Column(String(50), nullable=False)  # question, answer, issue, solution, comment
    target_id = Column(PG_UUID(as_uuid=True), nullable=False)

    # Who voted
    voter_id = Column(String(255), nullable=False)
    voter_type = Column(String(50), nullable=False, server_default="agent")

    # Vote value
    value = Column(Integer, nullable=False)  # +1 (upvote) or -1 (downvote)

    # Proof of work (anti-spam for agent votes)
    pow_nonce = Column(String(64), nullable=True)
    pow_hash = Column(String(64), nullable=True)
    pow_difficulty = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Vote(id={self.id}, target={self.target_type}:{self.target_id}, value={self.value})>"


class ProofOfWorkChallenge(Base):
    """Proof-of-work challenge for anti-spam protection."""

    __tablename__ = "pow_challenges"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    challenge = Column(String(255), nullable=False, unique=True)
    action = Column(String(50), nullable=False)  # question, answer, comment, vote
    target_id = Column(String(255), nullable=True)  # Optional target ID
    agent_id = Column(String(255), nullable=False)
    difficulty = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, server_default="false")
    used_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ProofOfWorkChallenge(id={self.id}, action={self.action}, used={self.used})>"


# =============================================================================
# ENTERPRISE / MULTI-TENANCY MODELS
# =============================================================================


# Junction table for organization members
org_members = Table(
    "org_members",
    Base.metadata,
    Column(
        "org_id",
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("role", String(50), nullable=False, server_default="member"),  # owner, admin, member, viewer
    Column("invited_at", DateTime(timezone=True), server_default=func.now()),
    Column("joined_at", DateTime(timezone=True), nullable=True),
)


class User(Base):
    """User model - represents a human user or service account."""

    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identity
    email = Column(String(255), nullable=False, unique=True)
    username = Column(String(100), nullable=True, unique=True)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(2048), nullable=True)

    # Authentication
    password_hash = Column(String(255), nullable=True)  # Null for OAuth-only users
    email_verified = Column(Boolean, nullable=False, server_default="false")
    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Account type
    account_type = Column(String(50), nullable=False, server_default="user")  # user, service, bot
    is_active = Column(Boolean, nullable=False, server_default="true")
    is_superuser = Column(Boolean, nullable=False, server_default="false")

    # OAuth providers (linked accounts)
    oauth_providers = Column(JSONB, nullable=False, server_default="{}")  # {github: {id, username}, google: {id, email}}

    # Reputation and stats
    reputation = Column(Integer, nullable=False, server_default="0")
    questions_count = Column(Integer, nullable=False, server_default="0")
    answers_count = Column(Integer, nullable=False, server_default="0")
    accepted_answers_count = Column(Integer, nullable=False, server_default="0")

    # Preferences
    preferences = Column(JSONB, nullable=False, server_default="{}")

    # Timestamps
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organizations = relationship("Organization", secondary=org_members, back_populates="members")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, username={self.username})>"


class Organization(Base):
    """Organization model - represents a company, team, or group."""

    __tablename__ = "organizations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identity
    slug = Column(String(100), nullable=False, unique=True)  # URL-safe identifier
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(2048), nullable=True)
    website_url = Column(String(2048), nullable=True)

    # Owner
    owner_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Subscription and billing
    plan = Column(String(50), nullable=False, server_default="free")  # free, starter, pro, enterprise
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True, unique=True)
    stripe_subscription_id = Column(String(255), nullable=True)

    # Quotas (based on plan)
    max_members = Column(Integer, nullable=False, server_default="5")
    max_api_keys = Column(Integer, nullable=False, server_default="3")
    max_sources = Column(Integer, nullable=False, server_default="10")
    max_documents = Column(Integer, nullable=False, server_default="1000")
    max_queries_per_day = Column(Integer, nullable=False, server_default="1000")
    max_storage_mb = Column(Integer, nullable=False, server_default="100")

    # Usage tracking
    current_members = Column(Integer, nullable=False, server_default="0")
    current_sources = Column(Integer, nullable=False, server_default="0")
    current_documents = Column(Integer, nullable=False, server_default="0")
    current_storage_mb = Column(Integer, nullable=False, server_default="0")
    queries_today = Column(Integer, nullable=False, server_default="0")
    queries_reset_at = Column(DateTime(timezone=True), nullable=True)

    # Settings
    settings = Column(JSONB, nullable=False, server_default="{}")
    is_active = Column(Boolean, nullable=False, server_default="true")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("User", secondary=org_members, back_populates="organizations")
    api_keys = relationship("APIKey", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug={self.slug}, name={self.name}, plan={self.plan})>"


class APIKey(Base):
    """API Key model - for programmatic access to the API."""

    __tablename__ = "api_keys"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Key identity
    name = Column(String(255), nullable=False)  # User-defined name
    key_prefix = Column(String(12), nullable=False)  # First 8 chars of key (for identification)
    key_hash = Column(String(255), nullable=False, unique=True)  # Hashed full key

    # Ownership (user OR organization, not both)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    organization_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Permissions
    scopes = Column(PG_ARRAY(String), nullable=False, server_default="{}")  # read, write, admin
    allowed_ips = Column(PG_ARRAY(String), nullable=True)  # IP whitelist (null = all)
    allowed_origins = Column(PG_ARRAY(String), nullable=True)  # CORS origins

    # Rate limiting
    rate_limit_per_second = Column(Integer, nullable=False, server_default="5")
    rate_limit_per_day = Column(Integer, nullable=True)  # Null = unlimited (or org quota)

    # Status
    is_active = Column(Boolean, nullable=False, server_default="true")
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Null = never expires

    # Usage tracking
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_used_ip = Column(String(45), nullable=True)  # IPv6 max length
    total_requests = Column(Integer, nullable=False, server_default="0")
    requests_today = Column(Integer, nullable=False, server_default="0")
    requests_reset_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="api_keys")
    organization = relationship("Organization", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"


class UserSession(Base):
    """User session model - for tracking authenticated sessions."""

    __tablename__ = "user_sessions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Session identity
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(String(255), nullable=False, unique=True)  # Hashed JWT/session token

    # Session metadata
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    device_info = Column(JSONB, nullable=True)  # Parsed user agent

    # Status
    is_active = Column(Boolean, nullable=False, server_default="true")
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<UserSession(id={self.id}, user_id={self.user_id}, active={self.is_active})>"


class UsageEvent(Base):
    """Usage event model - for tracking API usage and billing."""

    __tablename__ = "usage_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Who
    user_id = Column(PG_UUID(as_uuid=True), nullable=True)
    organization_id = Column(PG_UUID(as_uuid=True), nullable=True)
    api_key_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # What
    event_type = Column(String(50), nullable=False)  # search, ingest, qa_submit, qa_answer
    resource_type = Column(String(50), nullable=True)  # document, chunk, question, answer
    resource_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # Metering
    units = Column(Integer, nullable=False, server_default="1")  # e.g., tokens, documents, queries
    unit_type = Column(String(50), nullable=False, server_default="request")  # request, token, byte, document

    # Context
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    ip_address = Column(String(45), nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<UsageEvent(id={self.id}, type={self.event_type}, units={self.units})>"


class AuditLog(Base):
    """Audit log model - for tracking security-relevant actions."""

    __tablename__ = "audit_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Actor
    actor_type = Column(String(50), nullable=False)  # user, api_key, system
    actor_id = Column(String(255), nullable=False)
    organization_id = Column(PG_UUID(as_uuid=True), nullable=True)

    # Action
    action = Column(String(100), nullable=False)  # create, update, delete, login, logout, etc.
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(255), nullable=True)

    # Details
    changes = Column(JSONB, nullable=True)  # {field: {old: x, new: y}}
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")

    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    # Result
    status = Column(String(50), nullable=False, server_default="success")  # success, failure, blocked
    error_message = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, actor={self.actor_type}:{self.actor_id})>"


# =============================================================================
# BILLING MODELS (Paddle)
# =============================================================================


class Subscription(Base):
    """Subscription model - tracks Paddle subscriptions."""

    __tablename__ = "subscriptions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Paddle identifiers
    paddle_subscription_id = Column(String(255), nullable=False, unique=True)
    paddle_customer_id = Column(String(255), nullable=False)
    paddle_price_id = Column(String(255), nullable=False)

    # Organization link
    organization_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Plan details
    plan = Column(String(50), nullable=False)  # starter, pro, enterprise
    billing_cycle = Column(String(20), nullable=False)  # monthly, yearly
    quantity = Column(Integer, nullable=False, server_default="1")

    # Status
    status = Column(String(50), nullable=False)  # active, past_due, canceled, paused, trialing
    scheduled_change = Column(JSONB, nullable=True)  # Pending plan changes

    # Dates
    current_period_start = Column(DateTime(timezone=True), nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)

    # Trial
    trial_start = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)

    # Pricing (stored in cents/smallest currency unit)
    unit_price = Column(Integer, nullable=False)  # Price per unit
    currency = Column(String(3), nullable=False, server_default="USD")

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", backref="subscriptions")
    transactions = relationship("Transaction", back_populates="subscription", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, paddle_id={self.paddle_subscription_id}, plan={self.plan}, status={self.status})>"


class Transaction(Base):
    """Transaction model - tracks Paddle transactions/invoices."""

    __tablename__ = "transactions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Paddle identifiers
    paddle_transaction_id = Column(String(255), nullable=False, unique=True)
    paddle_invoice_id = Column(String(255), nullable=True)
    paddle_customer_id = Column(String(255), nullable=False)

    # Links
    subscription_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Transaction details
    status = Column(String(50), nullable=False)  # completed, pending, failed, refunded
    origin = Column(String(50), nullable=True)  # subscription_charge, subscription_update, etc.

    # Amounts (stored in cents/smallest currency unit)
    subtotal = Column(Integer, nullable=False)
    tax = Column(Integer, nullable=False, server_default="0")
    total = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, server_default="USD")

    # Tax details
    tax_rate = Column(Float, nullable=True)
    tax_country = Column(String(2), nullable=True)  # ISO country code

    # Payment details
    payment_method_type = Column(String(50), nullable=True)  # card, paypal, apple_pay, google_pay
    card_brand = Column(String(50), nullable=True)  # visa, mastercard, amex
    card_last_four = Column(String(4), nullable=True)

    # Invoice
    invoice_number = Column(String(100), nullable=True)
    invoice_url = Column(String(2048), nullable=True)  # Paddle-hosted invoice URL

    # Line items
    items = Column(JSONB, nullable=False, server_default="[]")

    # Billing period this transaction covers
    billing_period_start = Column(DateTime(timezone=True), nullable=True)
    billing_period_end = Column(DateTime(timezone=True), nullable=True)

    # Dates
    billed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    subscription = relationship("Subscription", back_populates="transactions")
    organization = relationship("Organization", backref="transactions")

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, paddle_id={self.paddle_transaction_id}, total={self.total}, status={self.status})>"


class PaddleCustomer(Base):
    """Paddle customer model - links Paddle customers to organizations."""

    __tablename__ = "paddle_customers"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Paddle identifiers
    paddle_customer_id = Column(String(255), nullable=False, unique=True)

    # Organization link
    organization_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Customer details (synced from Paddle)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)

    # Marketing consent
    marketing_consent = Column(Boolean, nullable=False, server_default="false")

    # Address (for tax calculation)
    country_code = Column(String(2), nullable=True)  # ISO country code
    postal_code = Column(String(20), nullable=True)
    region = Column(String(100), nullable=True)

    # Metadata
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", backref="paddle_customer")

    def __repr__(self) -> str:
        return f"<PaddleCustomer(id={self.id}, paddle_id={self.paddle_customer_id}, email={self.email})>"


class PaddleWebhookEvent(Base):
    """Paddle webhook event log - for idempotency and debugging."""

    __tablename__ = "paddle_webhook_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Event identifiers
    paddle_event_id = Column(String(255), nullable=False, unique=True)
    event_type = Column(String(100), nullable=False)  # subscription.created, transaction.completed, etc.

    # Related resources
    paddle_customer_id = Column(String(255), nullable=True)
    paddle_subscription_id = Column(String(255), nullable=True)
    paddle_transaction_id = Column(String(255), nullable=True)

    # Processing status
    status = Column(String(50), nullable=False, server_default="pending")  # pending, processed, failed, ignored
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Raw payload
    payload = Column(JSONB, nullable=False)

    # Timestamps
    occurred_at = Column(DateTime(timezone=True), nullable=False)  # When Paddle created the event
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PaddleWebhookEvent(id={self.id}, type={self.event_type}, status={self.status})>"
