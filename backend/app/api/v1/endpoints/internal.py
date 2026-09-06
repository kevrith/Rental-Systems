"""RentFlow's own customer-success surface (Sprint 20) — cross-organization,
gated by `require_platform_staff` rather than `OrgContext`. Nothing here is
scoped to a single tenant; every route deliberately reads or writes across
every organisation on the platform.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_staff
from app.core.config import settings
from app.core.database import get_db
from app.models.customer_success import CustomerSuccessAlert, OrganizationHealthScore
from app.models.organization import Organization
from app.models.user import User
from app.schemas.customer_success import (
    ChangelogEntryRead,
    ChangelogEntryWrite,
    HelpArticleRead,
    HelpArticleWrite,
    OrganizationHealthScoreRead,
    OrganizationHealthSummary,
    OrganizationPlanUpdate,
)
from app.services import changelog_service, help_service, referral_service

router = APIRouter()


@router.get("/organizations", response_model=list[OrganizationHealthSummary])
async def list_organization_health(
    staff: User = Depends(require_platform_staff), db: AsyncSession = Depends(get_db)
) -> list[OrganizationHealthSummary]:
    organizations = await db.scalars(select(Organization).order_by(Organization.name))
    summaries: list[OrganizationHealthSummary] = []
    for organization in organizations:
        latest = await db.scalar(
            select(OrganizationHealthScore)
            .where(OrganizationHealthScore.organization_id == organization.id)
            .order_by(OrganizationHealthScore.week_of.desc())
            .limit(1)
        )
        summaries.append(
            OrganizationHealthSummary(
                organization_id=organization.id,
                organization_name=organization.name,
                latest_score=latest.score if latest else None,
                trend=latest.trend if latest else None,
                week_of=latest.week_of if latest else None,
                is_at_risk=bool(latest and latest.score < settings.CUSTOMER_HEALTH_AT_RISK_THRESHOLD),
            )
        )
    summaries.sort(key=lambda s: (s.latest_score is None, s.latest_score))
    return summaries


@router.get(
    "/organizations/{organization_id}/health-history", response_model=list[OrganizationHealthScoreRead]
)
async def organization_health_history(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationHealthScoreRead]:
    rows = await db.scalars(
        select(OrganizationHealthScore)
        .where(OrganizationHealthScore.organization_id == organization_id)
        .order_by(OrganizationHealthScore.week_of.desc())
        .limit(52)
    )
    return [OrganizationHealthScoreRead.model_validate(row) for row in rows]


@router.post("/alerts/{alert_id}/acknowledge", status_code=204)
async def acknowledge_alert(
    alert_id: uuid.UUID, staff: User = Depends(require_platform_staff), db: AsyncSession = Depends(get_db)
) -> None:
    alert = await db.get(CustomerSuccessAlert, alert_id)
    if alert is not None and alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by_id = staff.id
        await db.commit()


@router.patch("/organizations/{organization_id}/plan")
async def update_organization_plan(
    organization_id: uuid.UUID,
    payload: OrganizationPlanUpdate,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    organization.subscription_plan = payload.plan
    await db.flush()
    await referral_service.handle_plan_upgraded(db, organization)
    await db.commit()
    return {"organization_id": str(organization.id), "plan": payload.plan.value}


# ------------------------------------------------------------- help articles


@router.get("/help-articles", response_model=list[HelpArticleRead])
async def list_all_help_articles(
    staff: User = Depends(require_platform_staff), db: AsyncSession = Depends(get_db)
) -> list[HelpArticleRead]:
    rows = await help_service.list_all(db)
    return [HelpArticleRead.model_validate(row) for row in rows]


@router.post("/help-articles", response_model=HelpArticleRead, status_code=201)
async def create_help_article(
    payload: HelpArticleWrite,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> HelpArticleRead:
    row = await help_service.create(db, staff, payload)
    return HelpArticleRead.model_validate(row)


@router.patch("/help-articles/{article_id}", response_model=HelpArticleRead)
async def update_help_article(
    article_id: uuid.UUID,
    payload: HelpArticleWrite,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> HelpArticleRead:
    row = await help_service.update(db, staff, article_id, payload)
    return HelpArticleRead.model_validate(row)


# -------------------------------------------------------------- changelog


@router.get("/changelog-entries", response_model=list[ChangelogEntryRead])
async def list_all_changelog_entries(
    staff: User = Depends(require_platform_staff), db: AsyncSession = Depends(get_db)
) -> list[ChangelogEntryRead]:
    rows = await changelog_service.list_all(db)
    return [ChangelogEntryRead.model_validate(row) for row in rows]


@router.post("/changelog-entries", response_model=ChangelogEntryRead, status_code=201)
async def create_changelog_entry(
    payload: ChangelogEntryWrite,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> ChangelogEntryRead:
    row = await changelog_service.create(db, staff, payload)
    return ChangelogEntryRead.model_validate(row)


@router.patch("/changelog-entries/{entry_id}", response_model=ChangelogEntryRead)
async def update_changelog_entry(
    entry_id: uuid.UUID,
    payload: ChangelogEntryWrite,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> ChangelogEntryRead:
    row = await changelog_service.update(db, entry_id, payload)
    return ChangelogEntryRead.model_validate(row)
