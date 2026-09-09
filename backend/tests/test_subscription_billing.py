"""RentFlow's own subscription billing (Sprint 27, US-113).

The money here flows the other way from the rest of the suite: an organisation
paying RentFlow, not a tenant paying a landlord. What is worth pinning down is
that the two never cross, that a saved card is what makes a renewal possible,
and that failing to pay costs an account its *write* access and nothing else.
"""

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.plans import PLAN_PRICES, price_for
from app.models.organization import Organization, SubscriptionPlan
from app.models.subscription import (
    BillingInterval,
    Subscription,
    SubscriptionInvoice,
    SubscriptionInvoiceStatus,
    SubscriptionStatus,
)
from app.services import paystack_service, subscription_service
from tests.conftest import Actor
from tests.test_paystack import SECRET_KEY, _sign


def _charge_body(reference: str, amount_kes: int, *, reusable: bool = True) -> dict:
    return {
        "event": "charge.success",
        "data": {
            "reference": reference,
            "status": "success",
            "amount": amount_kes * 100,
            "currency": "KES",
            "channel": "card",
            "paid_at": "2026-09-09T09:30:00.000Z",
            "gateway_response": "Successful",
            "authorization": {
                "authorization_code": "AUTH_testcode123",
                "last4": "4081",
                "brand": "visa",
                "reusable": reusable,
            },
        },
    }


def _ok_charge(amount: Decimal) -> paystack_service.ChargeResult:
    return paystack_service.ChargeResult(reference="x", success=True, status="success", amount=amount)


