"""Add external source tracking and comments to Q&A models.

This migration adds:
- External source fields to questions (source, source_id, source_url, library_name, is_answered, answered_at)
- External source fields to answers (source, source_id, source_url, code_snippets, is_verified, verification_proof)
- Comments table for threaded discussions
- Proof-of-work fields to votes (pow_nonce, pow_hash, pow_difficulty)
- ProofOfWorkChallenge table for challenge management

Revision ID: 004
Revises: 003
Create Date: 2025-12-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade database schema."""

    # Add external source fields to questions
    if not column_exists("questions", "source"):
        op.add_column(
            "questions",
            sa.Column("source", sa.String(50), nullable=False, server_default="internal"),
        )
    if not column_exists("questions", "source_id"):
        op.add_column(
            "questions",
            sa.Column("source_id", sa.String(255), nullable=True),
        )
    if not column_exists("questions", "source_url"):
        op.add_column(
            "questions",
            sa.Column("source_url", sa.String(2048), nullable=True),
        )
    if not column_exists("questions", "library_name"):
        op.add_column(
            "questions",
            sa.Column("library_name", sa.String(255), nullable=True),
        )
    if not column_exists("questions", "is_answered"):
        op.add_column(
            "questions",
            sa.Column("is_answered", sa.Boolean(), nullable=False, server_default="false"),
        )
    if not column_exists("questions", "answered_at"):
        op.add_column(
            "questions",
            sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Create index on source (ignore if exists)
    try:
        op.create_index("idx_questions_source", "questions", ["source"])
    except Exception:
        pass  # Index may already exist

    # Add external source fields to answers
    if not column_exists("answers", "source"):
        op.add_column(
            "answers",
            sa.Column("source", sa.String(50), nullable=False, server_default="internal"),
        )
    if not column_exists("answers", "source_id"):
        op.add_column(
            "answers",
            sa.Column("source_id", sa.String(255), nullable=True),
        )
    if not column_exists("answers", "source_url"):
        op.add_column(
            "answers",
            sa.Column("source_url", sa.String(2048), nullable=True),
        )
    if not column_exists("answers", "code_snippets"):
        op.add_column(
            "answers",
            sa.Column("code_snippets", postgresql.JSONB, nullable=True, server_default="[]"),
        )
    if not column_exists("answers", "is_verified"):
        op.add_column(
            "answers",
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        )
    if not column_exists("answers", "verification_proof"):
        op.add_column(
            "answers",
            sa.Column("verification_proof", postgresql.JSONB, nullable=True),
        )

    # Create comments table if it doesn't exist
    if not table_exists("comments"):
        op.create_table(
            "comments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "question_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("questions.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "answer_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("answers.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "parent_comment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("comments.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("source", sa.String(50), nullable=False, server_default="internal"),
            sa.Column("source_id", sa.String(255), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("author_id", sa.String(255), nullable=False),
            sa.Column("author_type", sa.String(50), nullable=False, server_default="agent"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("idx_comments_question_id", "comments", ["question_id"])
        op.create_index("idx_comments_answer_id", "comments", ["answer_id"])
        op.create_index("idx_comments_parent", "comments", ["parent_comment_id"])

    # Add proof-of-work fields to votes
    if not column_exists("votes", "pow_nonce"):
        op.add_column(
            "votes",
            sa.Column("pow_nonce", sa.String(64), nullable=True),
        )
    if not column_exists("votes", "pow_hash"):
        op.add_column(
            "votes",
            sa.Column("pow_hash", sa.String(64), nullable=True),
        )
    if not column_exists("votes", "pow_difficulty"):
        op.add_column(
            "votes",
            sa.Column("pow_difficulty", sa.Integer(), nullable=True),
        )

    # Create proof-of-work challenges table if it doesn't exist
    if not table_exists("pow_challenges"):
        op.create_table(
            "pow_challenges",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("challenge", sa.String(255), nullable=False, unique=True),
            sa.Column("action", sa.String(50), nullable=False),  # question, answer, comment, vote
            sa.Column("target_id", sa.String(255), nullable=True),
            sa.Column("agent_id", sa.String(255), nullable=False),
            sa.Column("difficulty", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_pow_challenges_agent", "pow_challenges", ["agent_id"])
        op.create_index("idx_pow_challenges_expires", "pow_challenges", ["expires_at"])


def downgrade() -> None:
    """Downgrade database schema."""

    # Drop pow_challenges table
    if table_exists("pow_challenges"):
        op.drop_index("idx_pow_challenges_expires")
        op.drop_index("idx_pow_challenges_agent")
        op.drop_table("pow_challenges")

    # Drop proof-of-work fields from votes
    if column_exists("votes", "pow_difficulty"):
        op.drop_column("votes", "pow_difficulty")
    if column_exists("votes", "pow_hash"):
        op.drop_column("votes", "pow_hash")
    if column_exists("votes", "pow_nonce"):
        op.drop_column("votes", "pow_nonce")

    # Drop comments table
    if table_exists("comments"):
        op.drop_index("idx_comments_parent")
        op.drop_index("idx_comments_answer_id")
        op.drop_index("idx_comments_question_id")
        op.drop_table("comments")

    # Drop external source fields from answers
    if column_exists("answers", "verification_proof"):
        op.drop_column("answers", "verification_proof")
    if column_exists("answers", "is_verified"):
        op.drop_column("answers", "is_verified")
    if column_exists("answers", "code_snippets"):
        op.drop_column("answers", "code_snippets")
    if column_exists("answers", "source_url"):
        op.drop_column("answers", "source_url")
    if column_exists("answers", "source_id"):
        op.drop_column("answers", "source_id")
    if column_exists("answers", "source"):
        op.drop_column("answers", "source")

    # Drop external source fields from questions
    try:
        op.drop_index("idx_questions_source")
    except Exception:
        pass
    if column_exists("questions", "answered_at"):
        op.drop_column("questions", "answered_at")
    if column_exists("questions", "is_answered"):
        op.drop_column("questions", "is_answered")
    if column_exists("questions", "library_name"):
        op.drop_column("questions", "library_name")
    if column_exists("questions", "source_url"):
        op.drop_column("questions", "source_url")
    if column_exists("questions", "source_id"):
        op.drop_column("questions", "source_id")
    if column_exists("questions", "source"):
        op.drop_column("questions", "source")
