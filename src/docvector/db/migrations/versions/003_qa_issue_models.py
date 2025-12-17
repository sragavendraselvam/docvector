"""Add Q&A and Issue models for Stack Overflow-style functionality.

This migration adds:
- questions: User/agent submitted questions about libraries
- answers: Answers to questions (can be marked as accepted solution)
- issues: Bug reports and problems with reproducible examples
- solutions: Solutions to issues with validation status
- votes: Upvotes/downvotes on questions, answers, issues, solutions
- tags: Reusable tags for categorization
- question_tags/issue_tags: Many-to-many relationships for tags

Revision ID: 003
Revises: 002
Create Date: 2025-12-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""

    # Create tags table first (referenced by other tables)
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),  # framework, language, topic, etc.
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_tags_name", "tags", ["name"])
    op.create_index("idx_tags_category", "tags", ["category"])

    # Create questions table
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),  # Rendered markdown

        # Library association
        sa.Column(
            "library_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("libraries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("library_version", sa.String(50), nullable=True),

        # Author info (placeholder for future auth - using string identifier for now)
        sa.Column("author_id", sa.String(255), nullable=False),  # Agent ID or user ID
        sa.Column("author_type", sa.String(50), nullable=False, server_default="agent"),  # agent, user

        # Status and scoring
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),  # open, answered, closed
        sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_answer_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Embedding for semantic search
        sa.Column("embedding_id", sa.String(255), nullable=True),

        # Metadata
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_questions_library_id", "questions", ["library_id"])
    op.create_index("idx_questions_author_id", "questions", ["author_id"])
    op.create_index("idx_questions_status", "questions", ["status"])
    op.create_index("idx_questions_vote_score", "questions", ["vote_score"])
    op.create_index("idx_questions_created_at", "questions", ["created_at"])

    # Create answers table
    op.create_table(
        "answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),

        # Author info
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("author_type", sa.String(50), nullable=False, server_default="agent"),

        # Status and scoring
        sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),

        # Code validation (for AI-submitted answers)
        sa.Column("validation_status", sa.String(50), nullable=True),  # pending, validated, failed
        sa.Column("validation_details", postgresql.JSONB, nullable=True),

        # Embedding for semantic search
        sa.Column("embedding_id", sa.String(255), nullable=True),

        # Metadata
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_answers_question_id", "answers", ["question_id"])
    op.create_index("idx_answers_author_id", "answers", ["author_id"])
    op.create_index("idx_answers_is_accepted", "answers", ["is_accepted"])
    op.create_index("idx_answers_vote_score", "answers", ["vote_score"])

    # Add foreign key for accepted_answer_id in questions
    op.create_foreign_key(
        "fk_questions_accepted_answer",
        "questions",
        "answers",
        ["accepted_answer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create issues table (bug reports with reproducible examples)
    op.create_table(
        "issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_html", sa.Text(), nullable=True),

        # Library association
        sa.Column(
            "library_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("libraries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("library_version", sa.String(50), nullable=True),

        # Reproduction details
        sa.Column("steps_to_reproduce", sa.Text(), nullable=True),
        sa.Column("expected_behavior", sa.Text(), nullable=True),
        sa.Column("actual_behavior", sa.Text(), nullable=True),
        sa.Column("code_snippet", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),

        # Environment info
        sa.Column("environment", postgresql.JSONB, nullable=True),  # OS, runtime, dependencies

        # Author info
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("author_type", sa.String(50), nullable=False, server_default="agent"),

        # Status and scoring
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),  # open, confirmed, resolved, closed, duplicate
        sa.Column("severity", sa.String(50), nullable=True),  # critical, major, minor, trivial
        sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_solution_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Reproducibility validation
        sa.Column("is_reproducible", sa.Boolean(), nullable=True),
        sa.Column("reproduction_count", sa.Integer(), nullable=False, server_default="0"),

        # Embedding for semantic search
        sa.Column("embedding_id", sa.String(255), nullable=True),

        # External references (GitHub issue, etc.)
        sa.Column("external_url", sa.String(2048), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),

        # Metadata
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_issues_library_id", "issues", ["library_id"])
    op.create_index("idx_issues_author_id", "issues", ["author_id"])
    op.create_index("idx_issues_status", "issues", ["status"])
    op.create_index("idx_issues_severity", "issues", ["severity"])
    op.create_index("idx_issues_vote_score", "issues", ["vote_score"])
    op.create_index("idx_issues_created_at", "issues", ["created_at"])

    # Create solutions table
    op.create_table(
        "solutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("code_snippet", sa.Text(), nullable=True),

        # Author info
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("author_type", sa.String(50), nullable=False, server_default="agent"),

        # Status and scoring
        sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),

        # Validation (did this actually fix the issue?)
        sa.Column("validation_status", sa.String(50), nullable=True),  # pending, validated, failed
        sa.Column("validation_details", postgresql.JSONB, nullable=True),
        sa.Column("works_count", sa.Integer(), nullable=False, server_default="0"),  # "This worked for me"
        sa.Column("doesnt_work_count", sa.Integer(), nullable=False, server_default="0"),

        # Embedding for semantic search
        sa.Column("embedding_id", sa.String(255), nullable=True),

        # Metadata
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_solutions_issue_id", "solutions", ["issue_id"])
    op.create_index("idx_solutions_author_id", "solutions", ["author_id"])
    op.create_index("idx_solutions_is_accepted", "solutions", ["is_accepted"])
    op.create_index("idx_solutions_vote_score", "solutions", ["vote_score"])

    # Add foreign key for accepted_solution_id in issues
    op.create_foreign_key(
        "fk_issues_accepted_solution",
        "issues",
        "solutions",
        ["accepted_solution_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create votes table (polymorphic voting for questions, answers, issues, solutions)
    op.create_table(
        "votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # What is being voted on (polymorphic)
        sa.Column("target_type", sa.String(50), nullable=False),  # question, answer, issue, solution
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Who voted
        sa.Column("voter_id", sa.String(255), nullable=False),
        sa.Column("voter_type", sa.String(50), nullable=False, server_default="agent"),

        # Vote value
        sa.Column("value", sa.Integer(), nullable=False),  # +1 (upvote) or -1 (downvote)

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_votes_target", "votes", ["target_type", "target_id"])
    op.create_index("idx_votes_voter", "votes", ["voter_id"])
    # Unique constraint: one vote per user per target
    op.create_unique_constraint(
        "uq_votes_voter_target",
        "votes",
        ["voter_id", "target_type", "target_id"],
    )

    # Create question_tags junction table
    op.create_table(
        "question_tags",
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # Create issue_tags junction table
    op.create_table(
        "issue_tags",
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop junction tables first
    op.drop_table("issue_tags")
    op.drop_table("question_tags")

    # Drop votes table
    op.drop_constraint("uq_votes_voter_target", "votes", type_="unique")
    op.drop_index("idx_votes_voter")
    op.drop_index("idx_votes_target")
    op.drop_table("votes")

    # Drop foreign key from issues before dropping solutions
    op.drop_constraint("fk_issues_accepted_solution", "issues", type_="foreignkey")

    # Drop solutions table
    op.drop_index("idx_solutions_vote_score")
    op.drop_index("idx_solutions_is_accepted")
    op.drop_index("idx_solutions_author_id")
    op.drop_index("idx_solutions_issue_id")
    op.drop_table("solutions")

    # Drop issues table
    op.drop_index("idx_issues_created_at")
    op.drop_index("idx_issues_vote_score")
    op.drop_index("idx_issues_severity")
    op.drop_index("idx_issues_status")
    op.drop_index("idx_issues_author_id")
    op.drop_index("idx_issues_library_id")
    op.drop_table("issues")

    # Drop foreign key from questions before dropping answers
    op.drop_constraint("fk_questions_accepted_answer", "questions", type_="foreignkey")

    # Drop answers table
    op.drop_index("idx_answers_vote_score")
    op.drop_index("idx_answers_is_accepted")
    op.drop_index("idx_answers_author_id")
    op.drop_index("idx_answers_question_id")
    op.drop_table("answers")

    # Drop questions table
    op.drop_index("idx_questions_created_at")
    op.drop_index("idx_questions_vote_score")
    op.drop_index("idx_questions_status")
    op.drop_index("idx_questions_author_id")
    op.drop_index("idx_questions_library_id")
    op.drop_table("questions")

    # Drop tags table
    op.drop_index("idx_tags_category")
    op.drop_index("idx_tags_name")
    op.drop_table("tags")
