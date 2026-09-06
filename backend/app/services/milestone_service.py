"""Per-organisation milestone celebrations (US-092).

`check_and_queue` is called from the write paths that can complete a milestone
— see `app.services.payment_service._confirm` (100th payment),
`app.services.tenant_service.create_tenant` (50th tenant) and
`app.services.etims_service.submit` (first eTIMS receipt). The unique
constraint on (organization_id, milestone_key) is what makes it safe to call
on every matching write without checking "have we already fired this" first.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.customer_success import MilestoneEvent, MilestoneKey


async def check_and_queue(db: AsyncSession, organization_id: uuid.UUID, milestone_key: MilestoneKey) -> None:
    stmt = (
        pg_insert(MilestoneEvent)
        .values(organization_id=organization_id, milestone_key=milestone_key, reached_at=datetime.now(UTC))
        .on_conflict_do_nothing(constraint="uq_milestone_organization_key")
    )
    await db.execute(stmt)


async def pending_for(db: AsyncSession, context: OrgContext) -> list[MilestoneEvent]:
    rows = await db.scalars(
        select(MilestoneEvent).where(
            MilestoneEvent.organization_id == context.organization_id,
            MilestoneEvent.acknowledged_at.is_(None),
        )
    )
    return list(rows)


async def acknowledge(db: AsyncSession, context: OrgContext, milestone_key: MilestoneKey) -> None:
    row = await db.scalar(
        select(MilestoneEvent).where(
            MilestoneEvent.organization_id == context.organization_id,
            MilestoneEvent.milestone_key == milestone_key,
        )
    )
    if row is not None and row.acknowledged_at is None:
        row.acknowledged_at = datetime.now(UTC)
        await db.commit()
