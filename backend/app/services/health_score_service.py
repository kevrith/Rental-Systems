"""Weekly customer health scoring (US-091).

Six 0-100 signals, each honestly derived from what the platform already
records (no synthetic baseline data), combined with the acceptance criteria's
weights: login frequency 20%, payments processed 25%, feature adoption 20%,
caretaker activity 15%, tenant-portal adoption 10%, support tickets 10%.

A signal with nothing to measure (no caretakers on a self-managed account, no
tenants yet on a brand-new trial) scores 100 for that component rather than 0
— an empty account is not the same as an unhealthy one.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.billing import Payment, PaymentStatus
from app.models.customer_success import (
    CustomerSuccessAlert,
    HealthTrend,
    OrganizationHealthScore,
    SupportRequest,
)
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import MaintenanceRequest
from app.models.organization import Organization
from app.models.property import CaretakerAssignment, Property, Unit
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import User, UserRole
from app.services import notification_service
from app.services.notifications import get_email_notifier

_LOGIN_WINDOW_DAYS = 14
_ADOPTION_WINDOW_DAYS = 30
_PAYMENT_WINDOW_DAYS = 30
_SUPPORT_WINDOW_DAYS = 30
_ADOPTION_TABLES = (Property, Unit, Tenant, Payment, MaintenanceRequest)

WEIGHTS = {
    "login_score": 0.20,
    "payment_score": 0.25,
    "adoption_score": 0.20,
    "caretaker_score": 0.15,
    "portal_score": 0.10,
    "support_score": 0.10,
}


def week_start(today: date | None = None) -> date:
    today = today or datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


async def _login_score(db: AsyncSession, organization_id: uuid.UUID, since: datetime) -> int:
    total = await db.scalar(
        select(func.count(User.id)).where(User.organization_id == organization_id, User.is_active.is_(True))
    )
    if not total:
        return 0
    active = await db.scalar(
        select(func.count(User.id)).where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.last_login_at.is_not(None),
            User.last_login_at >= since,
        )
    )
    return round(100 * (active or 0) / total)


async def _payment_score(db: AsyncSession, organization_id: uuid.UUID, since: datetime) -> int:
    active_tenancies = await db.scalar(
        select(func.count(Tenancy.id)).where(
            Tenancy.organization_id == organization_id, Tenancy.status == TenancyStatus.ACTIVE
        )
    )
    if not active_tenancies:
        return 100
    paying = await db.scalar(
        select(func.count(func.distinct(Payment.tenancy_id))).where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.paid_at >= since,
        )
    )
    return round(100 * min(paying or 0, active_tenancies) / active_tenancies)


async def _adoption_score(db: AsyncSession, organization_id: uuid.UUID, since: datetime) -> int:
    touched = 0
    for model in _ADOPTION_TABLES:
        count = await db.scalar(
            select(func.count(model.id)).where(
                model.organization_id == organization_id, model.created_at >= since
            )
        )
        if count:
            touched += 1
    return round(100 * touched / len(_ADOPTION_TABLES))


async def _caretaker_score(db: AsyncSession, organization_id: uuid.UUID, since: datetime) -> int:
    caretaker_ids = list(
        await db.scalars(
            select(CaretakerAssignment.user_id).where(
                CaretakerAssignment.organization_id == organization_id,
                CaretakerAssignment.is_active.is_(True),
            )
        )
    )
    if not caretaker_ids:
        return 100
    active = await db.scalar(
        select(func.count(func.distinct(User.id))).where(
            User.id.in_(caretaker_ids), User.last_login_at.is_not(None), User.last_login_at >= since
        )
    )
    return round(100 * (active or 0) / len(set(caretaker_ids)))


async def _portal_score(db: AsyncSession, organization_id: uuid.UUID, since: datetime) -> int:
    portal_roles = [UserRole.TENANT, UserRole.OWNER_PORTAL_USER]
    total = await db.scalar(
        select(func.count(User.id)).where(
            User.organization_id == organization_id, User.role.in_(portal_roles), User.is_active.is_(True)
        )
    )
    if not total:
        return 100
    active = await db.scalar(
        select(func.count(User.id)).where(
            User.organization_id == organization_id,
            User.role.in_(portal_roles),
            User.is_active.is_(True),
            User.last_login_at.is_not(None),
            User.last_login_at >= since,
        )
    )
    return round(100 * (active or 0) / total)


async def _support_score(db: AsyncSession, organization_id: uuid.UUID, since: datetime) -> int:
    open_count = await db.scalar(
        select(func.count(SupportRequest.id)).where(
            SupportRequest.organization_id == organization_id, SupportRequest.created_at >= since
        )
    )
    return max(0, 100 - 20 * (open_count or 0))


async def compute_for_organization(db: AsyncSession, organization: Organization) -> OrganizationHealthScore:
    now = datetime.now(UTC)
    org_id = organization.id
    login_since = now - timedelta(days=_LOGIN_WINDOW_DAYS)
    payment_since = now - timedelta(days=_PAYMENT_WINDOW_DAYS)
    adoption_since = now - timedelta(days=_ADOPTION_WINDOW_DAYS)
    support_since = now - timedelta(days=_SUPPORT_WINDOW_DAYS)
    components = {
        "login_score": await _login_score(db, org_id, login_since),
        "payment_score": await _payment_score(db, org_id, payment_since),
        "adoption_score": await _adoption_score(db, org_id, adoption_since),
        "caretaker_score": await _caretaker_score(db, org_id, login_since),
        "portal_score": await _portal_score(db, org_id, adoption_since),
        "support_score": await _support_score(db, org_id, support_since),
    }
    score = round(sum(components[key] * weight for key, weight in WEIGHTS.items()))

    week_of = week_start(now.date())
    previous = await db.scalar(
        select(OrganizationHealthScore)
        .where(
            OrganizationHealthScore.organization_id == organization.id,
            OrganizationHealthScore.week_of < week_of,
        )
        .order_by(OrganizationHealthScore.week_of.desc())
        .limit(1)
    )
    if previous is None:
        trend = HealthTrend.STABLE
    elif score > previous.score + 2:
        trend = HealthTrend.IMPROVING
    elif score < previous.score - 2:
        trend = HealthTrend.DECLINING
    else:
        trend = HealthTrend.STABLE

    row = await db.scalar(
        select(OrganizationHealthScore).where(
            OrganizationHealthScore.organization_id == organization.id,
            OrganizationHealthScore.week_of == week_of,
        )
    )
    if row is None:
        row = OrganizationHealthScore(organization_id=organization.id, week_of=week_of)
        db.add(row)
    row.score = score
    row.trend = trend
    for key, value in components.items():
        setattr(row, key, value)
    await db.flush()

    if score < settings.CUSTOMER_HEALTH_AT_RISK_THRESHOLD:
        await _raise_alert(db, organization, row)

    await db.commit()
    await db.refresh(row)
    return row


async def _raise_alert(
    db: AsyncSession, organization: Organization, health_score: OrganizationHealthScore
) -> None:
    already = await db.scalar(
        select(CustomerSuccessAlert).where(CustomerSuccessAlert.health_score_id == health_score.id)
    )
    if already is not None:
        return

    alert = CustomerSuccessAlert(
        organization_id=organization.id,
        health_score_id=health_score.id,
        score=health_score.score,
        triggered_at=datetime.now(UTC),
    )
    db.add(alert)
    await db.flush()

    owners = await db.scalars(
        select(User).where(
            User.organization_id == organization.id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.ACCOUNT,
            title="We miss you at RentFlow",
            body=(
                "Your account activity has dropped recently — reply to this message or reach out any time "
                "if there's something we can help with."
            ),
            channels=[NotificationChannel.WHATSAPP],
            entity_type="customer_success_alert",
            entity_id=alert.id,
        )

    notifier = get_email_notifier()
    await notifier.send(
        settings.SUPPORT_EMAIL,
        f"At-risk account: {organization.name}",
        f"<p>{organization.name} (id {organization.id}) scored {health_score.score}/100 this week.</p>",
    )
