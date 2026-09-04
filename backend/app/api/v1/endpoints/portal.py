"""Tenant self-service portal (US-029, US-033).

Tenants authenticate with the same JWT as staff but carry `role=tenant`, and
every route here resolves the caller down to their own `Tenant` row. Nothing in
this module accepts a tenant id from the client — it is always derived from the
token, so one tenant can never address another's data.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, get_current_user, get_org_context
from app.core.config import settings
from app.core.database import get_db
from app.core.security import generate_url_token, hash_password, hash_token
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.file import StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import MaintenanceRequest
from app.models.property import Property, Unit
from app.models.session import TokenPurpose, VerificationToken
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import DEFAULT_INACTIVITY_TIMEOUT_MINUTES, User, UserRole
from app.schemas.auth import MessageResponse, TokenResponse
from app.schemas.billing import InvoiceRead, PaymentRead
from app.schemas.maintenance import MaintenanceRate
from app.schemas.operations import (
    MaintenanceCreate,
    MaintenanceRead,
    VacateNoticeCreate,
    VacateNoticeRead,
)
from app.services import (
    auth_service,
    file_service,
    invoice_service,
    maintenance_service,
    notification_service,
    operations_service,
    payment_service,
    session_service,
    tenant_service,
)

router = APIRouter()
invite_router = APIRouter()

LIVE = [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]


# ------------------------------------------------------------------ portal access


async def get_current_tenant(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Tenant:
    if current_user.role != UserRole.TENANT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This area is for tenants only")
    tenant = await db.scalar(select(Tenant).where(Tenant.portal_user_id == current_user.id))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No tenant record is linked to this login"
        )
    return tenant


async def _active_tenancy(db: AsyncSession, tenant: Tenant) -> Tenancy | None:
    return await db.scalar(
        select(Tenancy)
        .where(Tenancy.tenant_id == tenant.id, Tenancy.status.in_(LIVE))
        .order_by(Tenancy.start_date.desc())
        .limit(1)
    )


async def _owned_tenancy_ids(db: AsyncSession, tenant: Tenant) -> list[uuid.UUID]:
    return list(await db.scalars(select(Tenancy.id).where(Tenancy.tenant_id == tenant.id)))


async def _operator_context(db: AsyncSession, tenant: Tenant, user: User) -> OrgContext:
    """Build the org context the shared services expect.

    Portal routes reuse the operator services (payments, maintenance, notices),
    which are written against `OrgContext`. The tenant's own organization is the
    only one they can ever act in, so it is derived here rather than accepted.
    """
    from app.models.organization import Organization

    organization = await db.get(Organization, tenant.organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization is no longer available"
        )
    return OrgContext(user=user, organization=organization)


# --------------------------------------------------------------------- invitation


class InviteTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class AcceptPortalInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=72)


class PortalInvitePreview(BaseModel):
    full_name: str
    organization_name: str
    phone_number: str


class PortalSession(BaseModel):
    tenant_id: uuid.UUID
    full_name: str
    tokens: TokenResponse


@invite_router.post("/invite", response_model=MessageResponse)
async def invite_tenant_to_portal(
    payload: InviteTenantRequest,
    context: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Send the tenant a one-click link to set up their portal login."""
    from app.core.permissions import Permission

    if not context.can(Permission.TENANT_MANAGE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot invite tenants")

    tenant = await tenant_service.get_tenant(db, context, payload.tenant_id)
    if tenant.portal_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This tenant already has portal access"
        )

    raw = generate_url_token()
    db.add(
        VerificationToken(
            user_id=None,
            purpose=TokenPurpose.TENANT_PORTAL_INVITE,
            token_hash=hash_token(f"{tenant.id}:{raw}"),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.INVITATION_TTL_HOURS),
        )
    )

    link = f"{settings.FRONTEND_URL}/portal/setup?token={raw}&t={tenant.id}"
    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.ACCOUNT,
        title="Your RentFlow tenant portal",
        body=(
            f"Hi {tenant.full_name.split()[0]}, set up your tenant portal to pay rent, download "
            f"receipts and raise maintenance requests: {link}"
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        organization_id=context.organization_id,
    )
    await db.commit()
    return MessageResponse(message=f"Portal invitation sent to {tenant.phone_number}")


@invite_router.get("/setup/preview", response_model=PortalInvitePreview)
async def preview_portal_invite(
    token: str, tenant_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> PortalInvitePreview:
    tenant = await _consume_portal_token(db, token, tenant_id, consume=False)
    from app.models.organization import Organization

    organization = await db.get(Organization, tenant.organization_id)
    return PortalInvitePreview(
        full_name=tenant.full_name,
        organization_name=organization.name if organization else "",
        phone_number=tenant.phone_number,
    )


async def _consume_portal_token(db: AsyncSession, raw: str, tenant_id: uuid.UUID, *, consume: bool) -> Tenant:
    token = await db.scalar(
        select(VerificationToken).where(
            VerificationToken.token_hash == hash_token(f"{tenant_id}:{raw}"),
            VerificationToken.purpose == TokenPurpose.TENANT_PORTAL_INVITE,
        )
    )
    if token is None or token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This link is invalid or already used"
        )
    if token.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This link has expired")

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    if consume:
        token.used_at = datetime.now(UTC)
    return tenant


