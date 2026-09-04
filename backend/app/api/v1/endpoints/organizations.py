from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, get_org_context, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.organization import Organization, SubscriptionPlan
from app.schemas.organization import (
    OrganizationRead,
    OrganizationWithTrial,
    UpdateOrganizationRequest,
)
from app.services import audit_service

router = APIRouter()


def _with_trial(organization: Organization) -> OrganizationWithTrial:
    is_trial = organization.subscription_plan == SubscriptionPlan.TRIAL
    days_remaining: int | None = None
    if is_trial and organization.trial_ends_at:
        delta = organization.trial_ends_at - datetime.now(UTC)
        days_remaining = max(0, delta.days + (1 if delta.seconds else 0))

    return OrganizationWithTrial(
        **OrganizationRead.model_validate(organization).model_dump(),
        is_trial=is_trial,
        is_trial_expired=organization.is_trial_expired,
        trial_days_remaining=days_remaining,
        is_read_only=organization.is_trial_expired,
    )


@router.get("/me", response_model=OrganizationWithTrial)
async def get_my_organization(
    context: OrgContext = Depends(get_org_context),
) -> OrganizationWithTrial:
    return _with_trial(context.organization)


@router.patch("/me", response_model=OrganizationWithTrial)
async def update_my_organization(
    payload: UpdateOrganizationRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> OrganizationWithTrial:
    organization = context.organization
    before = {field: getattr(organization, field) for field in payload.model_fields_set}

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, field, value)

    after = {field: getattr(organization, field) for field in payload.model_fields_set}
    audit_service.record(
        db,
        organization_id=organization.id,
        action="organization.updated",
        entity_type="organization",
        entity_id=organization.id,
        actor=context.user,
        summary="Updated organization settings",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(organization)
    return _with_trial(organization)