async def _subscribed_org(db, owner: Actor, *, plan=SubscriptionPlan.STARTER) -> Subscription:
    """An organisation already paying, with a card on file."""
    today = date.today()
    subscription = Subscription(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        plan=plan,
        interval=BillingInterval.MONTHLY,
        status=SubscriptionStatus.ACTIVE,
        amount=price_for(plan, annual=False),
        current_period_start=today - timedelta(days=30),
        current_period_end=today - timedelta(days=1),
        next_billing_date=today,
        paystack_authorization_code="AUTH_testcode123",
        billing_email="billing@example.com",
        card_last4="4081",
        card_brand="visa",
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


# ----------------------------------------------------------------- the price list


def test_backend_prices_match_the_published_pricing_page() -> None:
    """The figures here are what the marketing site advertises. Charging
    anything else is a support ticket at best."""
    assert PLAN_PRICES[SubscriptionPlan.STARTER].monthly == Decimal("2000.00")
    assert PLAN_PRICES[SubscriptionPlan.PROFESSIONAL].monthly == Decimal("8000.00")
    assert PLAN_PRICES[SubscriptionPlan.BUSINESS].monthly == Decimal("20000.00")
    # Annual is ten months' money for twelve months' service.
    for plan, price in PLAN_PRICES.items():
        assert price.annual == price.monthly * 10, plan


def test_plans_without_a_self_serve_price_cannot_be_charged() -> None:
    """Defaulting these to zero would silently hand out a paid plan."""
    for plan in (SubscriptionPlan.TRIAL, SubscriptionPlan.ENTERPRISE):
        with pytest.raises(ValueError):
            price_for(plan, annual=False)


# ----------------------------------------------------------------- period maths


def test_a_month_is_a_calendar_month_not_thirty_days() -> None:
    end = subscription_service._period_end(date(2026, 1, 15), BillingInterval.MONTHLY)
    assert end == date(2026, 2, 14)


def test_a_period_starting_on_the_31st_lands_on_the_short_months_last_day() -> None:
    end = subscription_service._period_end(date(2026, 1, 31), BillingInterval.MONTHLY)
    assert end == date(2026, 2, 27)  # the day before 28 Feb, the nearest valid 31st


def test_an_annual_period_runs_a_full_year() -> None:
    end = subscription_service._period_end(date(2026, 3, 1), BillingInterval.ANNUAL)
    assert end == date(2027, 2, 28)


# ----------------------------------------------------------------- checkout


async def test_checkout_does_not_put_anyone_on_a_paid_plan_before_they_pay(
    owner: Actor, db, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)

    async def fake_init(**kwargs) -> paystack_service.InitializeResult:
        return paystack_service.InitializeResult(
            reference=f"{paystack_service.SUBSCRIPTION_PREFIX}{kwargs['invoice_id']}",
            authorization_url="https://checkout.paystack.com/abc123",
            access_code="abc123",
        )

    monkeypatch.setattr(paystack_service, "initialize_subscription_charge", fake_init)

    response = await owner.post(
        "/api/v1/billing/subscription/checkout",
        json={"plan": "professional", "interval": "monthly"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["authorization_url"].startswith("https://checkout.paystack.com/")
    assert Decimal(response.json()["amount"]) == Decimal("8000.00")

    org = await db.get(Organization, uuid.UUID(owner.user["organization_id"]))
    await db.refresh(org)
    assert org.subscription_plan == SubscriptionPlan.TRIAL  # unchanged until paid

    invoice = await db.scalar(select(SubscriptionInvoice))
    assert invoice.status == SubscriptionInvoiceStatus.PENDING


async def test_enterprise_cannot_be_self_served(owner: Actor, monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    response = await owner.post("/api/v1/billing/subscription/checkout", json={"plan": "enterprise"})
    assert response.status_code == 400


async def test_checkout_is_refused_when_paystack_is_not_configured(owner: Actor, monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", None)
    response = await owner.post("/api/v1/billing/subscription/checkout", json={"plan": "starter"})
    assert response.status_code == 503


# ----------------------------------------------------------------- the webhook


async def test_a_subscription_charge_is_not_mistaken_for_rent(
    owner: Actor, client: AsyncClient, db, monkeypatch
) -> None:
    """One webhook serves two ledgers; the reference prefix is what separates
    them. A subscription event must never look for a rent payment."""
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    subscription = await _subscribed_org(db, owner)

    invoice = SubscriptionInvoice(
        organization_id=subscription.organization_id,
        subscription_id=subscription.id,
        reference_code="SUB-0001",
        period_start=date.today(),
        period_end=date.today() + timedelta(days=29),
        amount=Decimal("2000.00"),
        status=SubscriptionInvoiceStatus.PENDING,
    )
    reference = f"{paystack_service.SUBSCRIPTION_PREFIX}{uuid.uuid4()}"
    invoice.paystack_reference = reference
    db.add(invoice)
    await db.commit()

    monkeypatch.setattr(
        paystack_service, "verify_transaction", lambda ref: _verify_ok(ref, Decimal("2000.00"))
    )

    body = json.dumps(_charge_body(reference, 2000)).encode()
    response = await client.post(
        "/api/v1/paystack/webhook",
        content=body,
        headers={"x-paystack-signature": _sign(body), "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Subscription invoice paid"


async def _verify_ok(reference: str, amount: Decimal) -> paystack_service.ChargeResult:
    return paystack_service.ChargeResult(reference=reference, success=True, status="success", amount=amount)


async def test_paying_saves_the_card_and_moves_the_organisation_onto_the_plan(
    owner: Actor, db, monkeypatch
) -> None:
    subscription = await _subscribed_org(db, owner, plan=SubscriptionPlan.PROFESSIONAL)
    subscription.paystack_authorization_code = None
    subscription.card_last4 = None
    invoice = SubscriptionInvoice(
        organization_id=subscription.organization_id,
        subscription_id=subscription.id,
        reference_code="SUB-0002",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        amount=Decimal("8000.00"),
        status=SubscriptionInvoiceStatus.PENDING,
    )
    db.add(invoice)
    await db.commit()
    invoice.subscription = subscription

    await subscription_service.mark_paid(db, invoice, paid_at=None, authorization=_charge_body("ref", 8000))
    await db.commit()

    assert invoice.status == SubscriptionInvoiceStatus.PAID
    assert subscription.paystack_authorization_code == "AUTH_testcode123"
    assert subscription.card_last4 == "4081"
    assert subscription.status == SubscriptionStatus.ACTIVE
    # The next charge is the day after the period just paid for.
    assert subscription.next_billing_date == date(2026, 6, 1)

    org = await db.get(Organization, subscription.organization_id)
    assert org.subscription_plan == SubscriptionPlan.PROFESSIONAL


async def test_a_card_that_cannot_be_reused_is_not_saved(owner: Actor, db) -> None:
    """Only a reusable authorization can pay next month; storing anything else
    would leave the biller charging a token Paystack will reject."""
    assert paystack_service.read_authorization(_charge_body("r", 2000, reusable=False)) is None
    assert paystack_service.read_authorization(_charge_body("r", 2000)) is not None


# ----------------------------------------------------------------- dunning


async def test_a_failed_charge_keeps_the_account_working_during_grace(owner: Actor, db, monkeypatch) -> None:
    subscription = await _subscribed_org(db, owner)

    async def fails(**kwargs):
        raise paystack_service.PaystackError("Insufficient funds")

    monkeypatch.setattr(paystack_service, "charge_authorization", fails)

    outcome = await subscription_service.charge_due_subscription(db, subscription, date.today())
    await db.commit()

    assert outcome == "failed"
    assert subscription.status == SubscriptionStatus.PAST_DUE
    assert subscription.grace_ends_at is not None

    org = await db.get(Organization, subscription.organization_id)
    assert org.subscription_lapsed_at is None
    assert org.is_read_only is False  # still fully usable


async def test_retries_bill_one_month_not_three(owner: Actor, db, monkeypatch) -> None:
    """Three failed attempts are three tries at the same period. Raising a new
    invoice each night would invent debt the customer never incurred."""
    subscription = await _subscribed_org(db, owner)

    async def fails(**kwargs):
        raise paystack_service.PaystackError("Declined")

    monkeypatch.setattr(paystack_service, "charge_authorization", fails)

    for _ in range(3):
        await subscription_service.charge_due_subscription(db, subscription, date.today())
        await db.commit()

    invoices = list(
        await db.scalars(
            select(SubscriptionInvoice).where(SubscriptionInvoice.subscription_id == subscription.id)
        )
    )
    assert len(invoices) == 1
    assert invoices[0].attempts == 3


async def test_running_out_of_retries_drops_the_account_to_read_only(owner: Actor, db, monkeypatch) -> None:
    subscription = await _subscribed_org(db, owner)

    async def fails(**kwargs):
        raise paystack_service.PaystackError("Declined")

    monkeypatch.setattr(paystack_service, "charge_authorization", fails)

    for _ in range(subscription_service.MAX_ATTEMPTS):
        await subscription_service.charge_due_subscription(db, subscription, date.today())
        await db.commit()

    assert subscription.status == SubscriptionStatus.LAPSED

    org = await db.get(Organization, subscription.organization_id)
    assert org.subscription_lapsed_at is not None
    assert org.is_read_only is True


async def test_a_lapsed_account_can_still_be_read_but_not_written(owner: Actor, db, monkeypatch) -> None:
    """The whole point of read-only: a landlord who stops paying keeps every
    record they ever entered."""
    subscription = await _subscribed_org(db, owner)

    async def fails(**kwargs):
        raise paystack_service.PaystackError("Declined")

    monkeypatch.setattr(paystack_service, "charge_authorization", fails)
    for _ in range(subscription_service.MAX_ATTEMPTS):
        await subscription_service.charge_due_subscription(db, subscription, date.today())
        await db.commit()

    assert (await owner.get("/api/v1/properties")).status_code == 200

    blocked = await owner.post(
        "/api/v1/properties",
        json={"name": "Blocked Court", "address": "Nairobi", "property_type": "residential"},
    )
    assert blocked.status_code == 402


async def test_paying_a_late_invoice_restores_writing(owner: Actor, db, monkeypatch) -> None:
    subscription = await _subscribed_org(db, owner)

    async def fails(**kwargs):
        raise paystack_service.PaystackError("Declined")

    monkeypatch.setattr(paystack_service, "charge_authorization", fails)
    for _ in range(subscription_service.MAX_ATTEMPTS):
        await subscription_service.charge_due_subscription(db, subscription, date.today())
        await db.commit()

    org = await db.get(Organization, subscription.organization_id)
    assert org.is_read_only is True

    async def succeeds(**kwargs):
        return _ok_charge(Decimal(subscription.amount))

    monkeypatch.setattr(paystack_service, "charge_authorization", succeeds)
    outcome = await subscription_service.charge_due_subscription(db, subscription, date.today())
    await db.commit()

    assert outcome == "charged"
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.failed_attempts == 0
    await db.refresh(org)
    assert org.is_read_only is False


async def test_a_subscription_with_no_saved_card_cannot_be_charged(owner: Actor, db) -> None:
    subscription = await _subscribed_org(db, owner)
    subscription.paystack_authorization_code = None
    await db.commit()

    outcome = await subscription_service.charge_due_subscription(db, subscription, date.today())
    await db.commit()

    assert outcome == "no_card"
    assert subscription.status == SubscriptionStatus.PAST_DUE


# ----------------------------------------------------------------- scheduling


def test_the_biller_is_on_the_beat_schedule() -> None:
    from app.tasks.celery_app import celery_app

    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "rentflow.charge_due_subscriptions" in scheduled