@invite_router.post("/setup", response_model=PortalSession)
async def accept_portal_invite(
    payload: AcceptPortalInviteRequest,
    tenant_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PortalSession:
    tenant = await _consume_portal_token(db, payload.token, tenant_id, consume=True)
    if tenant.portal_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Portal access is already set up")

    user = User(
        organization_id=tenant.organization_id,
        full_name=tenant.full_name,
        email=tenant.email or f"{tenant.phone_number.lstrip('+')}@tenant.rentflow.local",
        phone_number=tenant.phone_number,
        password_hash=hash_password(payload.password),
        role=UserRole.TENANT,
        is_phone_verified=True,
        inactivity_timeout_minutes=DEFAULT_INACTIVITY_TIMEOUT_MINUTES[UserRole.TENANT],
    )
    db.add(user)
    await db.flush()

    tenant.portal_user_id = user.id
    _, tokens = await session_service.create_session(db, user, request)
    await db.commit()

    return PortalSession(tenant_id=tenant.id, full_name=tenant.full_name, tokens=tokens)


# --------------------------------------------------------------------- home screen


class PortalHome(BaseModel):
    tenant_id: uuid.UUID
    full_name: str
    reference_code: str
    phone_number: str
    tenancy_id: uuid.UUID | None
    tenancy_reference: str | None
    property_name: str | None
    unit_number: str | None
    monthly_rent: Decimal | None
    balance: Decimal
    next_due_date: date | None
    lease_end_date: date | None
    lease_document_id: uuid.UUID | None
    organization_name: str


@router.get("/home", response_model=PortalHome)
async def portal_home(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> PortalHome:
    """Balance, next due date and where they live — the whole first screen."""
    from app.models.organization import Organization

    tenancy = await _active_tenancy(db, tenant)
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, tenant.organization_id)

    balance = await invoice_service.outstanding_balance(db, tenancy.id) if tenancy else Decimal("0.00")
    next_due = None
    if tenancy:
        next_due = await db.scalar(
            select(Invoice.due_date)
            .where(
                Invoice.tenancy_id == tenancy.id,
                Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
            )
            .order_by(Invoice.due_date)
            .limit(1)
        )

    return PortalHome(
        tenant_id=tenant.id,
        full_name=tenant.full_name,
        reference_code=tenant.reference_code,
        phone_number=tenant.phone_number,
        tenancy_id=tenancy.id if tenancy else None,
        tenancy_reference=tenancy.reference_code if tenancy else None,
        property_name=property_record.name if property_record else None,
        unit_number=unit.unit_number if unit else None,
        monthly_rent=tenancy.monthly_rent if tenancy else None,
        balance=balance,
        next_due_date=next_due,
        lease_end_date=tenancy.end_date if tenancy else None,
        lease_document_id=tenancy.lease_document_id if tenancy else None,
        organization_name=organization.name if organization else "",
    )


# ------------------------------------------------------------------------ payment


class PortalPayRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    phone_number: str | None = Field(default=None, max_length=32)


class PortalPayResponse(BaseModel):
    payment_id: uuid.UUID
    reference_code: str
    message: str


@router.post("/pay", response_model=PortalPayResponse, status_code=status.HTTP_202_ACCEPTED)
async def pay_rent(
    payload: PortalPayRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalPayResponse:
    """'Pay Rent' — two taps to an M-Pesa prompt (US-029)."""
    tenancy = await _active_tenancy(db, tenant)
    if tenancy is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You have no active tenancy to pay for"
        )

    context = await _operator_context(db, tenant, current_user)

    payment, message = await payment_service.initiate_stk_push(
        db,
        context,
        tenancy_id=tenancy.id,
        amount=payload.amount,
        phone_number=payload.phone_number or tenant.phone_number,
        request=request,
    )
    return PortalPayResponse(payment_id=payment.id, reference_code=payment.reference_code, message=message)


@router.get("/payments", response_model=list[PaymentRead])
async def portal_payments(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> list[Payment]:
    tenancy_ids = await _owned_tenancy_ids(db, tenant)
    if not tenancy_ids:
        return []
    rows = await db.scalars(
        select(Payment)
        .where(Payment.tenancy_id.in_(tenancy_ids))
        .order_by(Payment.created_at.desc())
        .limit(200)
    )
    return list(rows)


@router.get("/payments/{payment_id}/status", response_model=PaymentRead)
async def portal_payment_status(
    payment_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Payment:
    payment = await db.get(Payment, payment_id)
    tenancy_ids = await _owned_tenancy_ids(db, tenant)
    if payment is None or payment.tenancy_id not in tenancy_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if payment.status == PaymentStatus.PENDING:
        context = await _operator_context(db, tenant, current_user)
        await payment_service.poll_status(db, context, payment_id)
        await db.refresh(payment)
    return payment


@router.get("/invoices", response_model=list[InvoiceRead])
async def portal_invoices(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> list[Invoice]:
    tenancy_ids = await _owned_tenancy_ids(db, tenant)
    if not tenancy_ids:
        return []
    rows = await db.scalars(
        select(Invoice)
        .where(Invoice.tenancy_id.in_(tenancy_ids))
        .order_by(Invoice.due_date.desc())
        .limit(100)
    )
    return list(rows)


# ---------------------------------------------------------------------- documents


class PortalDocument(BaseModel):
    id: uuid.UUID
    filename: str
    category: str
    created_at: datetime
    url: str


@router.get("/documents", response_model=list[PortalDocument])
async def portal_documents(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> list[PortalDocument]:
    """Lease, receipts, invoices and notices — the tenant's own vault."""
    records = await file_service.list_for_entity(db, tenant.organization_id, "tenant", tenant.id)
    return [
        PortalDocument(
            id=record.id,
            filename=record.filename,
            category=record.category.value,
            created_at=record.created_at,
            url=file_service.to_url(record),
        )
        for record in records
    ]


@router.get("/lease", response_model=PortalDocument)
async def portal_lease(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> PortalDocument:
    tenancy = await _active_tenancy(db, tenant)
    if tenancy is None or tenancy.lease_document_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No lease document is on file yet")
    record = await db.get(StoredFile, tenancy.lease_document_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease file is missing")
    return PortalDocument(
        id=record.id,
        filename=record.filename,
        category=record.category.value,
        created_at=record.created_at,
        url=file_service.to_url(record),
    )


# -------------------------------------------------------------------- maintenance


class PortalMaintenanceCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    category: str = "other"
    priority: str = "routine"
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


@router.post("/maintenance", response_model=MaintenanceRead, status_code=status.HTTP_201_CREATED)
async def portal_create_maintenance(
    payload: PortalMaintenanceCreate,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceRequest:
    tenancy = await _active_tenancy(db, tenant)
    if tenancy is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You need an active tenancy to raise a maintenance request",
        )

    from app.models.operations import MaintenanceCategory, MaintenancePriority

    context = await _operator_context(db, tenant, current_user)

    return await operations_service.create_maintenance_request(
        db,
        context,
        MaintenanceCreate(
            unit_id=tenancy.unit_id,
            title=payload.title,
            description=payload.description,
            category=MaintenanceCategory(payload.category),
            priority=MaintenancePriority(payload.priority),
            photo_file_ids=payload.photo_file_ids,
        ),
        request,
        tenant=tenant,
    )


@router.get("/maintenance", response_model=list[MaintenanceRead])
async def portal_maintenance(
    tenant: Tenant = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)
) -> list[MaintenanceRequest]:
    rows = await db.scalars(
        select(MaintenanceRequest)
        .where(MaintenanceRequest.reported_by_tenant_id == tenant.id)
        .order_by(MaintenanceRequest.created_at.desc())
        .limit(100)
    )
    return list(rows)


@router.post("/maintenance/{request_id}/rate", response_model=MaintenanceRead)
async def portal_rate_maintenance(
    request_id: uuid.UUID,
    payload: MaintenanceRate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceRequest:
    """The tenant's own verdict on a finished job (US-063)."""
    record = await db.get(MaintenanceRequest, request_id)
    if record is None or record.reported_by_tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance request not found")
    return await maintenance_service.rate_by_tenant(
        db, record, rating=payload.rating, feedback=payload.feedback
    )


# ------------------------------------------------------------------ vacate notice


class PortalVacateRequest(BaseModel):
    move_out_date: date
    reason: str | None = Field(default=None, max_length=2000)


@router.post("/vacate-notice", response_model=VacateNoticeRead, status_code=status.HTTP_201_CREATED)
async def portal_submit_vacate_notice(
    payload: PortalVacateRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Digital notice to vacate, validated against the lease's notice period."""
    tenancy = await _active_tenancy(db, tenant)
    if tenancy is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have no active tenancy")
    if payload.move_out_date <= date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Move-out date must be in the future"
        )

    context = await _operator_context(db, tenant, current_user)

    return await operations_service.submit_vacate_notice(
        db,
        context,
        VacateNoticeCreate(tenancy_id=tenancy.id, move_out_date=payload.move_out_date, reason=payload.reason),
        tenant=tenant,
        request=request,
    )


# ------------------------------------------------------------------------- profile


class PortalProfileUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    emergency_contact_relationship: str | None = Field(default=None, max_length=64)


@router.patch("/profile", response_model=MessageResponse)
async def portal_update_profile(
    payload: PortalProfileUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Tenants may correct their own contact details, but not their identity —
    name, ID and phone stay under the landlord's control."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    await db.commit()
    return MessageResponse(message="Profile updated")


@router.post("/change-password", response_model=MessageResponse)
async def portal_change_password(
    current_password: str,
    new_password: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    from app.services import user_service

    await user_service.change_password(db, current_user, current_password, new_password, request)
    return MessageResponse(message="Password changed")


__all__ = ["router", "invite_router", "get_current_tenant", "auth_service"]
