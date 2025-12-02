"""Paddle billing tables.

Revision ID: 006
Revises: 005
Create Date: 2024-01-15

This migration adds Paddle billing tables for subscription management:
- subscriptions: Active subscriptions linked to organizations
- transactions: Payment transaction history
- paddle_customers: Paddle customer records linked to organizations
- paddle_webhook_events: Webhook event log for idempotency and debugging
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Paddle Customers - link organizations to Paddle customer IDs
    op.create_table(
        "paddle_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paddle_customer_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_paddle_customers_org", "paddle_customers", ["organization_id"])

    # Subscriptions - active subscription records
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paddle_subscription_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("paddle_customer_id", sa.String(64), nullable=False, index=True),
        sa.Column("paddle_price_id", sa.String(64), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),  # free, starter, pro, enterprise
        sa.Column("billing_cycle", sa.String(16), nullable=False, server_default="monthly"),  # monthly, yearly
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),  # active, past_due, paused, canceled, trialing
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unit_price", sa.Integer(), nullable=True),  # Amount in cents
        sa.Column("currency", sa.String(3), nullable=True, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_subscriptions_org", "subscriptions", ["organization_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # Transactions - payment transaction history
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paddle_transaction_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("paddle_invoice_id", sa.String(64), nullable=True, index=True),
        sa.Column("paddle_customer_id", sa.String(64), nullable=False, index=True),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),  # completed, pending, failed, refunded
        sa.Column("origin", sa.String(32), nullable=True),  # subscription, one_time
        sa.Column("subtotal", sa.Integer(), nullable=True),  # Amount in cents
        sa.Column("tax", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True, server_default="USD"),
        sa.Column("items", postgresql.JSONB, nullable=True),  # Line items
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invoice_url", sa.Text(), nullable=True),
        sa.Column("receipt_url", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_transactions_org", "transactions", ["organization_id"])
    op.create_index("ix_transactions_subscription", "transactions", ["subscription_id"])

    # Paddle Webhook Events - for idempotency and debugging
    op.create_table(
        "paddle_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paddle_event_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("paddle_customer_id", sa.String(64), nullable=True, index=True),
        sa.Column("paddle_subscription_id", sa.String(64), nullable=True, index=True),
        sa.Column("paddle_transaction_id", sa.String(64), nullable=True, index=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, processed, failed, ignored
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_paddle_webhook_events_type_status", "paddle_webhook_events", ["event_type", "status"])


def downgrade() -> None:
    op.drop_table("paddle_webhook_events")
    op.drop_table("transactions")
    op.drop_table("subscriptions")
    op.drop_table("paddle_customers")
