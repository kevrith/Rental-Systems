"""The first-login setup wizard (US-089).

One row per organisation, created lazily on first read rather than at
registration, so an organisation that predates this sprint gets a normal
in-progress wizard instead of a migration having to backfill one for everybody.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.customer_success import OnboardingProgress

STEPS = ("added_property", "added_units", "invited_caretaker", "added_tenant", "setup_payment")


async def get_or_create(db: AsyncSession, context: OrgContext) -> OnboardingProgress:
    row = await db.scalar(
        select(OnboardingProgress).where(OnboardingProgress.organization_id == context.organization_id)
    )
    if row is not None:
        return row
    row = OnboardingProgress(organization_id=context.organization_id)
    db.add(row)
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
