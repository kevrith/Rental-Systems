"""Legal hold — an explicit override on top of retention and erasure (Sprint 26A).

See `docs/legal/data-retention-policy.md` for the policy this enforces. The
only thing this module does is answer "is anything stopping me from acting on
this entity right now" and manage the hold records themselves; the actual
retention sweep (`retention_service.py`) and tenant-initiated erasure
(`privacy_service.py`) are the two callers that have to check before touching
personal data.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_hold import LegalHold


async def active_hold(
    db: AsyncSession, organization_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> LegalHold | None:
    """An active hold covering this exact entity, or a whole-organization hold — whichever exists."""
    return await db.scalar(
        select(LegalHold)
        .where(
            LegalHold.organization_id == organization_id,
            LegalHold.released_at.is_(None),
            or_(
                (LegalHold.entity_type == entity_type) & (LegalHold.entity_id == entity_id),
                (LegalHold.entity_type == "organization") & (LegalHold.entity_id.is_(None)),
            ),
        )
        .order_by(LegalHold.created_at.desc())
        .limit(1)
    )


async def place_hold(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    reason: str,
    placed_by_id: uuid.UUID | None,
    placed_by_name: str | None,
) -> LegalHold:
    hold = LegalHold(
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        placed_by_id=placed_by_id,
        placed_by_name=placed_by_name,
    )
    db.add(hold)
    await db.flush()
    return hold


async def release_hold(
    db: AsyncSession,
    hold: LegalHold,
    *,
    released_by_id: uuid.UUID | None,
    released_by_name: str | None,
    note: str | None = None,
) -> LegalHold:
    hold.released_at = datetime.now(UTC)
    hold.released_by_id = released_by_id
    hold.released_by_name = released_by_name
    hold.release_note = note
    return hold


async def list_holds(
    db: AsyncSession, organization_id: uuid.UUID, *, include_released: bool = False
) -> list[LegalHold]:
    query = select(LegalHold).where(LegalHold.organization_id == organization_id)
    if not include_released:
        query = query.where(LegalHold.released_at.is_(None))
    return list(await db.scalars(query.order_by(LegalHold.created_at.desc())))
