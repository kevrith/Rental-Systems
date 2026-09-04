import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.schemas.property import (
    BulkCreateResult,
    PhotoRead,
    PortfolioDashboard,
    PropertyCreate,
    PropertyRead,
    PropertySummary,
    PropertyUpdate,
    UnitBulkCreate,
    UnitCreate,
    UnitDetail,
    UnitRead,
    UnitStatusUpdate,
    UnitUpdate,
)
from app.services import file_service, property_service

router = APIRouter()
units_router = APIRouter()
dashboard_router = APIRouter()


async def _photos(
    db: AsyncSession, org_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> list[PhotoRead]:
    records = await file_service.list_for_entity(db, org_id, entity_type, entity_id)
    return [PhotoRead(id=r.id, url=file_service.to_url(r), filename=r.filename) for r in records]


def _summary(record: Property, stats: dict | None, photos: list[PhotoRead]) -> PropertySummary:
    stats = stats or {}
    return PropertySummary(
        **PropertyRead.model_validate(record).model_dump(),
        total_units=stats.get("total_units", 0),
        occupied_units=stats.get("occupied_units", 0),
        vacant_units=stats.get("vacant_units", 0),
        maintenance_units=stats.get("maintenance_units", 0),
        reserved_units=stats.get("reserved_units", 0),
        occupancy_rate=stats.get("occupancy_rate", 0.0),
        monthly_rent_potential=stats.get("monthly_rent_potential", Decimal("0.00")),
        photos=photos,
    )


# --------------------------------------------------------------------- properties


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
async def create_property(
    payload: PropertyCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Property:
    return await property_service.create_property(db, context, payload, request)


@router.get("", response_model=list[PropertySummary])
async def list_properties(
    include_archived: bool = False,
    search: str | None = Query(default=None, max_length=255),
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[PropertySummary]:
    properties = await property_service.list_properties(db, context, include_archived, search)
    _, per_property = await property_service.portfolio_stats(db, context)
    photos_by_property = await file_service.list_for_entities(
        db, context.organization_id, "property", [p.id for p in properties]
    )
    return [
        _summary(
            record,
            per_property.get(record.id),
            [
                PhotoRead(id=f.id, url=file_service.to_url(f), filename=f.filename)
                for f in photos_by_property.get(record.id, [])
            ],
        )
        for record in properties
    ]


@router.get("/{property_id}", response_model=PropertySummary)
async def get_property(
    property_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> PropertySummary:
    record = await property_service.get_property(db, context, property_id)
    _, per_property = await property_service.portfolio_stats(db, context)
    photos = await _photos(db, context.organization_id, "property", record.id)
    return _summary(record, per_property.get(record.id), photos)


@router.patch("/{property_id}", response_model=PropertyRead)
async def update_property(
    property_id: uuid.UUID,
    payload: PropertyUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Property:
    return await property_service.update_property(db, context, property_id, payload, request)


@router.delete("/{property_id}", response_model=PropertyRead)
async def archive_property(
    property_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Property:
    return await property_service.archive_property(db, context, property_id, request)


@router.post("/{property_id}/restore", response_model=PropertyRead)
async def restore_property(
    property_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Property:
    return await property_service.restore_property(db, context, property_id, request)


@router.get("/{property_id}/units", response_model=list[UnitRead])
async def list_property_units(
    property_id: uuid.UUID,
    include_archived: bool = False,
    context: OrgContext = Depends(require(Permission.UNIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[Unit]:
    await property_service.get_property(db, context, property_id)
    return await property_service.list_units(
        db, context, property_id=property_id, include_archived=include_archived
    )


# -------------------------------------------------------------------------- units


@units_router.post("", response_model=UnitRead, status_code=status.HTTP_201_CREATED)
async def create_unit(
    payload: UnitCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Unit:
    return await property_service.create_unit(db, context, payload, request)


@units_router.post("/bulk", response_model=BulkCreateResult, status_code=status.HTTP_201_CREATED)
async def bulk_create_units(
    payload: UnitBulkCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BulkCreateResult:
    units = await property_service.bulk_create_units(db, context, payload, request)
    return BulkCreateResult(created=len(units), units=[UnitRead.model_validate(u) for u in units])


@units_router.get("", response_model=list[UnitRead])
async def list_units(
    property_id: uuid.UUID | None = None,
    unit_status: UnitStatus | None = None,
    include_archived: bool = False,
    search: str | None = Query(default=None, max_length=255),
    context: OrgContext = Depends(require(Permission.UNIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[Unit]:
    return await property_service.list_units(
        db,
        context,
        property_id=property_id,
        unit_status=unit_status,
        include_archived=include_archived,
        search=search,
    )


@units_router.get("/{unit_id}", response_model=UnitDetail)
async def get_unit(
    unit_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.UNIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> UnitDetail:
    record = await property_service.get_unit(db, context, unit_id)
    prop = await db.get(Property, record.property_id)
    photos = await _photos(db, context.organization_id, "unit", record.id)

    current = (
        await db.execute(
            select(Tenancy, Tenant)
            .join(Tenant, Tenant.id == Tenancy.tenant_id)
            .where(
                Tenancy.unit_id == record.id,
                Tenancy.status.in_(
                    [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]
                ),
            )
            .limit(1)
        )
    ).first()

    return UnitDetail(
        **UnitRead.model_validate(record).model_dump(),
        property_name=prop.name if prop else None,
        photos=photos,
        current_tenant_name=current[1].full_name if current else None,
        current_tenancy_id=current[0].id if current else None,
    )


@units_router.patch("/{unit_id}", response_model=UnitRead)
async def update_unit(
    unit_id: uuid.UUID,
    payload: UnitUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Unit:
    return await property_service.update_unit(db, context, unit_id, payload, request)


@units_router.patch("/{unit_id}/status", response_model=UnitRead)
async def update_unit_status(
    unit_id: uuid.UUID,
    payload: UnitStatusUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_STATUS_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> Unit:
    return await property_service.update_unit_status(db, context, unit_id, payload, request)


@units_router.delete("/{unit_id}", response_model=UnitRead)
async def archive_unit(
    unit_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Unit:
    return await property_service.archive_unit(db, context, unit_id, request)


# ---------------------------------------------------------------------- portfolio


@dashboard_router.get("/portfolio", response_model=PortfolioDashboard)
async def portfolio_dashboard(
    context: OrgContext = Depends(require(Permission.DASHBOARD_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> PortfolioDashboard:
    stats, per_property = await property_service.portfolio_stats(db, context)
    properties = await property_service.list_properties(db, context)
    photos_by_property = await file_service.list_for_entities(
        db, context.organization_id, "property", [p.id for p in properties]
    )
    return PortfolioDashboard(
        stats=stats,
        properties=[
            _summary(
                record,
                per_property.get(record.id),
                [
                    PhotoRead(id=f.id, url=file_service.to_url(f), filename=f.filename)
                    for f in photos_by_property.get(record.id, [])
                ],
            )
            for record in properties
        ],
    )
