"""Tenants and tenancies (Sprint 3).

Creating a tenancy is the pivot of the whole product: it flips the unit to
occupied, allocates a reference, and generates the lease PDF — all in one
transaction, so a failed lease render never leaves a half-created tenancy behind.
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.billing import Invoice, InvoiceStatus
from app.models.developer import WebhookEvent
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.schemas.tenant import (
    DuplicateWarning,
    TenancyCreate,
    TenancyUpdate,
    TenantCreate,
    TenantUpdate,
)
from app.services import (
    audit_service,
    lease_service,
    notification_service,
    reference_service,
    webhook_service,
)
from app.services.notifications import normalize_phone

EXPIRING_SOON_DAYS = 60
LIVE_TENANCY_STATUSES = [
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
]


async def _scope_tenants(db: AsyncSession, context: OrgContext, query: Select) -> Select:
    """Caretakers only see tenants who live in a property they are assigned to."""
    query = query.where(Tenant.organization_id == context.organization_id)
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(
            Tenant.id.in_(
                select(Tenancy.tenant_id)
                .join(Unit, Unit.id == Tenancy.unit_id)
                .where(Unit.property_id.in_(allowed))
            )
        )
    return query


# ------------------------------------------------------------------------ tenants


async def find_duplicates(
    db: AsyncSession,
    context: OrgContext,
    phone: str,
    national_id: str | None,
    exclude_id: uuid.UUID | None = None,
) -> list[DuplicateWarning]:
    conditions = [Tenant.phone_number == phone]
    if national_id:
        conditions.append(Tenant.national_id == national_id)

    query = select(Tenant).where(Tenant.organization_id == context.organization_id, or_(*conditions))
    if exclude_id:
        query = query.where(Tenant.id != exclude_id)

    warnings: list[DuplicateWarning] = []
    for match in await db.scalars(query):
        field = "phone_number" if match.phone_number == phone else "national_id"
        warnings.append(
            DuplicateWarning(
                field=field,
                value=match.phone_number if field == "phone_number" else (match.national_id or ""),
                existing_tenant_id=match.id,
                existing_tenant_name=match.full_name,
            )
        )
    return warnings


async def create_tenant(
    db: AsyncSession, context: OrgContext, payload: TenantCreate, request: Request | None = None
) -> Tenant:
    phone = normalize_phone(payload.phone_number)
    duplicates = await find_duplicates(db, context, phone, payload.national_id)

    if duplicates and not payload.acknowledge_duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "A tenant with these details already exists",
                "duplicates": [d.model_dump(mode="json") for d in duplicates],
            },
        )
    # The phone number is unique per organization at the database level, so an
    # acknowledged duplicate on phone still cannot be saved.
    if any(d.field == "phone_number" for d in duplicates):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{duplicates[0].existing_tenant_name} already uses {phone} in this organization",
        )

    reference = await reference_service.generate_reference(db, Tenant, context.organization_id, "TNT")
    record = Tenant(
        organization_id=context.organization_id,
        reference_code=reference,
        **payload.model_dump(exclude={"acknowledge_duplicate", "phone_number"}),
        phone_number=phone,
    )
    db.add(record)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenant.created",
        entity_type="tenant",
        entity_id=record.id,
        actor=context.user,
        summary=f"Added tenant {record.full_name} ({reference})",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    await webhook_service.dispatch(
        db,
        context.organization_id,
        WebhookEvent.TENANT_CREATED,
        {
            "id": str(record.id),
            "reference_code": record.reference_code,
            "full_name": record.full_name,
            "phone_number": record.phone_number,
        },
    )
    return record


async def get_tenant(db: AsyncSession, context: OrgContext, tenant_id: uuid.UUID) -> Tenant:
    record = assert_in_org(await db.get(Tenant, tenant_id), context, label="tenant")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        visible = await db.scalar(
            select(Tenancy.id)
            .join(Unit, Unit.id == Tenancy.unit_id)
            .where(Tenancy.tenant_id == record.id, Unit.property_id.in_(allowed))
            .limit(1)
        )
        if not visible:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This tenant is not in a property you are assigned to",
            )
    return record


async def update_tenant(
    db: AsyncSession,
    context: OrgContext,
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    request: Request | None = None,
) -> Tenant:
    record = await get_tenant(db, context, tenant_id)
    fields = payload.model_dump(exclude_unset=True)

    if "phone_number" in fields and fields["phone_number"]:
        fields["phone_number"] = normalize_phone(fields["phone_number"])
        if fields["phone_number"] != record.phone_number:
            clash = await db.scalar(
                select(Tenant.id).where(
                    Tenant.organization_id == context.organization_id,
                    Tenant.phone_number == fields["phone_number"],
                    Tenant.id != record.id,
                )
            )
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another tenant in this organization already uses that phone number",
                )

    before = {field: getattr(record, field) for field in fields}
    for field, value in fields.items():
        setattr(record, field, value)
    after = {field: getattr(record, field) for field in fields}

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenant.updated",
        entity_type="tenant",
        entity_id=record.id,
        actor=context.user,
        summary=f"Updated tenant {record.full_name}",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def archive_tenant(
    db: AsyncSession, context: OrgContext, tenant_id: uuid.UUID, request: Request | None = None
) -> Tenant:
    record = await get_tenant(db, context, tenant_id)
    live = await db.scalar(
        select(Tenancy.id).where(Tenancy.tenant_id == record.id, Tenancy.status.in_(LIVE_TENANCY_STATUSES))
    )
    if live:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This tenant has a live tenancy. End it before archiving them.",
        )

    record.is_archived = True
    record.archived_at = datetime.now(UTC)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenant.archived",
        entity_type="tenant",
        entity_id=record.id,
        actor=context.user,
        summary=f"Archived tenant {record.full_name}",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def list_tenants(
    db: AsyncSession,
    context: OrgContext,
    *,
    search: str | None = None,
    tenancy_status: TenancyStatus | None = None,
    property_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[dict]:
    """Tenant rows joined to their current tenancy, unit, property and balance."""
    await refresh_tenancy_statuses(db, context.organization_id)

    query = (
        select(Tenant, Tenancy, Unit, Property)
        .outerjoin(
            Tenancy,
            (Tenancy.tenant_id == Tenant.id) & (Tenancy.status.in_(LIVE_TENANCY_STATUSES)),
        )
        .outerjoin(Unit, Unit.id == Tenancy.unit_id)
        .outerjoin(Property, Property.id == Unit.property_id)
    )
    query = await _scope_tenants(db, context, query)

    if not include_archived:
        query = query.where(Tenant.is_archived.is_(False))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            Tenant.full_name.ilike(pattern)
            | Tenant.phone_number.ilike(pattern)
            | Tenant.national_id.ilike(pattern)
            | Tenant.reference_code.ilike(pattern)
            | Unit.unit_number.ilike(pattern)
            | Property.name.ilike(pattern)
        )
    if tenancy_status:
        if tenancy_status == TenancyStatus.VACATED:
            # A vacated tenant has no live tenancy at all.
            query = query.where(Tenancy.id.is_(None))
        else:
            query = query.where(Tenancy.status == tenancy_status)
    if property_id:
        query = query.where(Unit.property_id == property_id)

    rows = (await db.execute(query.order_by(Tenant.full_name))).all()

    tenancy_ids = [row[1].id for row in rows if row[1] is not None]
    balances = await _balances_for(db, tenancy_ids)

    result = []
    for tenant, tenancy, unit, property_record in rows:
        balance = balances.get(tenancy.id, Decimal("0.00")) if tenancy else Decimal("0.00")
        result.append(
            {
                "tenant": tenant,
                "tenancy": tenancy,
                "unit": unit,
                "property": property_record,
                "balance": balance,
                "payment_status": _payment_status(balance, tenancy),
            }
        )
    return result


def _payment_status(balance: Decimal, tenancy: Tenancy | None) -> str:
    if tenancy is None:
        return "no_tenancy"
    if balance <= 0:
        return "up_to_date"
    return "in_arrears"


async def _balances_for(db: AsyncSession, tenancy_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not tenancy_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Invoice.tenancy_id,
                func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0),
            )
            .where(
                Invoice.tenancy_id.in_(tenancy_ids),
                Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
            )
            .group_by(Invoice.tenancy_id)
        )
    ).all()
    return {tenancy_id: Decimal(total) for tenancy_id, total in rows}


def to_csv(rows: list[dict]) -> str:
    """CSV export for the tenant list (US-017)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Reference",
            "Name",
            "Phone",
            "Email",
            "National ID",
            "Property",
            "Unit",
            "Monthly rent (KES)",
            "Tenancy status",
            "Lease end",
            "Balance (KES)",
        ]
    )
    for row in rows:
        tenant, tenancy = row["tenant"], row["tenancy"]
        writer.writerow(
            [
                tenant.reference_code,
                tenant.full_name,
                tenant.phone_number,
                tenant.email or "",
                tenant.national_id or "",
                row["property"].name if row["property"] else "",
                row["unit"].unit_number if row["unit"] else "",
                f"{tenancy.monthly_rent:.2f}" if tenancy else "",
                tenancy.status.value if tenancy else "vacated",
                tenancy.end_date.isoformat() if tenancy and tenancy.end_date else "",
                f"{row['balance']:.2f}",
            ]
        )
    return buffer.getvalue()


