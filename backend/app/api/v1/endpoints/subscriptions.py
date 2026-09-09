"""What an organisation pays RentFlow (Sprint 27, US-113).

Deliberately thin: everything that decides money lives in
`subscription_service`, because the nightly biller drives the same logic with no
request context and the two must not drift.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.plans import PLAN_PRICES
from app.models.organization import SubscriptionPlan
from app.models.subscription import (
    BillingInterval,
    SubscriptionInvoice,
    SubscriptionInvoiceStatus,
    SubscriptionStatus,
)
from app.services import subscription_service

router = APIRouter()


class PlanOption(BaseModel):
    id: SubscriptionPlan
    monthly: Decimal
    annual: Decimal


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan: SubscriptionPlan
    interval: BillingInterval
    status: SubscriptionStatus
    amount: Decimal
    current_period_start: date
    current_period_end: date
    next_billing_date: date
    card_last4: str | None
    card_brand: str | None
    failed_attempts: int
    grace_ends_at: date | None
    cancelled_at: datetime | None


class SubscriptionInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference_code: str
    period_start: date
    period_end: date
    amount: Decimal
    status: SubscriptionInvoiceStatus
    attempts: int
    paid_at: datetime | None
    failure_reason: str | None
    created_at: datetime


class CheckoutRequest(BaseModel):
    plan: SubscriptionPlan
    interval: BillingInterval = BillingInterval.MONTHLY
    callback_url: str | None = None


class CheckoutResponse(BaseModel):
    invoice_id: uuid.UUID
    reference_code: str
    amount: Decimal
    authorization_url: str


@router.get("/plans", response_model=list[PlanOption])
async def list_plans(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
) -> list[PlanOption]:
    """The self-serve price list. Enterprise is quoted, so it is not here.

    Authenticated even though the same figures are on the public pricing page:
    the marketing site renders its own copy, so nothing needs this open, and an
    unauthenticated route is a surface to justify rather than a default.
    """
    return [
        PlanOption(id=plan, monthly=price.monthly, annual=price.annual) for plan, price in PLAN_PRICES.items()
    ]


@router.get("/subscription", response_model=SubscriptionRead | None)
async def current_subscription(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRead | None:
    subscription = await subscription_service.get_subscription(db, context.organization_id)
    return SubscriptionRead.model_validate(subscription) if subscription else None


@router.post("/subscription/checkout", response_model=CheckoutResponse)
async def start_checkout(
    payload: CheckoutRequest,
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """Open Paystack checkout for a plan. The card it saves pays every renewal."""
    from app.core.config import settings

    invoice, authorization_url = await subscription_service.start_checkout(
        db,
        context.organization,
        context.user,
        plan=payload.plan,
        interval=payload.interval,
        callback_url=payload.callback_url or f"{settings.FRONTEND_URL}/settings/billing",
    )
    return CheckoutResponse(
        invoice_id=invoice.id,
        reference_code=invoice.reference_code,
        amount=invoice.amount,
        authorization_url=authorization_url,
    )


@router.post("/subscription/cancel", response_model=SubscriptionRead)
async def cancel_subscription(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionRead:
    """Stop renewing. Access continues to the end of the period already paid for."""
    from fastapi import HTTPException, status

    subscription = await subscription_service.get_subscription(db, context.organization_id)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="There is no subscription to cancel"
        )
    cancelled = await subscription_service.cancel(db, subscription, context.user)
    return SubscriptionRead.model_validate(cancelled)


@router.get("/subscription/invoices", response_model=list[SubscriptionInvoiceRead])
async def subscription_invoices(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionInvoice]:
    rows = await db.scalars(
        select(SubscriptionInvoice)
        .where(SubscriptionInvoice.organization_id == context.organization_id)
        .order_by(SubscriptionInvoice.created_at.desc())
        .limit(100)
    )
    return list(rows)
