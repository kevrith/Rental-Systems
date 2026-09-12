"""RentFlow's own customer-success surface (Sprint 20) — cross-organization,
gated by `require_platform_staff` rather than `OrgContext`. Nothing here is
scoped to a single tenant; every route deliberately reads or writes across
every organisation on the platform.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, computed_field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_staff
from app.core.config import settings
from app.core.database import get_db
from app.models.billing import Payment
from app.models.customer_success import CustomerSuccessAlert, OrganizationHealthScore
from app.models.demo import DemoDataset
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.models.security import BreachCategory, BreachSeverity, BreachStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.customer_success import (
    ChangelogEntryRead,
    ChangelogEntryWrite,
    HelpArticleRead,
    HelpArticleWrite,
    OrganizationHealthScoreRead,
    OrganizationHealthSummary,
    OrganizationPlanUpdate,
)
from app.services import (
    audit_service,
    breach_service,
    changelog_service,
    help_service,
    notification_service,
    referral_service,
    session_service,
)

router = APIRouter()


@router.get("/platform-stats")
async def platform_stats(
    staff: User = Depends(require_platform_staff), db: AsyncSession = Depends(get_db)
) -> dict:
    """Single-call summary for the superadmin overview card row."""
    total_orgs = await db.scalar(select(func.count(Organization.id))) or 0
    active_orgs = (
        await db.scalar(select(func.count(Organization.id)).where(Organization.is_active.is_(True))) or 0
    )
    total_users = await db.scalar(select(func.count(User.id))) or 0
    total_units = await db.scalar(select(func.count(Unit.id))) or 0
    total_tenants = await db.scalar(select(func.count(Tenant.id))) or 0

    plan_rows = await db.execute(
        select(Organization.subscription_plan, func.count(Organization.id)).group_by(
            Organization.subscription_plan
        )
    )
    plan_breakdown = {str(plan.value): count for plan, count in plan_rows}

    mode_rows = await db.execute(
        select(Organization.operating_mode, func.count(Organization.id)).group_by(Organization.operating_mode)
    )
    mode_breakdown = {str(mode.value): count for mode, count in mode_rows}

    return {
        "total_organizations": total_orgs,
        "active_organizations": active_orgs,
        "suspended_organizations": total_orgs - active_orgs,
        "total_users": total_users,
        "total_units": total_units,
        "total_tenants": total_tenants,
        "plan_breakdown": plan_breakdown,
        "mode_breakdown": mode_breakdown,
    }


@router.get("/organizations/detail")
async def list_organizations_detail(
    search: str | None = Query(default=None),
    plan: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Enriched org list: plan, mode, status, owner, unit/tenant counts."""
    query = select(Organization).order_by(Organization.created_at.desc())
    if search:
        term = f"%{search.strip()}%"
        query = query.where(Organization.name.ilike(term))
    if plan:
        query = query.where(Organization.subscription_plan == plan)
    if is_active is not None:
        query = query.where(Organization.is_active.is_(is_active))

    orgs = list(await db.scalars(query.limit(200)))
    result = []
    for org in orgs:
        owner = await db.scalar(
            select(User)
            .where(
                User.organization_id == org.id,
                User.role == UserRole.OWNER,
            )
            .limit(1)
        )
        unit_count = await db.scalar(select(func.count(Unit.id)).where(Unit.organization_id == org.id)) or 0
        tenant_count = (
            await db.scalar(select(func.count(Tenant.id)).where(Tenant.organization_id == org.id)) or 0
        )
        user_count = await db.scalar(select(func.count(User.id)).where(User.organization_id == org.id)) or 0
        result.append(
            {
                "id": str(org.id),
                "name": org.name,
                "subscription_plan": org.subscription_plan.value,
                "operating_mode": org.operating_mode.value,
                "is_active": org.is_active,
                "trial_ends_at": org.trial_ends_at.isoformat() if org.trial_ends_at else None,
                "is_trial_expired": org.is_trial_expired,
                "created_at": org.created_at.isoformat(),
                "suspended_at": org.suspended_at.isoformat() if org.suspended_at else None,
                "owner_name": owner.full_name if owner else None,
                "owner_email": owner.email if owner else None,
                "owner_phone": owner.phone_number if owner else None,
                "unit_count": unit_count,
                "tenant_count": tenant_count,
                "user_count": user_count,
            }
        )
    return result


