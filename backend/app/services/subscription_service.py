"""RentFlow's own subscription billing (Sprint 27, US-113).

The shape of it:

  * an organisation picks a plan and pays once through Paystack's hosted page,
    which saves a card;
  * every renewal after that is charged server-side against the saved card by
    the nightly biller, with no customer present;
  * a failed charge starts a dunning window rather than cutting access — the
    account keeps working until `grace_ends_at`, then drops to read-only.

Read-only, never deleted: the same rule an expired trial follows. A landlord who
stops paying keeps every tenant, lease and receipt they ever entered; the data
just stops growing until they settle. Losing a landlord's records over a failed
card would be indefensible.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.plans import price_for
from app.models.organization import Organization, SubscriptionPlan
from app.models.subscription import (
    BillingInterval,
    Subscription,
    SubscriptionInvoice,
    SubscriptionInvoiceStatus,
    SubscriptionStatus,
)
from app.models.user import User
from app.services import audit_service, paystack_service, reference_service

logger = logging.getLogger("rentflow.subscription")

# How long an account keeps working after a charge fails. Long enough to notice
# an expired card and fix it, short enough that free service is not indefinite.
GRACE_DAYS = 7

# Retries inside the grace window, one per nightly run. After this the
# subscription lapses whether or not the grace date has arrived.
MAX_ATTEMPTS = 3


def _period_end(start: date, interval: BillingInterval) -> date:
    """The last day covered by one period beginning on `start`.

    Month arithmetic by calendar, not by 30 days: a subscription started on the
    15th renews on the 15th. A start day with no counterpart in the next month
    (the 31st) lands on that month's last day and stays there.
    """
    if interval == BillingInterval.ANNUAL:
        try:
            return start.replace(year=start.year + 1) - timedelta(days=1)
        except ValueError:  # 29 February
            return start.replace(year=start.year + 1, day=28) - timedelta(days=1)

    month = start.month + 1
    year = start.year + (month > 12)
    month = month - 12 if month > 12 else month
    day = start.day
    while True:
        try:
            return date(year, month, day) - timedelta(days=1)
        except ValueError:
            day -= 1


async def get_subscription(db: AsyncSession, organization_id: uuid.UUID) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.organization_id == organization_id))


async def _next_invoice(
    db: AsyncSession,
    subscription: Subscription,
    period_start: date,
    period_end: date,
) -> SubscriptionInvoice:
    code = await reference_service.generate_reference(
        db, SubscriptionInvoice, subscription.organization_id, "SUB"
    )
    invoice = SubscriptionInvoice(
        organization_id=subscription.organization_id,
        subscription_id=subscription.id,
        reference_code=code,
        period_start=period_start,
        period_end=period_end,
        amount=subscription.amount,
        status=SubscriptionInvoiceStatus.PENDING,
    )
    db.add(invoice)
    await db.flush()
    return invoice


async def start_checkout(
    db: AsyncSession,
    organization: Organization,
    actor: User,
    *,
    plan: SubscriptionPlan,
    interval: BillingInterval,
    callback_url: str,
) -> tuple[SubscriptionInvoice, str]:
    """Open the first charge for a plan and return where to send the customer.

    The subscription row is created up front but stays inactive until the
    webhook confirms payment — nobody is on a paid plan because they opened a
    checkout page.
    """
    if not paystack_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Card billing is not enabled on this deployment",
        )
    try:
        amount = price_for(plan, annual=interval == BillingInterval.ANNUAL)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{plan.value.title()} is not a self-serve plan — talk to us about a quote",
        ) from exc

    email = actor.email
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add an email address to your profile before subscribing",
        )

    today = date.today()
    period_end = _period_end(today, interval)

    subscription = await get_subscription(db, organization.id)
    if subscription is None:
        subscription = Subscription(
            organization_id=organization.id,
            plan=plan,
            interval=interval,
            status=SubscriptionStatus.PAST_DUE,
            amount=amount,
            current_period_start=today,
            current_period_end=period_end,
            next_billing_date=today,
        )
        db.add(subscription)
        await db.flush()
    else:
        # A plan change takes effect when this charge succeeds, not before.
        subscription.plan = plan
        subscription.interval = interval
        subscription.amount = amount

    invoice = await _next_invoice(db, subscription, today, period_end)

    try:
        result = await paystack_service.initialize_subscription_charge(
            email=email,
            amount=amount,
            invoice_id=invoice.id,
            organization_id=organization.id,
            callback_url=callback_url,
        )
    except paystack_service.PaystackError as exc:
        invoice.status = SubscriptionInvoiceStatus.FAILED
        invoice.failure_reason = str(exc)[:500]
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not start checkout: {exc}"
        ) from exc

    invoice.paystack_reference = result.reference
    subscription.billing_email = email

    audit_service.record(
        db,
        organization_id=organization.id,
        action="subscription.checkout_started",
        entity_type="subscription",
        entity_id=subscription.id,
        actor=actor,
        summary=f"Checkout opened for {plan.value} ({interval.value}), KES {amount}",
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice, result.authorization_url


async def handle_charge(db: AsyncSession, reference: str, body: dict) -> str:
    """Apply a verified Paystack charge that belongs to a subscription.

    Called only for references carrying the subscription prefix; rent goes down
    `payment_service.handle_paystack_event` instead.
    """
    invoice = await db.scalar(
        select(SubscriptionInvoice)
        .options(selectinload(SubscriptionInvoice.subscription))
        .where(SubscriptionInvoice.paystack_reference == reference)
    )
    if invoice is None:
        return "No matching subscription invoice"
    if invoice.status == SubscriptionInvoiceStatus.PAID:
        return "Subscription invoice already paid"

    try:
        verification = await paystack_service.verify_transaction(reference)
    except paystack_service.PaystackError as exc:
        logger.warning("Could not verify subscription charge %s: %s", reference, exc)
        return "Verification against Paystack failed"

    if not verification.success:
        await mark_failed(db, invoice, verification.gateway_response or verification.status)
        await db.commit()
        return "Subscription charge failed"

    await mark_paid(db, invoice, paid_at=verification.paid_at, authorization=body)
    await db.commit()
    return "Subscription invoice paid"


async def mark_paid(
    db: AsyncSession,
    invoice: SubscriptionInvoice,
    *,
    paid_at: datetime | None,
    authorization: dict | None = None,
) -> None:
    """Settle an invoice and roll the subscription on to its next period."""
    subscription = invoice.subscription
    invoice.status = SubscriptionInvoiceStatus.PAID
    invoice.paid_at = paid_at or datetime.now(UTC)
    invoice.failure_reason = None

    # A card is only saved on the hosted-page charge; renewals reuse it.
    if authorization:
        saved = paystack_service.read_authorization(authorization)
        if saved:
            subscription.paystack_authorization_code = saved["authorization_code"]
            subscription.card_last4 = saved["last4"] or None
            subscription.card_brand = saved["brand"] or None

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.failed_attempts = 0
    subscription.grace_ends_at = None
    subscription.current_period_start = invoice.period_start
    subscription.current_period_end = invoice.period_end
    subscription.next_billing_date = invoice.period_end + timedelta(days=1)

    organization = await db.get(Organization, subscription.organization_id)
    if organization is not None:
        # The plan on the organisation is what the rest of the app gates on
        # (storage limits, feature checks), so it only moves once money lands.
        organization.subscription_plan = subscription.plan
        organization.trial_ends_at = None
        # Paying a late invoice restores writing in the same breath.
        organization.subscription_lapsed_at = None

    audit_service.record(
        db,
        organization_id=subscription.organization_id,
        action="subscription.invoice_paid",
        entity_type="subscription_invoice",
        entity_id=invoice.id,
        summary=(
            f"{invoice.reference_code} paid — KES {invoice.amount} for "
            f"{invoice.period_start} to {invoice.period_end}"
        ),
    )


async def mark_failed(db: AsyncSession, invoice: SubscriptionInvoice, reason: str) -> None:
    """Record a failed attempt and move the subscription along its dunning path."""
    subscription = invoice.subscription
    invoice.status = SubscriptionInvoiceStatus.FAILED
    invoice.failure_reason = reason[:500]
    invoice.attempts += 1

    subscription.failed_attempts += 1
    if subscription.grace_ends_at is None:
        subscription.grace_ends_at = date.today() + timedelta(days=GRACE_DAYS)

    out_of_road = subscription.failed_attempts >= MAX_ATTEMPTS or date.today() > subscription.grace_ends_at
    subscription.status = SubscriptionStatus.LAPSED if out_of_road else SubscriptionStatus.PAST_DUE
    if out_of_road:
        await _lock_account(db, subscription)

    audit_service.record(
        db,
        organization_id=subscription.organization_id,
        action="subscription.charge_failed",
        entity_type="subscription_invoice",
        entity_id=invoice.id,
        summary=(
            f"Attempt {subscription.failed_attempts} on {invoice.reference_code} failed: {reason[:200]}"
        ),
    )


async def charge_due_subscription(db: AsyncSession, subscription: Subscription, today: date) -> str:
    """Attempt one renewal. Returns a short word for what happened, for the log.

    Reuses the period's existing unpaid invoice rather than raising a new one on
    every retry, so three failed attempts are three attempts on one month — not
    three months of debt.
    """
    if not subscription.has_saved_card:
        await mark_failed_without_invoice(db, subscription, "No saved card to charge")
        return "no_card"

    period_start = subscription.next_billing_date
    period_end = _period_end(period_start, subscription.interval)

    invoice = await db.scalar(
        select(SubscriptionInvoice).where(
            SubscriptionInvoice.subscription_id == subscription.id,
            SubscriptionInvoice.period_start == period_start,
            SubscriptionInvoice.status != SubscriptionInvoiceStatus.PAID,
        )
    )
    if invoice is None:
        invoice = await _next_invoice(db, subscription, period_start, period_end)
    invoice.subscription = subscription

    # A fresh reference per attempt: Paystack rejects a reused one, and a retry
    # is a genuinely new charge against the same month.
    reference = f"{paystack_service.SUBSCRIPTION_PREFIX}{invoice.id}-{invoice.attempts + 1}"
    invoice.paystack_reference = reference

    try:
        result = await paystack_service.charge_authorization(
            email=subscription.billing_email or "",
            amount=Decimal(invoice.amount),
            authorization_code=subscription.paystack_authorization_code or "",
            reference=reference,
        )
    except paystack_service.PaystackError as exc:
        await mark_failed(db, invoice, str(exc))
        return "failed"

    if not result.success:
        await mark_failed(db, invoice, result.gateway_response or result.status)
        return "failed"

    await mark_paid(db, invoice, paid_at=result.paid_at)
    return "charged"


async def mark_failed_without_invoice(db: AsyncSession, subscription: Subscription, reason: str) -> None:
    """Dunning for a subscription that cannot even be attempted."""
    subscription.failed_attempts += 1
    if subscription.grace_ends_at is None:
        subscription.grace_ends_at = date.today() + timedelta(days=GRACE_DAYS)
    if subscription.failed_attempts >= MAX_ATTEMPTS or date.today() > subscription.grace_ends_at:
        subscription.status = SubscriptionStatus.LAPSED
        await _lock_account(db, subscription)
    else:
        subscription.status = SubscriptionStatus.PAST_DUE

    audit_service.record(
        db,
        organization_id=subscription.organization_id,
        action="subscription.charge_failed",
        entity_type="subscription",
        entity_id=subscription.id,
        summary=f"Renewal could not be attempted: {reason}",
    )


async def _lock_account(db: AsyncSession, subscription: Subscription) -> None:
    """Drop the organisation to read-only. Nothing is deleted or hidden."""
    organization = await db.get(Organization, subscription.organization_id)
    if organization is not None and organization.subscription_lapsed_at is None:
        organization.subscription_lapsed_at = datetime.now(UTC)
        logger.warning(
            "Organisation %s is read-only: subscription unpaid past grace",
            subscription.organization_id,
        )


async def cancel(db: AsyncSession, subscription: Subscription, actor: User) -> Subscription:
    """Stop future charges. Access runs to the end of the paid period."""
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = datetime.now(UTC)
    audit_service.record(
        db,
        organization_id=subscription.organization_id,
        action="subscription.cancelled",
        entity_type="subscription",
        entity_id=subscription.id,
        actor=actor,
        summary=f"Cancelled; access runs to {subscription.current_period_end}",
    )
    await db.commit()
    await db.refresh(subscription)
    return subscription