# ---------------------------------------------------------------------- tenancies


async def create_tenancy(
    db: AsyncSession, context: OrgContext, payload: TenancyCreate, request: Request | None = None
) -> Tenancy:
    tenant = assert_in_org(await db.get(Tenant, payload.tenant_id), context, label="tenant")
    unit = assert_in_org(await db.get(Unit, payload.unit_id), context, label="unit")

    allowed = await accessible_property_ids(db, context)
    if allowed is not None and unit.property_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )

    occupied_by = await db.scalar(
        select(Tenancy).where(Tenancy.unit_id == unit.id, Tenancy.status.in_(LIVE_TENANCY_STATUSES))
    )
    if occupied_by:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unit {unit.unit_number} already has a live tenancy ({occupied_by.reference_code})",
        )

    reference = await reference_service.generate_reference(db, Tenancy, context.organization_id, "TCY")
    tenancy = Tenancy(
        organization_id=context.organization_id,
        reference_code=reference,
        **payload.model_dump(exclude={"generate_lease", "lease_template_id"}),
    )
    tenancy.status = _derive_status(tenancy, date.today())
    db.add(tenancy)
    await db.flush()

    # The unit's status is a consequence of its tenancy, never set by hand here.
    unit.status = UnitStatus.OCCUPIED
    # The advert stops being true the moment someone moves in (US-074).
    from app.services import vacancy_service

    await vacancy_service.close_listing_for_unit(db, unit.id)
    unit.vacancy_date = None
    unit.expected_vacancy_date = None

    if payload.generate_lease:
        await lease_service.generate_and_store_lease(db, tenancy, payload.lease_template_id)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenancy.created",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=context.user,
        summary=f"{tenant.full_name} moved into unit {unit.unit_number} ({reference})",
        request=request,
    )
    await db.commit()
    await db.refresh(tenancy)
    return tenancy


