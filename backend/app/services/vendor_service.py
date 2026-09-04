"""The approved-contractor registry (US-060).

Vendors are cheap to create and expensive to get wrong, so the rules here are
about keeping the list trustworthy: one row per phone number, ratings that can
only come from a job that was actually completed, and deactivation instead of
deletion once a vendor has history attached.
"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.operations import MaintenanceRequest, MaintenanceStatus
from app.models.vendor import CATEGORY_SPECIALTIES, Vendor, VendorSpecialty
from app.schemas.vendor import VendorCreate, VendorUpdate
from app.services import audit_service

ZERO = Decimal("0.00")


async def _assert_phone_free(
    db: AsyncSession, organization_id: uuid.UUID, phone: str, *, exclude: uuid.UUID | None = None
) -> None:
    query = select(Vendor.id).where(Vendor.organization_id == organization_id, Vendor.phone_number == phone)
    if exclude:
        query = query.where(Vendor.id != exclude)
    if await db.scalar(query):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vendor with this phone number is already on your list",
        )


async def create_vendor(
    db: AsyncSession, context: OrgContext, payload: VendorCreate, request: Request | None = None
) -> Vendor:
    await _assert_phone_free(db, context.organization_id, payload.phone_number)

    vendor = Vendor(
        organization_id=context.organization_id,
        name=payload.name,
        company_name=payload.company_name,
        specialties=[s.value for s in payload.specialties],
        phone_number=payload.phone_number,
        email=payload.email,
        rate_notes=payload.rate_notes,
        notes=payload.notes,
        is_active=True,
    )
    db.add(vendor)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vendor.created",
        entity_type="vendor",
        entity_id=vendor.id,
        actor=context.user,
        summary=f"Added vendor {vendor.name} ({', '.join(vendor.specialties) or 'no specialty'})",
        request=request,
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def update_vendor(
    db: AsyncSession,
    context: OrgContext,
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    request: Request | None = None,
) -> Vendor:
    vendor = assert_in_org(await db.get(Vendor, vendor_id), context, label="vendor")
    fields = payload.model_dump(exclude_unset=True)

    if "phone_number" in fields and fields["phone_number"] != vendor.phone_number:
        await _assert_phone_free(db, context.organization_id, fields["phone_number"], exclude=vendor.id)
    if "specialties" in fields and fields["specialties"] is not None:
        fields["specialties"] = [
            s.value if isinstance(s, VendorSpecialty) else str(s) for s in fields["specialties"]
        ]

    for field, value in fields.items():
        setattr(vendor, field, value)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vendor.updated",
        entity_type="vendor",
        entity_id=vendor.id,
        actor=context.user,
        summary=f"Updated vendor {vendor.name}: {', '.join(sorted(fields)) or 'no change'}",
        request=request,
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def deactivate_vendor(
    db: AsyncSession, context: OrgContext, vendor_id: uuid.UUID, request: Request | None = None
) -> Vendor:
    """Vendors are never deleted — completed jobs point at them, and the cost
    history behind a maintenance report has to stay readable."""
    vendor = assert_in_org(await db.get(Vendor, vendor_id), context, label="vendor")

    open_jobs = await db.scalar(
        select(func.count(MaintenanceRequest.id)).where(
            MaintenanceRequest.vendor_id == vendor.id,
            MaintenanceRequest.status.in_(
                [
                    MaintenanceStatus.ASSIGNED,
                    MaintenanceStatus.IN_PROGRESS,
                ]
            ),
        )
    )
    if open_jobs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{vendor.name} still has {open_jobs} job(s) in progress. Reassign them first.",
        )

    vendor.is_active = False
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vendor.deactivated",
        entity_type="vendor",
        entity_id=vendor.id,
        actor=context.user,
        summary=f"Deactivated vendor {vendor.name}",
        request=request,
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def list_vendors(
    db: AsyncSession,
    context: OrgContext,
    *,
    specialty: VendorSpecialty | None = None,
    category: str | None = None,
    search: str | None = None,
    active_only: bool = True,
    limit: int = 200,
) -> list[Vendor]:
    """The registry, optionally narrowed to whoever can do a given job.

    `category` takes a maintenance category and expands it into the specialties
    that can answer it, so the assignment screen can ask for "who fixes this"
    without knowing the mapping.
    """
    query = select(Vendor).where(Vendor.organization_id == context.organization_id)

    if active_only:
        query = query.where(Vendor.is_active.is_(True), Vendor.is_archived.is_(False))
    if specialty:
        query = query.where(Vendor.specialties.contains([specialty.value]))
    elif category:
        wanted = CATEGORY_SPECIALTIES.get(category, ())
        if wanted:
            query = query.where(or_(*[Vendor.specialties.contains([s.value]) for s in wanted]))
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Vendor.name.ilike(term),
                Vendor.company_name.ilike(term),
                Vendor.phone_number.ilike(term),
            )
        )

    # Best-rated first, then the most-used — a fresh vendor with no jobs sorts
    # below a proven one rather than above it.
    rows = await db.scalars(
        query.order_by(
            (Vendor.rating_total / func.nullif(Vendor.rating_count, 0)).desc().nulls_last(),
            Vendor.jobs_completed.desc(),
            Vendor.name.asc(),
        ).limit(limit)
    )
    return list(rows)


async def get_vendor(db: AsyncSession, context: OrgContext, vendor_id: uuid.UUID) -> Vendor:
    return assert_in_org(await db.get(Vendor, vendor_id), context, label="vendor")


async def vendor_jobs(
    db: AsyncSession, context: OrgContext, vendor_id: uuid.UUID, *, limit: int = 50
) -> list[MaintenanceRequest]:
    rows = await db.scalars(
        select(MaintenanceRequest)
        .where(
            MaintenanceRequest.organization_id == context.organization_id,
            MaintenanceRequest.vendor_id == vendor_id,
        )
        .order_by(MaintenanceRequest.created_at.desc())
        .limit(limit)
    )
    return list(rows)


def record_job_result(vendor: Vendor, *, cost: Decimal | None, rating: int | None) -> None:
    """Fold one finished job into the vendor's running performance counters.

    Called from the maintenance completion path inside that transaction, so the
    counters and the job's own record can never disagree.
    """
    vendor.jobs_completed += 1
    if cost is not None:
        vendor.total_billed = Decimal(vendor.total_billed) + Decimal(cost)
    if rating is not None:
        vendor.rating_total += rating
        vendor.rating_count += 1
