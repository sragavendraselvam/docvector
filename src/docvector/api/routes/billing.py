"""Billing API routes."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from docvector.api.middleware.auth import AuthContext, require_user
from docvector.api.schemas.billing import (
    BillingOverviewResponse,
    CancelSubscriptionRequest,
    CheckoutResponse,
    CreateCheckoutRequest,
    CustomerPortalResponse,
    PlanInfo,
    PLANS,
    PLAN_FEATURES,
    SubscriptionResponse,
    TransactionListResponse,
    TransactionResponse,
    UpdateSubscriptionRequest,
    UsageResponse,
)
from docvector.core import DocVectorException, get_logger, settings
from docvector.db import get_db_session
from docvector.services.billing_service import BillingService

logger = get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ============ Plans ============


@router.get("/plans", response_model=list[PlanInfo])
async def list_plans():
    """List all available billing plans."""
    return PLANS


@router.get("/plans/{plan_id}", response_model=PlanInfo)
async def get_plan(plan_id: str):
    """Get details for a specific plan."""
    for plan in PLANS:
        if plan.id == plan_id:
            return plan
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Plan '{plan_id}' not found",
    )


# ============ Subscription Management ============


@router.get("/subscription", response_model=Optional[SubscriptionResponse])
async def get_subscription(
    auth: AuthContext = Depends(require_user),
):
    """Get current subscription for the user's organization."""
    if not auth.organization_id:
        # User without org - return None (free tier)
        return None

    async with get_db_session() as db:
        billing_service = BillingService(db)
        subscription = await billing_service.get_subscription(auth.organization_id)
        return subscription


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: Request,
    data: CreateCheckoutRequest,
    auth: AuthContext = Depends(require_user),
):
    """Create a Paddle checkout session for subscription."""
    if data.plan not in ["starter", "pro", "enterprise"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan. Must be one of: starter, pro, enterprise",
        )

    if data.billing_cycle not in ["monthly", "yearly"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid billing cycle. Must be: monthly or yearly",
        )

    # Determine success URL
    success_url = data.success_url
    if not success_url:
        # Default to referring page or a standard success page
        referer = request.headers.get("referer", "")
        success_url = f"{referer}?checkout=success" if referer else "/billing/success"

    async with get_db_session() as db:
        billing_service = BillingService(db)

        try:
            # Create or get organization for user
            org_id = auth.organization_id
            if not org_id:
                # Create a personal organization for the user
                from docvector.models import Organization

                org = Organization(
                    slug=f"personal-{auth.user.id}",
                    name=f"{auth.user.display_name or auth.user.username}'s Organization",
                    plan="free",
                )
                db.add(org)
                await db.commit()
                await db.refresh(org)
                org_id = org.id

            checkout_url = await billing_service.create_checkout_url(
                organization_id=org_id,
                plan=data.plan,
                billing_cycle=data.billing_cycle,
                success_url=success_url,
            )

            return CheckoutResponse(checkout_url=checkout_url)

        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


@router.patch("/subscription", response_model=SubscriptionResponse)
async def update_subscription(
    data: UpdateSubscriptionRequest,
    auth: AuthContext = Depends(require_user),
):
    """Update subscription plan or billing cycle."""
    if not auth.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to update",
        )

    if data.plan and data.plan not in ["starter", "pro", "enterprise"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan",
        )

    if data.billing_cycle and data.billing_cycle not in ["monthly", "yearly"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid billing cycle",
        )

    async with get_db_session() as db:
        billing_service = BillingService(db)

        try:
            subscription = await billing_service.update_subscription(
                organization_id=auth.organization_id,
                new_plan=data.plan,
                new_billing_cycle=data.billing_cycle,
            )
            return subscription
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    data: CancelSubscriptionRequest,
    auth: AuthContext = Depends(require_user),
):
    """Cancel the current subscription."""
    if not auth.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to cancel",
        )

    async with get_db_session() as db:
        billing_service = BillingService(db)

        try:
            subscription = await billing_service.cancel_subscription(
                organization_id=auth.organization_id,
                effective_from=data.effective_from,
            )
            return subscription
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


@router.post("/subscription/pause", response_model=SubscriptionResponse)
async def pause_subscription(
    auth: AuthContext = Depends(require_user),
):
    """Pause the current subscription."""
    if not auth.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to pause",
        )

    async with get_db_session() as db:
        billing_service = BillingService(db)

        try:
            subscription = await billing_service.pause_subscription(auth.organization_id)
            return subscription
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


@router.post("/subscription/resume", response_model=SubscriptionResponse)
async def resume_subscription(
    auth: AuthContext = Depends(require_user),
):
    """Resume a paused subscription."""
    if not auth.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription to resume",
        )

    async with get_db_session() as db:
        billing_service = BillingService(db)

        try:
            subscription = await billing_service.resume_subscription(auth.organization_id)
            return subscription
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


