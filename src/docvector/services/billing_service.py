"""Paddle Billing Service - subscription management and payment processing.

Paddle is a Merchant of Record (MoR) that handles:
- Global payment processing
- Sales tax, VAT, and GST compliance
- Invoicing and receipts
- Subscription management
- Dunning (failed payment recovery)

This service wraps the Paddle API and syncs data to our database.
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from docvector.core import DocVectorException, get_logger, settings
from docvector.models import (
    Organization,
    PaddleCustomer,
    PaddleWebhookEvent,
    Subscription,
    Transaction,
)

logger = get_logger(__name__)

# Paddle API base URLs
PADDLE_API_URLS = {
    "sandbox": "https://sandbox-api.paddle.com",
    "production": "https://api.paddle.com",
}

# Plan quotas
PLAN_QUOTAS = {
    "free": {
        "max_members": 1,
        "max_api_keys": 1,
        "max_sources": 3,
        "max_documents": 100,
        "max_queries_per_day": 100,
        "max_storage_mb": 10,
    },
    "starter": {
        "max_members": 5,
        "max_api_keys": 5,
        "max_sources": 20,
        "max_documents": 5000,
        "max_queries_per_day": 10000,
        "max_storage_mb": 500,
    },
    "pro": {
        "max_members": 25,
        "max_api_keys": 20,
        "max_sources": 100,
        "max_documents": 50000,
        "max_queries_per_day": 100000,
        "max_storage_mb": 5000,
    },
    "enterprise": {
        "max_members": 9999,
        "max_api_keys": 100,
        "max_sources": 9999,
        "max_documents": 999999,
        "max_queries_per_day": 999999,
        "max_storage_mb": 99999,
    },
}


class BillingService:
    """Service for Paddle billing operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.api_key = settings.paddle_api_key
        self.environment = settings.paddle_environment
        self.base_url = PADDLE_API_URLS.get(self.environment, PADDLE_API_URLS["sandbox"])
        self.webhook_secret = settings.paddle_webhook_secret

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
    ) -> dict:
        """Make a request to the Paddle API."""
        if not self.api_key:
            raise DocVectorException(
                code="PADDLE_NOT_CONFIGURED",
                message="Paddle API key not configured",
            )

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=data)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=data)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code >= 400:
                logger.error(
                    "Paddle API error",
                    status=response.status_code,
                    body=response.text,
                )
                raise DocVectorException(
                    code="PADDLE_API_ERROR",
                    message=f"Paddle API error: {response.status_code}",
                    details={"response": response.text},
                )

            return response.json()

    # ============ Price/Plan Helpers ============

    def get_price_id(self, plan: str, billing_cycle: str) -> Optional[str]:
        """Get Paddle price ID for a plan and billing cycle."""
        price_map = {
            ("starter", "monthly"): settings.paddle_price_starter_monthly,
            ("starter", "yearly"): settings.paddle_price_starter_yearly,
            ("pro", "monthly"): settings.paddle_price_pro_monthly,
            ("pro", "yearly"): settings.paddle_price_pro_yearly,
            ("enterprise", "monthly"): settings.paddle_price_enterprise_monthly,
            ("enterprise", "yearly"): settings.paddle_price_enterprise_yearly,
        }
        return price_map.get((plan, billing_cycle))

    def get_plan_from_price_id(self, price_id: str) -> Tuple[str, str]:
        """Get plan and billing cycle from Paddle price ID."""
        price_to_plan = {
            settings.paddle_price_starter_monthly: ("starter", "monthly"),
            settings.paddle_price_starter_yearly: ("starter", "yearly"),
            settings.paddle_price_pro_monthly: ("pro", "monthly"),
            settings.paddle_price_pro_yearly: ("pro", "yearly"),
            settings.paddle_price_enterprise_monthly: ("enterprise", "monthly"),
            settings.paddle_price_enterprise_yearly: ("enterprise", "yearly"),
        }
        return price_to_plan.get(price_id, ("unknown", "unknown"))

    # ============ Customer Operations ============

    async def get_or_create_customer(
        self,
        organization_id: UUID,
        email: str,
        name: Optional[str] = None,
    ) -> PaddleCustomer:
        """Get or create a Paddle customer for an organization."""
        # Check if customer already exists
        existing = await self.session.scalar(
            select(PaddleCustomer).where(PaddleCustomer.organization_id == organization_id)
        )
        if existing:
            return existing

        # Create customer in Paddle
        response = await self._make_request(
            "POST",
            "/customers",
            data={
                "email": email,
                "name": name,
                "custom_data": {"organization_id": str(organization_id)},
            },
        )

        paddle_customer = response["data"]

        # Save to database
        customer = PaddleCustomer(
            paddle_customer_id=paddle_customer["id"],
            organization_id=organization_id,
            email=email,
            name=name,
        )
        self.session.add(customer)
        await self.session.commit()
        await self.session.refresh(customer)

        logger.info("Paddle customer created", customer_id=paddle_customer["id"])
        return customer

    async def get_customer_by_paddle_id(self, paddle_customer_id: str) -> Optional[PaddleCustomer]:
        """Get a customer by Paddle customer ID."""
        return await self.session.scalar(
            select(PaddleCustomer).where(PaddleCustomer.paddle_customer_id == paddle_customer_id)
        )

    # ============ Subscription Operations ============

    async def create_checkout_url(
        self,
        organization_id: UUID,
        plan: str,
        billing_cycle: str,
        success_url: str,
        cancel_url: Optional[str] = None,
    ) -> str:
        """Create a Paddle checkout URL for subscription.

        This creates a checkout session that redirects the user to Paddle's
        hosted checkout page.
        """
        price_id = self.get_price_id(plan, billing_cycle)
        if not price_id:
            raise DocVectorException(
                code="INVALID_PLAN",
                message=f"Invalid plan or billing cycle: {plan}/{billing_cycle}",
            )

        # Get organization
        org = await self.session.get(Organization, organization_id)
        if not org:
            raise DocVectorException(
                code="ORG_NOT_FOUND",
                message="Organization not found",
            )

        # Get or create customer
        customer = await self.get_or_create_customer(
            organization_id=organization_id,
            email=org.owner.email if org.owner else f"org-{org.id}@docvector.dev",
            name=org.name,
        )

        # Create checkout session
        response = await self._make_request(
            "POST",
            "/transactions",
            data={
                "items": [
                    {
                        "price_id": price_id,
                        "quantity": 1,
                    }
                ],
                "customer_id": customer.paddle_customer_id,
                "custom_data": {
                    "organization_id": str(organization_id),
                    "plan": plan,
                    "billing_cycle": billing_cycle,
                },
                "checkout": {
                    "url": success_url,
                },
            },
        )

        transaction = response["data"]
        checkout_url = transaction.get("checkout", {}).get("url")

        if not checkout_url:
            raise DocVectorException(
                code="CHECKOUT_ERROR",
                message="Failed to create checkout URL",
            )

        return checkout_url

    async def get_subscription(self, organization_id: UUID) -> Optional[Subscription]:
        """Get active subscription for an organization."""
        return await self.session.scalar(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .where(Subscription.status.in_(["active", "trialing", "past_due"]))
            .order_by(Subscription.created_at.desc())
        )

    async def get_subscription_by_paddle_id(self, paddle_subscription_id: str) -> Optional[Subscription]:
        """Get subscription by Paddle subscription ID."""
        return await self.session.scalar(
            select(Subscription).where(Subscription.paddle_subscription_id == paddle_subscription_id)
        )

    async def cancel_subscription(
        self,
        organization_id: UUID,
        effective_from: str = "next_billing_period",
    ) -> Subscription:
        """Cancel a subscription.

        Args:
            organization_id: Organization ID
            effective_from: When to cancel - "immediately" or "next_billing_period"
        """
        subscription = await self.get_subscription(organization_id)
        if not subscription:
            raise DocVectorException(
                code="NO_SUBSCRIPTION",
                message="No active subscription found",
            )

        # Cancel in Paddle
        await self._make_request(
            "POST",
            f"/subscriptions/{subscription.paddle_subscription_id}/cancel",
            data={"effective_from": effective_from},
        )

        # Update local record
        subscription.status = "canceled"
        subscription.canceled_at = datetime.now(timezone.utc)
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        # Update organization plan to free
        org = await self.session.get(Organization, organization_id)
        if org:
            await self._update_org_quotas(org, "free")
            await self.session.commit()

        logger.info("Subscription canceled", subscription_id=str(subscription.id))
        return subscription

    async def update_subscription(
        self,
        organization_id: UUID,
        new_plan: str,
        new_billing_cycle: str,
        proration_behavior: str = "prorated_immediately",
    ) -> Subscription:
        """Update subscription to a new plan.

        Args:
            organization_id: Organization ID
            new_plan: New plan (starter, pro, enterprise)
            new_billing_cycle: New billing cycle (monthly, yearly)
            proration_behavior: How to handle proration
        """
        subscription = await self.get_subscription(organization_id)
        if not subscription:
            raise DocVectorException(
                code="NO_SUBSCRIPTION",
                message="No active subscription found",
            )

        new_price_id = self.get_price_id(new_plan, new_billing_cycle)
        if not new_price_id:
            raise DocVectorException(
                code="INVALID_PLAN",
                message=f"Invalid plan or billing cycle: {new_plan}/{new_billing_cycle}",
            )

        # Update in Paddle
        await self._make_request(
            "PATCH",
            f"/subscriptions/{subscription.paddle_subscription_id}",
            data={
                "items": [
                    {
                        "price_id": new_price_id,
                        "quantity": 1,
                    }
                ],
                "proration_billing_mode": proration_behavior,
            },
        )

        # Update local record
        subscription.plan = new_plan
        subscription.billing_cycle = new_billing_cycle
        subscription.paddle_price_id = new_price_id
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        # Update organization quotas
        org = await self.session.get(Organization, organization_id)
        if org:
            await self._update_org_quotas(org, new_plan)
            await self.session.commit()

        logger.info("Subscription updated", subscription_id=str(subscription.id), new_plan=new_plan)
        return subscription

    async def pause_subscription(self, organization_id: UUID) -> Subscription:
        """Pause a subscription."""
        subscription = await self.get_subscription(organization_id)
        if not subscription:
            raise DocVectorException(
                code="NO_SUBSCRIPTION",
                message="No active subscription found",
            )

        # Pause in Paddle
        await self._make_request(
            "POST",
            f"/subscriptions/{subscription.paddle_subscription_id}/pause",
        )

        # Update local record
        subscription.status = "paused"
        subscription.paused_at = datetime.now(timezone.utc)
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        logger.info("Subscription paused", subscription_id=str(subscription.id))
        return subscription

    async def resume_subscription(self, organization_id: UUID) -> Subscription:
        """Resume a paused subscription."""
        subscription = await self.session.scalar(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .where(Subscription.status == "paused")
        )
        if not subscription:
            raise DocVectorException(
                code="NO_PAUSED_SUBSCRIPTION",
                message="No paused subscription found",
            )

        # Resume in Paddle
        await self._make_request(
            "POST",
            f"/subscriptions/{subscription.paddle_subscription_id}/resume",
            data={"effective_from": "immediately"},
        )

        # Update local record
        subscription.status = "active"
        subscription.paused_at = None
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        logger.info("Subscription resumed", subscription_id=str(subscription.id))
        return subscription

    # ============ Transaction Operations ============

    async def get_transactions(
        self,
        organization_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Transaction]:
        """Get transactions for an organization."""
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.organization_id == organization_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_transaction_by_paddle_id(self, paddle_transaction_id: str) -> Optional[Transaction]:
        """Get transaction by Paddle transaction ID."""
        return await self.session.scalar(
            select(Transaction).where(Transaction.paddle_transaction_id == paddle_transaction_id)
        )

    # ============ Webhook Processing ============

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Paddle webhook signature."""
        if not self.webhook_secret:
            logger.warning("Webhook secret not configured, skipping verification")
            return True

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    async def process_webhook(self, event_type: str, data: dict) -> bool:
        """Process a Paddle webhook event.

        Returns True if the event was processed successfully.
        """
        event_id = data.get("event_id")

        # Validate event_id is present
        if not event_id:
            logger.warning("Webhook received without event_id", event_type=event_type)
            raise DocVectorException(
                code="INVALID_WEBHOOK",
                message="Webhook payload missing event_id",
            )

        # Check for duplicate (idempotency)
        existing = await self.session.scalar(
            select(PaddleWebhookEvent).where(PaddleWebhookEvent.paddle_event_id == event_id)
        )
        if existing and existing.status == "processed":
            logger.info("Webhook already processed", event_id=event_id)
            return True

        # Create event record
        if not existing:
            event_record = PaddleWebhookEvent(
                paddle_event_id=event_id,
                event_type=event_type,
                paddle_customer_id=data.get("data", {}).get("customer_id"),
                paddle_subscription_id=data.get("data", {}).get("subscription_id"),
                paddle_transaction_id=data.get("data", {}).get("id") if "transaction" in event_type else None,
                payload=data,
                occurred_at=datetime.fromisoformat(data.get("occurred_at", datetime.now(timezone.utc).isoformat())),
            )
            self.session.add(event_record)
            await self.session.commit()
        else:
            event_record = existing

        try:
            # Route to handler
            handler = self._get_webhook_handler(event_type)
            if handler:
                await handler(data["data"])
                event_record.status = "processed"
            else:
                event_record.status = "ignored"
                logger.info("Unhandled webhook event type", event_type=event_type)

            event_record.processed_at = datetime.now(timezone.utc)
            await self.session.commit()
            return True

        except Exception as e:
            event_record.status = "failed"
            event_record.error_message = str(e)
            await self.session.commit()
            logger.error("Webhook processing failed", event_type=event_type, error=str(e))
            raise

    def _get_webhook_handler(self, event_type: str):
        """Get handler for webhook event type."""
        handlers = {
            "subscription.created": self._handle_subscription_created,
            "subscription.updated": self._handle_subscription_updated,
            "subscription.canceled": self._handle_subscription_canceled,
            "subscription.paused": self._handle_subscription_paused,
            "subscription.resumed": self._handle_subscription_resumed,
            "transaction.completed": self._handle_transaction_completed,
            "transaction.payment_failed": self._handle_transaction_failed,
            "customer.created": self._handle_customer_created,
            "customer.updated": self._handle_customer_updated,
        }
        return handlers.get(event_type)

    async def _handle_subscription_created(self, data: dict):
        """Handle subscription.created webhook."""
        paddle_subscription_id = data["id"]
        paddle_customer_id = data["customer_id"]
        paddle_price_id = data["items"][0]["price"]["id"]

        # Get plan from price ID
        plan, billing_cycle = self.get_plan_from_price_id(paddle_price_id)

        # Get organization from customer
        customer = await self.get_customer_by_paddle_id(paddle_customer_id)
        if not customer:
            logger.error("Customer not found for subscription", customer_id=paddle_customer_id)
            return

        # Create subscription record
        subscription = Subscription(
            paddle_subscription_id=paddle_subscription_id,
            paddle_customer_id=paddle_customer_id,
            paddle_price_id=paddle_price_id,
            organization_id=customer.organization_id,
            plan=plan,
            billing_cycle=billing_cycle,
            status=data["status"],
            current_period_start=datetime.fromisoformat(data["current_billing_period"]["starts_at"]),
            current_period_end=datetime.fromisoformat(data["current_billing_period"]["ends_at"]),
            unit_price=data["items"][0]["price"]["unit_price"]["amount"],
            currency=data["items"][0]["price"]["unit_price"]["currency_code"],
        )
        self.session.add(subscription)

        # Update organization plan and quotas
        org = await self.session.get(Organization, customer.organization_id)
        if org:
            org.plan = plan
            await self._update_org_quotas(org, plan)

        await self.session.commit()
        logger.info("Subscription created", subscription_id=paddle_subscription_id, plan=plan)

    async def _handle_subscription_updated(self, data: dict):
        """Handle subscription.updated webhook."""
        subscription = await self.get_subscription_by_paddle_id(data["id"])
        if not subscription:
            logger.warning("Subscription not found", paddle_id=data["id"])
            return

        # Update fields
        subscription.status = data["status"]
        subscription.current_period_start = datetime.fromisoformat(data["current_billing_period"]["starts_at"])
        subscription.current_period_end = datetime.fromisoformat(data["current_billing_period"]["ends_at"])

        # Check for plan change
        new_price_id = data["items"][0]["price"]["id"]
        if new_price_id != subscription.paddle_price_id:
            plan, billing_cycle = self.get_plan_from_price_id(new_price_id)
            subscription.paddle_price_id = new_price_id
            subscription.plan = plan
            subscription.billing_cycle = billing_cycle

            # Update organization
            org = await self.session.get(Organization, subscription.organization_id)
            if org:
                org.plan = plan
                await self._update_org_quotas(org, plan)

        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("Subscription updated", subscription_id=data["id"])

    async def _handle_subscription_canceled(self, data: dict):
        """Handle subscription.canceled webhook."""
        subscription = await self.get_subscription_by_paddle_id(data["id"])
        if not subscription:
            return

        subscription.status = "canceled"
        subscription.canceled_at = datetime.now(timezone.utc)
        subscription.updated_at = datetime.now(timezone.utc)

        # Downgrade to free plan
        org = await self.session.get(Organization, subscription.organization_id)
        if org:
            org.plan = "free"
            await self._update_org_quotas(org, "free")

        await self.session.commit()
        logger.info("Subscription canceled", subscription_id=data["id"])

    async def _handle_subscription_paused(self, data: dict):
        """Handle subscription.paused webhook."""
        subscription = await self.get_subscription_by_paddle_id(data["id"])
        if not subscription:
            return

        subscription.status = "paused"
        subscription.paused_at = datetime.now(timezone.utc)
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("Subscription paused", subscription_id=data["id"])

    async def _handle_subscription_resumed(self, data: dict):
        """Handle subscription.resumed webhook."""
        subscription = await self.get_subscription_by_paddle_id(data["id"])
        if not subscription:
            return

        subscription.status = "active"
        subscription.paused_at = None
        subscription.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("Subscription resumed", subscription_id=data["id"])

    async def _handle_transaction_completed(self, data: dict):
        """Handle transaction.completed webhook."""
        paddle_transaction_id = data["id"]

        # Check if already exists
        existing = await self.get_transaction_by_paddle_id(paddle_transaction_id)
        if existing:
            existing.status = "completed"
            existing.completed_at = datetime.now(timezone.utc)
            await self.session.commit()
            return

        # Get organization from customer
        customer = await self.get_customer_by_paddle_id(data["customer_id"])
        org_id = customer.organization_id if customer else None

        # Get subscription if this is a subscription transaction
        subscription = None
        if data.get("subscription_id"):
            subscription = await self.get_subscription_by_paddle_id(data["subscription_id"])

        # Create transaction record
        details = data.get("details", {})
        totals = details.get("totals", {})

        transaction = Transaction(
            paddle_transaction_id=paddle_transaction_id,
            paddle_invoice_id=data.get("invoice_id"),
            paddle_customer_id=data["customer_id"],
            subscription_id=subscription.id if subscription else None,
            organization_id=org_id,
            status="completed",
            origin=data.get("origin"),
            subtotal=int(totals.get("subtotal", 0)),
            tax=int(totals.get("tax", 0)),
            total=int(totals.get("total", 0)),
            currency=data.get("currency_code", "USD"),
            items=data.get("items", []),
            invoice_url=data.get("checkout", {}).get("url"),
            completed_at=datetime.now(timezone.utc),
        )

        # Add billing period if subscription
        if data.get("billing_period"):
            transaction.billing_period_start = datetime.fromisoformat(data["billing_period"]["starts_at"])
            transaction.billing_period_end = datetime.fromisoformat(data["billing_period"]["ends_at"])

        self.session.add(transaction)
        await self.session.commit()
        logger.info("Transaction recorded", transaction_id=paddle_transaction_id)

    async def _handle_transaction_failed(self, data: dict):
        """Handle transaction.payment_failed webhook."""
        # Update subscription status to past_due if exists
        if data.get("subscription_id"):
            subscription = await self.get_subscription_by_paddle_id(data["subscription_id"])
            if subscription and subscription.status == "active":
                subscription.status = "past_due"
                subscription.updated_at = datetime.now(timezone.utc)
                await self.session.commit()

        logger.warning("Transaction failed", transaction_id=data["id"])

    async def _handle_customer_created(self, data: dict):
        """Handle customer.created webhook."""
        # Check if we need to create a local record
        existing = await self.get_customer_by_paddle_id(data["id"])
        if existing:
            return

        # This shouldn't happen often - customers are usually created by us
        logger.info("Customer created via Paddle directly", customer_id=data["id"])

    async def _handle_customer_updated(self, data: dict):
        """Handle customer.updated webhook."""
        customer = await self.get_customer_by_paddle_id(data["id"])
        if not customer:
            return

        customer.email = data.get("email", customer.email)
        customer.name = data.get("name", customer.name)
        customer.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("Customer updated", customer_id=data["id"])

    # ============ Helper Methods ============

    async def _update_org_quotas(self, org: Organization, plan: str):
        """Update organization quotas based on plan."""
        quotas = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["free"])
        org.plan = plan
        org.max_members = quotas["max_members"]
        org.max_api_keys = quotas["max_api_keys"]
        org.max_sources = quotas["max_sources"]
        org.max_documents = quotas["max_documents"]
        org.max_queries_per_day = quotas["max_queries_per_day"]
        org.max_storage_mb = quotas["max_storage_mb"]
        org.updated_at = datetime.now(timezone.utc)

    async def get_billing_portal_url(self, organization_id: UUID) -> str:
        """Get Paddle customer portal URL for managing billing."""
        customer = await self.session.scalar(
            select(PaddleCustomer).where(PaddleCustomer.organization_id == organization_id)
        )
        if not customer:
            raise DocVectorException(
                code="NO_CUSTOMER",
                message="No billing account found",
            )

        # Paddle's customer portal URL pattern
        portal_url = f"https://{'sandbox-' if self.environment == 'sandbox' else ''}customer-portal.paddle.com"
        return f"{portal_url}?customer_id={customer.paddle_customer_id}"