@router.get("/users")
async def list_all_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Cross-tenant user search for superadmin."""
    query = select(User).order_by(User.created_at.desc())
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            User.full_name.ilike(term) | User.email.ilike(term) | User.phone_number.ilike(term)
        )
    if role:
        query = query.where(User.role == role)

    users = list(await db.scalars(query.limit(200)))
    result = []
    for user in users:
        org = await db.get(Organization, user.organization_id)
        result.append(
            {
                "id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role.value,
                "is_active": user.is_active,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "created_at": user.created_at.isoformat(),
                "organization_id": str(user.organization_id),
                "organization_name": org.name if org else None,
            }
        )
    return result


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enable or disable any user account platform-wide."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = not user.is_active
    if not user.is_active:
        await session_service.revoke_all(db, user.id)
    await db.commit()
    return {"id": str(user.id), "is_active": user.is_active}


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
    if "storage_limit_bytes" in payload.model_fields_set:
        organization.storage_limit_bytes = payload.storage_limit_bytes
    await db.flush()
    await referral_service.handle_plan_upgraded(db, organization)
    await db.commit()
    return {"organization_id": str(organization.id), "plan": payload.plan.value}


# ----------------------------------------- cross-org drill-down reads + CRUD


class InternalUnitCreate(BaseModel):
    property_id: uuid.UUID
    unit_number: str = Field(min_length=1, max_length=64)
    unit_type: str | None = None
    bedrooms: int | None = None
    monthly_rent: str = "0.00"
    deposit_amount: str = "0.00"


class InternalUnitUpdate(BaseModel):
    unit_number: str | None = Field(default=None, min_length=1, max_length=64)
    unit_type: str | None = None
    bedrooms: int | None = None
    monthly_rent: str | None = None
    deposit_amount: str | None = None


class InternalTenantCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone_number: str = Field(min_length=1, max_length=32)
    email: str | None = None


class InternalTenantUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, min_length=1, max_length=32)
    email: str | None = None


def _unit_dict(r: Unit, property_name: str | None) -> dict:
    return {
        "id": str(r.id),
        "unit_number": r.unit_number,
        "property_name": property_name,
        "property_id": str(r.property_id),
        "status": r.status.value,
        "monthly_rent": str(r.monthly_rent),
        "unit_type": r.unit_type,
        "bedrooms": r.bedrooms,
        "created_at": r.created_at.isoformat(),
    }


@router.get("/organizations/{organization_id}/properties")
async def org_properties(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list(
        await db.scalars(
            select(Property)
            .where(Property.organization_id == organization_id, Property.is_archived.is_(False))
            .order_by(Property.name)
        )
    )
    return [{"id": str(r.id), "name": r.name} for r in rows]


@router.get("/organizations/{organization_id}/units")
async def org_units(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list(
        await db.scalars(
            select(Unit)
            .where(Unit.organization_id == organization_id, Unit.is_archived.is_(False))
            .order_by(Unit.created_at.desc())
            .limit(500)
        )
    )
    props = {}
    for row in rows:
        if row.property_id not in props:
            p = await db.get(Property, row.property_id)
            props[row.property_id] = p.name if p else None
    return [_unit_dict(r, props.get(r.property_id)) for r in rows]


@router.post("/organizations/{organization_id}/units", status_code=201)
async def create_org_unit(
    organization_id: uuid.UUID,
    payload: InternalUnitCreate,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    prop = await db.get(Property, payload.property_id)
    if not prop or prop.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Property not found in this organization")
    from app.services import reference_service

    reference = await reference_service.generate_reference(db, Unit, organization_id, "UNT")
    unit = Unit(
        organization_id=organization_id,
        property_id=payload.property_id,
        reference_code=reference,
        unit_number=payload.unit_number,
        unit_type=payload.unit_type,
        bedrooms=payload.bedrooms,
        monthly_rent=payload.monthly_rent,
        deposit_amount=payload.deposit_amount,
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return _unit_dict(unit, prop.name)


@router.patch("/organizations/{organization_id}/units/{unit_id}")
async def update_org_unit(
    organization_id: uuid.UUID,
    unit_id: uuid.UUID,
    payload: InternalUnitUpdate,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    unit = await db.get(Unit, unit_id)
    if not unit or unit.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Unit not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)
    await db.commit()
    await db.refresh(unit)
    prop = await db.get(Property, unit.property_id)
    return _unit_dict(unit, prop.name if prop else None)


@router.delete("/organizations/{organization_id}/units/{unit_id}", status_code=204)
async def delete_org_unit(
    organization_id: uuid.UUID,
    unit_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> None:
    unit = await db.get(Unit, unit_id)
    if not unit or unit.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Unit not found")
    unit.is_archived = True
    await db.commit()


@router.get("/organizations/{organization_id}/tenants")
async def org_tenants(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list(
        await db.scalars(
            select(Tenant)
            .where(Tenant.organization_id == organization_id, Tenant.is_archived.is_(False))
            .order_by(Tenant.created_at.desc())
            .limit(500)
        )
    )
    return [
        {
            "id": str(r.id),
            "full_name": r.full_name,
            "phone_number": r.phone_number,
            "email": r.email,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/organizations/{organization_id}/tenants", status_code=201)
async def create_org_tenant(
    organization_id: uuid.UUID,
    payload: InternalTenantCreate,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.services import reference_service

    reference = await reference_service.generate_reference(db, Tenant, organization_id, "TNT")
    tenant = Tenant(
        organization_id=organization_id,
        reference_code=reference,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return {
        "id": str(tenant.id),
        "full_name": tenant.full_name,
        "phone_number": tenant.phone_number,
        "email": tenant.email,
        "created_at": tenant.created_at.isoformat(),
    }


@router.patch("/organizations/{organization_id}/tenants/{tenant_id}")
async def update_org_tenant(
    organization_id: uuid.UUID,
    tenant_id: uuid.UUID,
    payload: InternalTenantUpdate,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant or tenant.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Tenant not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    await db.commit()
    await db.refresh(tenant)
    return {
        "id": str(tenant.id),
        "full_name": tenant.full_name,
        "phone_number": tenant.phone_number,
        "email": tenant.email,
        "created_at": tenant.created_at.isoformat(),
    }


@router.delete("/organizations/{organization_id}/tenants/{tenant_id}", status_code=204)
async def delete_org_tenant(
    organization_id: uuid.UUID,
    tenant_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant or tenant.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.is_archived = True
    await db.commit()


@router.get("/organizations/{organization_id}/payments")
async def org_payments(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = list(
        await db.scalars(
            select(Payment)
            .where(Payment.organization_id == organization_id)
            .order_by(Payment.created_at.desc())
            .limit(200)
        )
    )
    return [
        {
            "id": str(r.id),
            "reference_code": r.reference_code,
            "amount": str(r.amount),
            "method": r.method.value,
            "status": r.status.value,
            "paid_at": r.paid_at.isoformat() if r.paid_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/organizations/{organization_id}/demo-data")
async def org_demo_data(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    dataset = await db.scalar(
        select(DemoDataset)
        .where(
            DemoDataset.organization_id == organization_id,
            DemoDataset.removed_at.is_(None),
        )
        .order_by(DemoDataset.created_at.desc())
        .limit(1)
    )
    return {
        "loaded": dataset is not None,
        "row_count": dataset.row_count if dataset else 0,
        "recipe": dataset.recipe if dataset else None,
        "loaded_at": dataset.created_at.isoformat() if dataset else None,
    }


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


# ------------------------------------------------------- account suspension


class OrganizationSuspend(BaseModel):
    # Required, and shown to the account holder. A suspension nobody can
    # explain is one that generates a support ticket instead of a payment.
    reason: str = Field(min_length=5, max_length=1000)
    notify_account: bool = True


class OrganizationSuspensionState(BaseModel):
    organization_id: uuid.UUID
    name: str
    is_active: bool
    suspended_at: datetime | None
    suspension_reason: str | None
    reactivated_at: datetime | None


def _suspension_state(organization: Organization) -> OrganizationSuspensionState:
    return OrganizationSuspensionState(
        organization_id=organization.id,
        name=organization.name,
        is_active=organization.is_active,
        suspended_at=organization.suspended_at,
        suspension_reason=organization.suspension_reason,
        reactivated_at=organization.reactivated_at,
    )


async def _load_organization(db: AsyncSession, organization_id: uuid.UUID) -> Organization:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


@router.get("/organizations/{organization_id}/suspension", response_model=OrganizationSuspensionState)
async def read_suspension_state(
    organization_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSuspensionState:
    return _suspension_state(await _load_organization(db, organization_id))


@router.post("/organizations/{organization_id}/suspend", response_model=OrganizationSuspensionState)
async def suspend_organization(
    organization_id: uuid.UUID,
    payload: OrganizationSuspend,
    request: Request,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSuspensionState:
    """Cut an account off (Module 25) — non-payment, abuse, or at its own request.

    `Organization.is_active` is already the flag `deps.get_org_context` refuses
    on; what this adds is the *why*, the *who*, and a way back. Every live
    session is revoked so the cut takes effect immediately rather than whenever
    the current access token happens to expire.

    Data is untouched. A suspension is a door being locked, not a deletion —
    account deletion has its own path with its own grace period (US-004).
    """
    organization = await _load_organization(db, organization_id)
    if not organization.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account is already suspended")

    now = datetime.now(UTC)
    organization.is_active = False
    organization.suspended_at = now
    organization.suspension_reason = payload.reason
    organization.suspended_by_id = staff.id
    organization.reactivated_at = None

    members = list(
        await db.scalars(
            select(User).where(User.organization_id == organization.id, User.is_active.is_(True))
        )
    )
    for member in members:
        await session_service.revoke_all(db, member.id)

    if payload.notify_account:
        for member in members:
            if member.role not in (UserRole.OWNER, UserRole.AGENCY_ADMIN):
                continue
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_user(member),
                notification_type=NotificationType.ACCOUNT,
                title="Your RentFlow account has been suspended",
                body=(
                    f"Your RentFlow account has been suspended. Reason: {payload.reason} "
                    f"Your data is safe and nothing has been deleted. "
                    f"Contact {settings.SUPPORT_EMAIL} to restore access."
                ),
                # Not in-app: they cannot sign in to read it.
                channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
                organization_id=organization.id,
            )

    audit_service.record(
        db,
        organization_id=organization.id,
        action="organization.suspended",
        entity_type="organization",
        entity_id=organization.id,
        actor=staff,
        summary=f"Account suspended by RentFlow staff: {payload.reason}",
        changes={"sessions_revoked": len(members)},
        request=request,
    )
    await db.commit()
    await db.refresh(organization)
    return _suspension_state(organization)


@router.post("/organizations/{organization_id}/reactivate", response_model=OrganizationSuspensionState)
async def reactivate_organization(
    organization_id: uuid.UUID,
    request: Request,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSuspensionState:
    """Restore access. Users sign in again — revoked sessions are not resurrected."""
    organization = await _load_organization(db, organization_id)
    if organization.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account is not suspended")

    organization.is_active = True
    organization.reactivated_at = datetime.now(UTC)
    organization.suspension_reason = None

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
            title="Your RentFlow account is active again",
            body=(
                "Your RentFlow account has been restored and you can sign in again. "
                "You will need to log in fresh — existing sessions were ended when the "
                "account was suspended."
            ),
            channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
            organization_id=organization.id,
        )

    audit_service.record(
        db,
        organization_id=organization.id,
        action="organization.reactivated",
        entity_type="organization",
        entity_id=organization.id,
        actor=staff,
        summary="Account reactivated by RentFlow staff",
        request=request,
    )
    await db.commit()
    await db.refresh(organization)
    return _suspension_state(organization)


# ------------------------------------------------------------ breach register


class BreachReport(BaseModel):
    category: BreachCategory
    severity: BreachSeverity
    summary: str = Field(min_length=10, max_length=512)
    detail: str | None = Field(default=None, max_length=10000)
    # When RentFlow became aware. Defaults to now; backdating it shortens the
    # remaining 72 hours, which is the correct and uncomfortable behaviour.
    detected_at: datetime | None = None
    occurred_at: datetime | None = None
    affected_organization_ids: list[uuid.UUID] = Field(default_factory=list)
    affected_subject_count: int | None = Field(default=None, ge=0)
    data_categories: list[str] = Field(default_factory=list)


class BreachAdvance(BaseModel):
    new_status: BreachStatus
    note: str | None = Field(default=None, max_length=10000)
    # Required to move to NOTIFIED — it is the evidence the notification happened.
    regulator_reference: str | None = Field(default=None, max_length=128)


class BreachNotifyCustomers(BaseModel):
    message: str = Field(min_length=20, max_length=4000)


class BreachRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference_code: str
    category: BreachCategory
    severity: BreachSeverity
    status: BreachStatus
    summary: str
    detail: str | None
    detected_at: datetime
    occurred_at: datetime | None
    notification_due_at: datetime
    affected_organization_ids: list[str]
    affected_subject_count: int | None
    data_categories: list[str]
    detector: str | None
    contained_at: datetime | None
    regulator_notified_at: datetime | None
    regulator_reference: str | None
    customers_notified_at: datetime | None
    no_notification_reason: str | None
    closed_at: datetime | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hours_remaining(self) -> float:
        """Negative once the 72-hour window has passed."""
        return round((self.notification_due_at - datetime.now(UTC)).total_seconds() / 3600, 1)


@router.get("/breaches", response_model=list[BreachRead])
async def list_breaches(
    open_only: bool = False,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> list[BreachRead]:
    rows = await breach_service.list_breaches(db, open_only=open_only)
    return [BreachRead.model_validate(row) for row in rows]


@router.get("/breaches/dashboard")
async def breach_dashboard(
    staff: User = Depends(require_platform_staff), db: AsyncSession = Depends(get_db)
) -> dict:
    """Open, awaiting notification, and overdue — the three numbers that matter."""
    return breach_service.dashboard(await breach_service.list_breaches(db))


@router.post("/breaches", response_model=BreachRead, status_code=201)
async def report_breach(
    payload: BreachReport,
    request: Request,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> BreachRead:
    """Record a breach and start the Kenya DPA s.43 72-hour clock."""
    breach = await breach_service.report(
        db,
        reported_by=staff,
        request=request,
        **payload.model_dump(),
    )
    return BreachRead.model_validate(breach)


@router.get("/breaches/{breach_id}", response_model=BreachRead)
async def get_breach(
    breach_id: uuid.UUID,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> BreachRead:
    return BreachRead.model_validate(await breach_service.get(db, breach_id))


@router.post("/breaches/{breach_id}/advance", response_model=BreachRead)
async def advance_breach(
    breach_id: uuid.UUID,
    payload: BreachAdvance,
    request: Request,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> BreachRead:
    """Move a breach along, recording what each state requires as evidence."""
    breach = await breach_service.advance(
        db,
        breach_id,
        new_status=payload.new_status,
        staff=staff,
        note=payload.note,
        regulator_reference=payload.regulator_reference,
        request=request,
    )
    return BreachRead.model_validate(breach)


@router.post("/breaches/{breach_id}/notify-customers")
async def notify_breach_customers(
    breach_id: uuid.UUID,
    payload: BreachNotifyCustomers,
    staff: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Tell each affected landlord, so they can discharge their own duty to tenants."""
    told = await breach_service.notify_affected_customers(db, breach_id, staff=staff, message=payload.message)
    return {"contacts_notified": told}
