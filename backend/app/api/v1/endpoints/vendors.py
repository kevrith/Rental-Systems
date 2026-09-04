import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.operations import MaintenanceRequest, MaintenanceStatus
from app.models.property import Property, Unit
from app.models.vendor import Vendor, VendorSpecialty
from app.schemas.vendor import (
    VendorCreate,
    VendorDetail,
    VendorJobSummary,
    VendorRead,
    VendorUpdate,
)
from app.services import vendor_service

router = APIRouter()


def _read(vendor: Vendor) -> VendorRead:
    return VendorRead(
        **{
            field: getattr(vendor, field)
            for field in (
                "id",
                "organization_id",
                "name",
                "company_name",
                "specialties",
                "phone_number",
                "email",
                "rate_notes",
                "notes",
                "is_active",
                "jobs_completed",
                "rating_count",
                "total_billed",
                "created_at",
            )
        },
        average_rating=vendor.average_rating,
        average_job_cost=vendor.average_job_cost,
    )


@router.post("", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.VENDOR_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> VendorRead:
    return _read(await vendor_service.create_vendor(db, context, payload, request))


@router.get("", response_model=list[VendorRead])
async def list_vendors(
    specialty: VendorSpecialty | None = None,
    category: str | None = Query(
        default=None,
        description="A maintenance category — returns the vendors whose specialties can answer it",
    ),
    search: str | None = None,
    include_inactive: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.VENDOR_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[VendorRead]:
    rows = await vendor_service.list_vendors(
        db,
        context,
        specialty=specialty,
        category=category,
        search=search,
        active_only=not include_inactive,
        limit=limit,
    )
    return [_read(vendor) for vendor in rows]


@router.get("/{vendor_id}", response_model=VendorDetail)
async def get_vendor(
    vendor_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.VENDOR_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> VendorDetail:
    vendor = await vendor_service.get_vendor(db, context, vendor_id)
    jobs = await vendor_service.vendor_jobs(db, context, vendor_id)

    open_jobs = int(
        await db.scalar(
            select(func.count(MaintenanceRequest.id)).where(
                MaintenanceRequest.vendor_id == vendor.id,
                MaintenanceRequest.status.in_([MaintenanceStatus.ASSIGNED, MaintenanceStatus.IN_PROGRESS]),
            )
        )
        or 0
    )

    summaries: list[VendorJobSummary] = []
    for job in jobs:
        unit = await db.get(Unit, job.unit_id)
        property_record = await db.get(Property, unit.property_id) if unit else None
        summaries.append(
            VendorJobSummary(
                id=job.id,
                reference_code=job.reference_code,
                title=job.title,
                status=job.status.value,
                completed_at=job.completed_at,
                cost=job.cost,
                rating=job.vendor_rating,
                property_name=property_record.name if property_record else None,
                unit_number=unit.unit_number if unit else None,
            )
        )

    return VendorDetail(
        **_read(vendor).model_dump(),
        open_jobs=open_jobs,
        recent_jobs=summaries,
    )


@router.patch("/{vendor_id}", response_model=VendorRead)
async def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.VENDOR_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> VendorRead:
    return _read(await vendor_service.update_vendor(db, context, vendor_id, payload, request))


@router.post("/{vendor_id}/deactivate", response_model=VendorRead)
async def deactivate_vendor(
    vendor_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.VENDOR_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> VendorRead:
    return _read(await vendor_service.deactivate_vendor(db, context, vendor_id, request))
