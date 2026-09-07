"""Fraud pattern detection (Sprint 22, US-097).

Evaluated inline from `payment_service._confirm` rather than as a separate
Celery sweep — every confirmed payment, cash or M-Pesa, already funnels
through that one function (see its own docstring), so hooking in there is
what "runs on all payment events" means in practice, and it is what gets a
WhatsApp alert to the owner while the pattern is still fresh rather than in
tomorrow's batch. Failures here must never break a payment — the caller wraps
this in a try/except.

Each check is keyed by a stable `pattern_key` so the same rule against the
same subject (a caretaker, a tenancy) doesn't re-alert every few minutes, and
so an owner's "this is legitimate" decision (`FraudSuppression`) silences it
for good.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Payment, PaymentMethod, PaymentStatus
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.security import FraudAlert, FraudAlertType, FraudSuppression
from app.models.tenant import Tenancy
from app.models.user import User, UserRole
from app.services import notification_service
from app.services.pdf_service import format_kes

logger = logging.getLogger("rentflow.fraud")

NAIROBI = ZoneInfo("Africa/Nairobi")
OFF_HOURS_START = 0  # midnight
OFF_HOURS_END = 5  # up to, not including, 5am
VELOCITY_WINDOW_MINUTES = 10
# Once an alert fires for a pattern, don't fire it again for this long — the
# owner has already been told, and a caretaker still mid-shift shouldn't
# generate one WhatsApp message per payment.
ALERT_DEDUPE_MINUTES = 60


async def evaluate_payment(db: AsyncSession, payment: Payment, tenancy: Tenancy) -> None:
    organization = await db.get(Organization, payment.organization_id)
    if organization is None:
        return
    recorded_by = await db.get(User, payment.recorded_by_id) if payment.recorded_by_id else None

    if payment.method == PaymentMethod.CASH and recorded_by is not None:
        await _check_rapid_cash(db, organization, recorded_by)
    if recorded_by is not None:
        await _check_off_hours(db, organization, payment, recorded_by)
    await _check_unusual_amount(db, organization, payment, tenancy)
    await _check_velocity(db, organization, payment, tenancy)


async def _check_rapid_cash(db: AsyncSession, org: Organization, recorded_by: User) -> None:
    since = datetime.now(UTC) - timedelta(minutes=org.fraud_cash_window_minutes)
    count = await db.scalar(
        select(func.count(Payment.id)).where(
            Payment.organization_id == org.id,
            Payment.recorded_by_id == recorded_by.id,
            Payment.method == PaymentMethod.CASH,
            Payment.created_at >= since,
        )
    )
    if (count or 0) < org.fraud_max_cash_payments_per_window:
        return
    await _raise_alert(
        db,
        org.id,
        alert_type=FraudAlertType.RAPID_CASH_PAYMENTS,
        pattern_key=f"rapid_cash:{recorded_by.id}",
        entity_type="user",
        entity_id=recorded_by.id,
        summary=(
            f"{recorded_by.full_name} recorded {count} cash payments in the last "
            f"{org.fraud_cash_window_minutes} minutes."
        ),
        details={"count": count, "window_minutes": org.fraud_cash_window_minutes},
    )


async def _check_off_hours(db: AsyncSession, org: Organization, payment: Payment, recorded_by: User) -> None:
    confirmed_at = payment.paid_at or payment.created_at
    local_hour = confirmed_at.astimezone(NAIROBI).hour
    if not (OFF_HOURS_START <= local_hour < OFF_HOURS_END):
        return
    await _raise_alert(
        db,
        org.id,
        alert_type=FraudAlertType.OFF_HOURS_ACTIVITY,
        pattern_key=f"off_hours:{recorded_by.id}",
        entity_type="payment",
        entity_id=payment.id,
        summary=(
            f"{recorded_by.full_name} recorded a payment of KES {format_kes(payment.amount)} at "
            f"{local_hour:02d}:00 Nairobi time."
        ),
        details={"hour": local_hour, "amount": str(payment.amount)},
    )


async def _check_unusual_amount(
    db: AsyncSession, org: Organization, payment: Payment, tenancy: Tenancy
) -> None:
    rent = Decimal(tenancy.monthly_rent)
    if rent <= 0:
        return
    multiplier = Decimal(org.fraud_unusual_amount_multiplier)
    amount = Decimal(payment.amount)
    if rent / multiplier <= amount <= rent * multiplier:
        return
    await _raise_alert(
        db,
        org.id,
        alert_type=FraudAlertType.UNUSUAL_AMOUNT,
        pattern_key=f"unusual_amount:{tenancy.id}",
        entity_type="payment",
        entity_id=payment.id,
        summary=(
            f"Payment of KES {format_kes(amount)} is unusual against a monthly rent of "
            f"KES {format_kes(rent)} for {tenancy.reference_code}."
        ),
        details={"amount": str(amount), "monthly_rent": str(rent)},
    )


async def _check_velocity(db: AsyncSession, org: Organization, payment: Payment, tenancy: Tenancy) -> None:
    since = datetime.now(UTC) - timedelta(minutes=VELOCITY_WINDOW_MINUTES)
    count = await db.scalar(
        select(func.count(Payment.id)).where(
            Payment.tenancy_id == tenancy.id,
            Payment.amount == payment.amount,
            Payment.id != payment.id,
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.created_at >= since,
        )
    )
    if not count:
        return
    await _raise_alert(
        db,
        org.id,
        alert_type=FraudAlertType.VELOCITY_DUPLICATE,
        pattern_key=f"velocity:{tenancy.id}",
        entity_type="payment",
        entity_id=payment.id,
        summary=(
            f"KES {format_kes(payment.amount)} was paid more than once for {tenancy.reference_code} "
            f"within {VELOCITY_WINDOW_MINUTES} minutes."
        ),
        details={"amount": str(payment.amount), "matches": count},
    )


async def _raise_alert(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    alert_type: FraudAlertType,
    pattern_key: str,
    entity_type: str,
    entity_id: uuid.UUID,
    summary: str,
    details: dict[str, Any],
) -> None:
    suppressed = await db.scalar(
        select(FraudSuppression.id).where(
            FraudSuppression.organization_id == organization_id,
            FraudSuppression.pattern_key == pattern_key,
        )
    )
    if suppressed:
        return

    recent_cutoff = datetime.now(UTC) - timedelta(minutes=ALERT_DEDUPE_MINUTES)
    duplicate = await db.scalar(
        select(FraudAlert.id).where(
            FraudAlert.organization_id == organization_id,
            FraudAlert.pattern_key == pattern_key,
            FraudAlert.created_at >= recent_cutoff,
        )
    )
    if duplicate:
        return

    alert = FraudAlert(
        organization_id=organization_id,
        alert_type=alert_type,
        pattern_key=pattern_key,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        details=details,
    )
    db.add(alert)
    await db.flush()

    owners = await db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.FRAUD_ALERT,
            title="Suspicious activity detected",
            body=summary,
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.PUSH],
            link_path="/security/fraud-alerts",
            entity_type="fraud_alert",
            entity_id=alert.id,
            organization_id=organization_id,
        )
