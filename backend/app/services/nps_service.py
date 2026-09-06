"""NPS survey prompts (US-092).

Eligibility is checked inline rather than on a schedule: `queue_if_eligible` is
called from the same write paths that complete a milestone-worthy action
(first payment, first inspection) plus a lazy 30-day-old check on dashboard
load, and a prompt is only ever created once per user per trigger thanks to
the unique constraint on (organization_id, user_id, trigger_event).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.customer_success import NpsSurveyPrompt, NpsTrigger
from app.schemas.customer_success import NpsResponseCreate

_FIRST_MONTH_DAYS = 30


async def queue_if_eligible(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, trigger: NpsTrigger
) -> None:
    stmt = (
        pg_insert(NpsSurveyPrompt)
        .values(organization_id=organization_id, user_id=user_id, trigger_event=trigger)
        .on_conflict_do_nothing(constraint="uq_nps_prompt_user_trigger")
    )
    await db.execute(stmt)
    await db.commit()


async def pending_for(db: AsyncSession, context: OrgContext) -> NpsSurveyPrompt | None:
    org_age = datetime.now(UTC) - context.organization.created_at
    if org_age >= timedelta(days=_FIRST_MONTH_DAYS):
        await queue_if_eligible(db, context.organization_id, context.user.id, NpsTrigger.FIRST_MONTH)

    prompt = await db.scalar(
        select(NpsSurveyPrompt).where(
            NpsSurveyPrompt.organization_id == context.organization_id,
            NpsSurveyPrompt.user_id == context.user.id,
            NpsSurveyPrompt.responded_at.is_(None),
        )
    )
    if prompt is not None and prompt.shown_at is None:
        prompt.shown_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(prompt)
    return prompt


async def record_response(
    db: AsyncSession, context: OrgContext, prompt_id: uuid.UUID, payload: NpsResponseCreate
) -> NpsSurveyPrompt:
    prompt = await db.get(NpsSurveyPrompt, prompt_id)
    belongs_to_caller = (
        prompt is not None
        and prompt.organization_id == context.organization_id
        and prompt.user_id == context.user.id
    )
    if not belongs_to_caller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey prompt not found")
    assert prompt is not None
    prompt.score = payload.score
    prompt.comment = payload.comment
    prompt.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(prompt)
    return prompt
