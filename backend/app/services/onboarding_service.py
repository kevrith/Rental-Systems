"""The first-login setup wizard (US-089).

One row per organisation, created lazily on first read rather than at
registration, so an organisation that predates this sprint gets a normal
in-progress wizard instead of a migration having to backfill one for everybody.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.customer_success import OnboardingProgress
from app.models.organization import MpesaCollectionMode
from app.models.property import Property, Unit
from app.models.tenant import Tenant
from app.models.user import User, UserRole

STEPS = ("added_property", "added_units", "invited_caretaker", "added_tenant", "setup_payment")


async def _detect(db: AsyncSession, context: OrgContext) -> dict[str, bool]:
    """Check real data to determine which steps are already done."""
    org_id = context.organization_id

    has_property = bool(
        await db.scalar(
            select(func.count())
            .select_from(Property)
            .where(Property.organization_id == org_id, Property.archived_at.is_(None))
        )
    )
    has_unit = bool(
        await db.scalar(
            select(func.count())
            .select_from(Unit)
            .where(Unit.organization_id == org_id, Unit.archived_at.is_(None))
        )
    )
    has_tenant = bool(
        await db.scalar(
            select(func.count())
            .select_from(Tenant)
            .where(Tenant.organization_id == org_id, Tenant.archived_at.is_(None))
        )
    )
    has_caretaker = bool(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == org_id, User.role == UserRole.CARETAKER)
        )
    )
    org = context.organization
    has_payment = bool(
        org.mpesa_shortcode
        or org.mpesa_phone_number
        or org.mpesa_collection_mode != MpesaCollectionMode.MANUAL
    )

    return {
        "added_property": has_property,
        "added_units": has_unit,
        "invited_caretaker": has_caretaker,
        "added_tenant": has_tenant,
        "setup_payment": has_payment,
    }


async def get_or_create(db: AsyncSession, context: OrgContext) -> OnboardingProgress:
    row = await db.scalar(
        select(OnboardingProgress).where(OnboardingProgress.organization_id == context.organization_id)
    )
    detected = await _detect(db, context)
    if row is None:
        row = OnboardingProgress(organization_id=context.organization_id)
        db.add(row)
    # Sync any steps that are done in reality but not yet recorded.
    changed = False
    for step, done in detected.items():
        if done and not getattr(row, step):
            setattr(row, step, True)
            changed = True
    if changed or row not in db.new:
        if row.completed_at is None and all(getattr(row, name) for name in STEPS):
            row.completed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(row)
    return row


async def mark_step(db: AsyncSession, context: OrgContext, step: str) -> OnboardingProgress:
    row = await get_or_create(db, context)
    setattr(row, step, True)
    if row.completed_at is None and all(getattr(row, name) for name in STEPS):
        row.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


async def dismiss(db: AsyncSession, context: OrgContext) -> OnboardingProgress:
    row = await get_or_create(db, context)
    if row.dismissed_at is None:
        row.dismissed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(row)
    return row
