"""Billing API schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============ Plan Enums ============


class BillingPlan:
    """Available billing plans."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class BillingCycle:
    """Billing cycle options."""

    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus:
    """Subscription status values."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELED = "canceled"
    TRIALING = "trialing"


# ============ Request Schemas ============


class CreateCheckoutRequest(BaseModel):
    """Request to create a checkout session."""

    plan: str = Field(..., description="Plan to subscribe to (starter, pro, enterprise)")
    billing_cycle: str = Field(default="monthly", description="Billing cycle (monthly, yearly)")
    success_url: Optional[str] = Field(
        default=None, description="URL to redirect after successful checkout"
    )
    cancel_url: Optional[str] = Field(
        default=None, description="URL to redirect after cancelled checkout"
    )


class UpdateSubscriptionRequest(BaseModel):
    """Request to update subscription."""

    plan: Optional[str] = Field(default=None, description="New plan")
    billing_cycle: Optional[str] = Field(default=None, description="New billing cycle")


class CancelSubscriptionRequest(BaseModel):
    """Request to cancel subscription."""

    effective_from: str = Field(
        default="next_billing_period",
        description="When to cancel: 'immediately' or 'next_billing_period'",
    )
    reason: Optional[str] = Field(default=None, description="Cancellation reason")


# ============ Response Schemas ============


class PlanFeatures(BaseModel):
    """Features included in a plan."""

    max_documents: int
    max_api_calls_per_month: int
    max_team_members: int
    priority_support: bool
    custom_embeddings: bool
    sso: bool
    audit_logs: bool
    sla: Optional[str] = None


class PlanInfo(BaseModel):
    """Information about a billing plan."""

    id: str
    name: str
    description: str
    price_monthly: float
    price_yearly: float
    features: PlanFeatures


class SubscriptionResponse(BaseModel):
    """Subscription details response."""

    id: UUID
    organization_id: UUID
    plan: str
    billing_cycle: str
    status: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    canceled_at: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    paddle_subscription_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CheckoutResponse(BaseModel):
    """Checkout session response."""

    checkout_url: str
    paddle_transaction_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class CustomerPortalResponse(BaseModel):
    """Customer portal URL response."""

    portal_url: str


class TransactionResponse(BaseModel):
    """Transaction details response."""

    id: UUID
    organization_id: UUID
    paddle_transaction_id: str
    status: str
    amount: float
    currency: str
    tax_amount: Optional[float] = None
    payment_method: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """List of transactions response."""

    transactions: list[TransactionResponse]
    total: int
    limit: int
    offset: int


class UsageResponse(BaseModel):
    """Current usage response."""

    organization_id: UUID
    plan: str
    current_period_start: datetime
    current_period_end: datetime
    api_calls: int
    api_calls_limit: int
    documents: int
    documents_limit: int
    team_members: int
    team_members_limit: int


class BillingOverviewResponse(BaseModel):
    """Complete billing overview."""

    subscription: Optional[SubscriptionResponse] = None
    usage: Optional[UsageResponse] = None
    upcoming_invoice: Optional[dict] = None
    payment_method: Optional[dict] = None


# ============ Plan Definitions ============


PLAN_FEATURES = {
    "free": PlanFeatures(
        max_documents=100,
        max_api_calls_per_month=1000,
        max_team_members=1,
        priority_support=False,
        custom_embeddings=False,
        sso=False,
        audit_logs=False,
    ),
    "starter": PlanFeatures(
        max_documents=1000,
        max_api_calls_per_month=10000,
        max_team_members=3,
        priority_support=False,
        custom_embeddings=False,
        sso=False,
        audit_logs=False,
    ),
    "pro": PlanFeatures(
        max_documents=10000,
        max_api_calls_per_month=100000,
        max_team_members=10,
        priority_support=True,
        custom_embeddings=True,
        sso=False,
        audit_logs=True,
    ),
    "enterprise": PlanFeatures(
        max_documents=-1,  # Unlimited
        max_api_calls_per_month=-1,  # Unlimited
        max_team_members=-1,  # Unlimited
        priority_support=True,
        custom_embeddings=True,
        sso=True,
        audit_logs=True,
        sla="99.9%",
    ),
}

PLANS = [
    PlanInfo(
        id="free",
        name="Free",
        description="For individuals and small projects",
        price_monthly=0,
        price_yearly=0,
        features=PLAN_FEATURES["free"],
    ),
    PlanInfo(
        id="starter",
        name="Starter",
        description="For growing teams",
        price_monthly=29,
        price_yearly=290,  # ~2 months free
        features=PLAN_FEATURES["starter"],
    ),
    PlanInfo(
        id="pro",
        name="Pro",
        description="For professional teams",
        price_monthly=99,
        price_yearly=990,  # ~2 months free
        features=PLAN_FEATURES["pro"],
    ),
    PlanInfo(
        id="enterprise",
        name="Enterprise",
        description="For large organizations",
        price_monthly=499,
        price_yearly=4990,  # ~2 months free
        features=PLAN_FEATURES["enterprise"],
    ),
]
