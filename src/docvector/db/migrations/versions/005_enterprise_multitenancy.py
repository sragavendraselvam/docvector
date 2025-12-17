"""Add enterprise multi-tenancy models.

This migration adds:
- users table for authentication
- organizations table for multi-tenancy
- org_members junction table
- api_keys table for API access
- user_sessions table for session management
- usage_events table for metering
- audit_logs table for security tracking

Revision ID: 005
Revises: 004
Create Date: 2025-12-02

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade database schema."""

    # Create users table
    if not table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            # Identity
            sa.Column("email", sa.String(255), nullable=False, unique=True),
            sa.Column("username", sa.String(100), nullable=True, unique=True),
            sa.Column("display_name", sa.String(255), nullable=True),
            sa.Column("avatar_url", sa.String(2048), nullable=True),
            # Authentication
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
            # Account type
            sa.Column("account_type", sa.String(50), nullable=False, server_default="user"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
            # OAuth
            sa.Column("oauth_providers", postgresql.JSONB, nullable=False, server_default="{}"),
            # Reputation
            sa.Column("reputation", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("questions_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("answers_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accepted_answers_count", sa.Integer(), nullable=False, server_default="0"),
            # Preferences
            sa.Column("preferences", postgresql.JSONB, nullable=False, server_default="{}"),
            # Timestamps
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_users_email", "users", ["email"])
        op.create_index("idx_users_username", "users", ["username"])

    # Create organizations table
    if not table_exists("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            # Identity
            sa.Column("slug", sa.String(100), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("logo_url", sa.String(2048), nullable=True),
            sa.Column("website_url", sa.String(2048), nullable=True),
            # Owner
            sa.Column(
                "owner_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Subscription
            sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
            sa.Column("plan_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("stripe_customer_id", sa.String(255), nullable=True, unique=True),
            sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
            # Quotas
            sa.Column("max_members", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("max_api_keys", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("max_sources", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("max_documents", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("max_queries_per_day", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("max_storage_mb", sa.Integer(), nullable=False, server_default="100"),
            # Usage
            sa.Column("current_members", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_sources", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_documents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_storage_mb", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("queries_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("queries_reset_at", sa.DateTime(timezone=True), nullable=True),
            # Settings
            sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            # Timestamps
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_organizations_slug", "organizations", ["slug"])
        op.create_index("idx_organizations_owner", "organizations", ["owner_id"])

    # Create org_members junction table
    if not table_exists("org_members"):
        op.create_table(
            "org_members",
            sa.Column(
                "org_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("role", sa.String(50), nullable=False, server_default="member"),
            sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_org_members_user", "org_members", ["user_id"])
        op.create_index("idx_org_members_org", "org_members", ["org_id"])

    # Create api_keys table
    if not table_exists("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            # Key identity
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("key_prefix", sa.String(12), nullable=False),
            sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
            # Ownership
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
            # Permissions
            sa.Column("scopes", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
            sa.Column("allowed_ips", postgresql.ARRAY(sa.String), nullable=True),
            sa.Column("allowed_origins", postgresql.ARRAY(sa.String), nullable=True),
            # Rate limiting
            sa.Column("rate_limit_per_second", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("rate_limit_per_day", sa.Integer(), nullable=True),
            # Status
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            # Usage
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_ip", sa.String(45), nullable=True),
            sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("requests_today", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("requests_reset_at", sa.DateTime(timezone=True), nullable=True),
            # Timestamps
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_api_keys_user", "api_keys", ["user_id"])
        op.create_index("idx_api_keys_org", "api_keys", ["organization_id"])
        op.create_index("idx_api_keys_prefix", "api_keys", ["key_prefix"])

    # Create user_sessions table
    if not table_exists("user_sessions"):
        op.create_table(
            "user_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
            # Metadata
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column("device_info", postgresql.JSONB, nullable=True),
            # Status
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            # Timestamps
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_user_sessions_user", "user_sessions", ["user_id"])
        op.create_index("idx_user_sessions_expires", "user_sessions", ["expires_at"])

    # Create usage_events table
    if not table_exists("usage_events"):
        op.create_table(
            "usage_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            # Who
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
            # What
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=True),
            sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Metering
            sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_type", sa.String(50), nullable=False, server_default="request"),
            # Context
            sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
            sa.Column("ip_address", sa.String(45), nullable=True),
            # Timestamp
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_usage_events_user", "usage_events", ["user_id"])
        op.create_index("idx_usage_events_org", "usage_events", ["organization_id"])
        op.create_index("idx_usage_events_created", "usage_events", ["created_at"])
        op.create_index("idx_usage_events_type", "usage_events", ["event_type"])

    # Create audit_logs table
    if not table_exists("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            # Actor
            sa.Column("actor_type", sa.String(50), nullable=False),
            sa.Column("actor_id", sa.String(255), nullable=False),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Action
            sa.Column("action", sa.String(100), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=True),
            sa.Column("resource_id", sa.String(255), nullable=True),
            # Details
            sa.Column("changes", postgresql.JSONB, nullable=True),
            sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
            # Context
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            # Result
            sa.Column("status", sa.String(50), nullable=False, server_default="success"),
            sa.Column("error_message", sa.Text(), nullable=True),
            # Timestamp
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_type", "actor_id"])
        op.create_index("idx_audit_logs_org", "audit_logs", ["organization_id"])
        op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
        op.create_index("idx_audit_logs_created", "audit_logs", ["created_at"])


def downgrade() -> None:
    """Downgrade database schema."""

    # Drop tables in reverse order
    if table_exists("audit_logs"):
        op.drop_index("idx_audit_logs_created")
        op.drop_index("idx_audit_logs_action")
        op.drop_index("idx_audit_logs_org")
        op.drop_index("idx_audit_logs_actor")
        op.drop_table("audit_logs")

    if table_exists("usage_events"):
        op.drop_index("idx_usage_events_type")
        op.drop_index("idx_usage_events_created")
        op.drop_index("idx_usage_events_org")
        op.drop_index("idx_usage_events_user")
        op.drop_table("usage_events")

    if table_exists("user_sessions"):
        op.drop_index("idx_user_sessions_expires")
        op.drop_index("idx_user_sessions_user")
        op.drop_table("user_sessions")

    if table_exists("api_keys"):
        op.drop_index("idx_api_keys_prefix")
        op.drop_index("idx_api_keys_org")
        op.drop_index("idx_api_keys_user")
        op.drop_table("api_keys")

    if table_exists("org_members"):
        op.drop_index("idx_org_members_org")
        op.drop_index("idx_org_members_user")
        op.drop_table("org_members")

    if table_exists("organizations"):
        op.drop_index("idx_organizations_owner")
        op.drop_index("idx_organizations_slug")
        op.drop_table("organizations")

    if table_exists("users"):
        op.drop_index("idx_users_username")
        op.drop_index("idx_users_email")
        op.drop_table("users")