def _derive_status(tenancy: Tenancy, today: date) -> TenancyStatus:
    """Lifecycle status is always computed from dates — never set manually (US-018)."""
    if tenancy.vacated_at is not None:
        return TenancyStatus.VACATED
    if tenancy.notice_given_at is not None:
        return TenancyStatus.NOTICE_GIVEN
    if tenancy.is_open_ended or tenancy.end_date is None:
        return TenancyStatus.ACTIVE
    if tenancy.end_date < today:
        return TenancyStatus.EXPIRED
    if (tenancy.end_date - today).days <= EXPIRING_SOON_DAYS:
        return TenancyStatus.EXPIRING_SOON
    return TenancyStatus.ACTIVE


async def refresh_tenancy_statuses(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Recompute date-driven statuses. Cheap enough to run on read, and also run
    nightly by Celery Beat."""
    today = date.today()
    rows = await db.scalars(
        select(Tenancy).where(
            Tenancy.organization_id == organization_id,
            Tenancy.status.notin_([TenancyStatus.VACATED]),
        )
    )
    changed = 0
    for tenancy in rows:
        derived = _derive_status(tenancy, today)
        if derived != tenancy.status:
            tenancy.status = derived
            changed += 1
    if changed:
        await db.commit()
    return changed


async def get_tenancy(db: AsyncSession, context: OrgContext, tenancy_id: uuid.UUID) -> Tenancy:
    tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        unit = await db.get(Unit, tenancy.unit_id)
        if unit is None or unit.property_id not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
            )
    return tenancy


async def list_tenancies(
    db: AsyncSession,
    context: OrgContext,
    *,
    tenancy_status: TenancyStatus | None = None,
    unit_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    expiring_within_days: int | None = None,
) -> list[Tenancy]:
    await refresh_tenancy_statuses(db, context.organization_id)

    query = select(Tenancy).where(Tenancy.organization_id == context.organization_id)
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Tenancy.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed))))
    if tenancy_status:
        query = query.where(Tenancy.status == tenancy_status)
    if unit_id:
        query = query.where(Tenancy.unit_id == unit_id)
    if tenant_id:
        query = query.where(Tenancy.tenant_id == tenant_id)
    if expiring_within_days is not None:
        cutoff = date.today() + timedelta(days=expiring_within_days)
        query = query.where(Tenancy.end_date.is_not(None), Tenancy.end_date <= cutoff)

    rows = await db.scalars(query.order_by(Tenancy.start_date.desc()))
    return list(rows)


async def update_tenancy(
    db: AsyncSession,
    context: OrgContext,
    tenancy_id: uuid.UUID,
    payload: TenancyUpdate,
    request: Request | None = None,
) -> Tenancy:
    tenancy = await get_tenancy(db, context, tenancy_id)
    fields = payload.model_dump(exclude_unset=True)

    before = {field: getattr(tenancy, field) for field in fields}
    for field, value in fields.items():
        setattr(tenancy, field, value)
    tenancy.status = _derive_status(tenancy, date.today())
    after = {field: getattr(tenancy, field) for field in fields}

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenancy.updated",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=context.user,
        summary=f"Updated tenancy {tenancy.reference_code}",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(tenancy)
    return tenancy


async def vacate_tenancy(
    db: AsyncSession,
    context: OrgContext,
    tenancy_id: uuid.UUID,
    move_out_date: date,
    notes: str | None = None,
    request: Request | None = None,
) -> Tenancy:
    """Close out a tenancy and release the unit."""
    tenancy = await get_tenancy(db, context, tenancy_id)
    if tenancy.status == TenancyStatus.VACATED:
        return tenancy

    tenancy.status = TenancyStatus.VACATED
    tenancy.move_out_date = move_out_date
    tenancy.vacated_at = datetime.now(UTC)

    unit = await db.get(Unit, tenancy.unit_id)
    if unit:
        unit.status = UnitStatus.VACANT
        unit.vacancy_date = move_out_date
        unit.expected_vacancy_date = None

    tenant = await db.get(Tenant, tenancy.tenant_id)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenancy.vacated",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=context.user,
        summary=(
            f"{tenant.full_name if tenant else 'Tenant'} vacated unit "
            f"{unit.unit_number if unit else '?'} on {move_out_date.isoformat()}"
        ),
        changes={"notes": notes},
        request=request,
    )

    if tenant:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_tenant(tenant),
            notification_type=NotificationType.ACCOUNT,
            title="Tenancy closed",
            body=(
                f"Your tenancy {tenancy.reference_code} has been closed as of "
                f"{move_out_date.strftime('%d %b %Y')}. Any deposit refund will follow the "
                "move-out inspection."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        )

    await db.commit()
    await db.refresh(tenancy)
    return tenancy