# ============ Customer Portal ============


@router.get("/portal", response_model=CustomerPortalResponse)
async def get_customer_portal(
    auth: AuthContext = Depends(require_user),
):
    """Get Paddle customer portal URL for managing payment methods and invoices."""
    if not auth.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found",
        )

    async with get_db_session() as db:
        billing_service = BillingService(db)

        try:
            portal_url = await billing_service.get_billing_portal_url(auth.organization_id)
            return CustomerPortalResponse(portal_url=portal_url)
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


# ============ Transactions ============


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = 20,
    offset: int = 0,
    auth: AuthContext = Depends(require_user),
):
    """List billing transactions/invoices."""
    if not auth.organization_id:
        return TransactionListResponse(transactions=[], total=0, limit=limit, offset=offset)

    async with get_db_session() as db:
        billing_service = BillingService(db)
        transactions = await billing_service.get_transactions(
            organization_id=auth.organization_id,
            limit=limit,
            offset=offset,
        )

        return TransactionListResponse(
            transactions=[TransactionResponse.model_validate(t) for t in transactions],
            total=len(transactions),  # TODO: Get actual total count
            limit=limit,
            offset=offset,
        )


# ============ Usage & Overview ============


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    auth: AuthContext = Depends(require_user),
):
    """Get current usage statistics for the billing period."""
    # TODO: Implement actual usage tracking
    plan = "free"
    features = PLAN_FEATURES[plan]

    if auth.organization_id:
        async with get_db_session() as db:
            from docvector.models import Organization

            org = await db.get(Organization, auth.organization_id)
            if org:
                plan = org.plan or "free"
                features = PLAN_FEATURES.get(plan, PLAN_FEATURES["free"])

    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        period_end = period_start.replace(year=now.year + 1, month=1)
    else:
        period_end = period_start.replace(month=now.month + 1)

    return UsageResponse(
        organization_id=auth.organization_id or auth.user.id,
        plan=plan,
        current_period_start=period_start,
        current_period_end=period_end,
        api_calls=0,  # TODO: Track actual usage
        api_calls_limit=features.max_api_calls_per_month,
        documents=0,  # TODO: Count actual documents
        documents_limit=features.max_documents,
        team_members=1,  # TODO: Count actual team members
        team_members_limit=features.max_team_members,
    )


@router.get("/overview", response_model=BillingOverviewResponse)
async def get_billing_overview(
    auth: AuthContext = Depends(require_user),
):
    """Get complete billing overview including subscription, usage, and payment info."""
    subscription = None
    usage = None

    if auth.organization_id:
        async with get_db_session() as db:
            billing_service = BillingService(db)
            subscription = await billing_service.get_subscription(auth.organization_id)

    # Get usage (works for all users)
    usage_response = await get_usage(auth)

    return BillingOverviewResponse(
        subscription=SubscriptionResponse.model_validate(subscription) if subscription else None,
        usage=usage_response,
    )


# ============ Paddle Webhooks ============


@router.post("/webhooks/paddle")
async def paddle_webhook(request: Request):
    """
    Handle Paddle webhook events.

    Paddle sends webhooks for subscription lifecycle events:
    - subscription.created
    - subscription.updated
    - subscription.canceled
    - subscription.paused
    - subscription.resumed
    - subscription.past_due
    - transaction.completed
    - transaction.payment_failed
    """
    # Get raw body for signature verification
    body = await request.body()
    signature = request.headers.get("Paddle-Signature", "")

    async with get_db_session() as db:
        billing_service = BillingService(db)

        # Verify webhook signature
        if settings.paddle_webhook_secret:
            if not billing_service.verify_webhook_signature(body.decode(), signature):
                logger.warning("Invalid Paddle webhook signature")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature",
                )

        # Parse webhook payload
        import json

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        event_type = payload.get("event_type")
        data = payload.get("data", {})

        logger.info("Received Paddle webhook", event_type=event_type)

        try:
            # Process the webhook
            success = await billing_service.process_webhook(event_type, data)

            if success:
                return {"status": "processed", "event_type": event_type}
            else:
                return {"status": "ignored", "event_type": event_type}

        except DocVectorException as e:
            logger.error("Error processing Paddle webhook", error=e.message)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message,
            )


# ============ Paddle Client Token (for frontend) ============


@router.get("/paddle-config")
async def get_paddle_config():
    """
    Get Paddle configuration for frontend checkout.

    Returns the client token and environment needed to initialize
    Paddle.js on the frontend.
    """
    if not settings.paddle_client_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paddle billing not configured",
        )

    return {
        "client_token": settings.paddle_client_token,
        "environment": settings.paddle_environment,
        "seller_id": None,  # Optional: Add if needed
    }
