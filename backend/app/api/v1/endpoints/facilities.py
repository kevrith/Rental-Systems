"""Compliance, parking, amenities and utility accounts (US-078 to US-081)."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.facilities import (
    Amenity,
    BookingStatus,
    ComplianceItem,
    ComplianceStatus,
    ParkingAllocation,
)
from app.models.file import StoredFile
from app.models.property import Property
from app.models.tenant import Tenant
from app.schemas.facilities import (
    AllocationCreate,
    AllocationRead,
    AmenityCreate,
    AmenityRead,
    AmenityUsageRow,
    BayCreate,
    BlockCreate,
    BookingCreate,
    BookingDetail,
    BookingRead,
    ComplianceCreate,
    ComplianceDetail,
    ComplianceRead,
    ComplianceUpdate,
    ParkingOverview,
    UtilityAccountRead,
    UtilityAccountUpsert,
    UtilityStatusUpdate,
)
from app.services import compliance_report_service, facilities_service, file_service

compliance_router = APIRouter()
parking_router = APIRouter()
amenities_router = APIRouter()
utilities_router = APIRouter()


async def _compliance_detail(db: AsyncSession, item: ComplianceItem) -> ComplianceDetail:
    property_record = await db.get(Property, item.property_id)
    document = await db.get(StoredFile, item.document_id) if item.document_id else None
    return ComplianceDetail(
        **ComplianceRead.model_validate(item).model_dump(),
        property_name=property_record.name if property_record else None,
        document_url=file_service.to_url(document) if document else None,
    )


# ------------------------------------------------------------------ compliance


@compliance_router.get("/dashboard")
async def compliance_dashboard(
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Traffic light per property: green, amber at 60 days, red when expired."""
    return await facilities_service.compliance_dashboard(db, context)


@compliance_router.get("/report")
async def compliance_report(
    property_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The auditor's PDF: every item and its status, per property (US-078)."""
    pdf_bytes, filename = await compliance_report_service.render(db, context, property_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@compliance_router.get("", response_model=list[ComplianceDetail])
async def list_compliance(
    property_id: uuid.UUID | None = None,
    item_status: ComplianceStatus | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ComplianceDetail]:
    rows = await facilities_service.list_compliance_items(
        db, context, property_id=property_id, item_status=item_status
    )
    return [await _compliance_detail(db, item) for item in rows]


@compliance_router.post("", response_model=ComplianceDetail, status_code=status.HTTP_201_CREATED)
async def create_compliance(
    payload: ComplianceCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ComplianceDetail:
    item = await facilities_service.create_compliance_item(db, context, payload, request)
    return await _compliance_detail(db, item)


@compliance_router.patch("/{item_id}", response_model=ComplianceDetail)
async def update_compliance(
    item_id: uuid.UUID,
    payload: ComplianceUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ComplianceDetail:
    item = await facilities_service.update_compliance_item(db, context, item_id, payload, request)
    return await _compliance_detail(db, item)


# --------------------------------------------------------------------- parking


@parking_router.get("/property/{property_id}", response_model=ParkingOverview)
async def parking_overview(
    property_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ParkingOverview:
    return ParkingOverview(**await facilities_service.parking_overview(db, context, property_id))


@parking_router.post("/bays", status_code=status.HTTP_201_CREATED)
async def create_bay(
    payload: BayCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    bay = await facilities_service.create_bay(db, context, payload, request)
    return {"id": str(bay.id), "bay_number": bay.bay_number}


@parking_router.post(
    "/bays/{bay_id}/allocate", response_model=AllocationRead, status_code=status.HTTP_201_CREATED
)
async def allocate_bay(
    bay_id: uuid.UUID,
    payload: AllocationCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AllocationRead:
    allocation = await facilities_service.allocate_bay(db, context, bay_id, payload, request)
    return AllocationRead.model_validate(allocation)


@parking_router.post("/allocations/{allocation_id}/release", response_model=AllocationRead)
async def release_bay(
    allocation_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AllocationRead:
    allocation = await facilities_service.release_bay(db, context, allocation_id)
    return AllocationRead.model_validate(allocation)


@parking_router.get("/allocations", response_model=list[AllocationRead])
async def list_allocations(
    tenancy_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AllocationRead]:
    query = select(ParkingAllocation).where(ParkingAllocation.organization_id == context.organization_id)
    if tenancy_id:
        query = query.where(ParkingAllocation.tenancy_id == tenancy_id)
    rows = await db.scalars(query.order_by(ParkingAllocation.start_date.desc()).limit(200))
    return [AllocationRead.model_validate(row) for row in rows]


# ------------------------------------------------------------------- amenities


@amenities_router.get("", response_model=list[AmenityRead])
async def list_amenities(
    property_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AmenityRead]:
    query = select(Amenity).where(Amenity.organization_id == context.organization_id)
    if property_id:
        query = query.where(Amenity.property_id == property_id)
    rows = await db.scalars(query.order_by(Amenity.name))
    return [AmenityRead.model_validate(row) for row in rows]


@amenities_router.post("", response_model=AmenityRead, status_code=status.HTTP_201_CREATED)
async def create_amenity(
    payload: AmenityCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> AmenityRead:
    amenity = await facilities_service.create_amenity(db, context, payload, request)
    return AmenityRead.model_validate(amenity)


@amenities_router.get("/{amenity_id}/calendar", response_model=list[BookingDetail])
async def amenity_calendar(
    amenity_id: uuid.UUID,
    day_from: date | None = None,
    day_to: date | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[BookingDetail]:
    """What is taken, so the picker can grey out the slots that are gone."""
    start = day_from or date.today()
    rows = await facilities_service.amenity_calendar(
        db, context, amenity_id, day_from=start, day_to=day_to or start + timedelta(days=30)
    )

    amenity = await db.get(Amenity, amenity_id)
    details = []
    for booking in rows:
        tenant = await db.get(Tenant, booking.tenant_id) if booking.tenant_id else None
        details.append(
            BookingDetail(
                **BookingRead.model_validate(booking).model_dump(),
                tenant_name=tenant.full_name if tenant else None,
                amenity_name=amenity.name if amenity else None,
            )
        )
    return details


@amenities_router.post(
    "/{amenity_id}/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED
)
async def book_amenity(
    amenity_id: uuid.UUID,
    payload: BookingCreate,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking = await facilities_service.book_amenity(
        db,
        context,
        amenity_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        tenancy_id=payload.tenancy_id,
        purpose=payload.purpose,
        guests=payload.guests,
    )
    return BookingRead.model_validate(booking)


@amenities_router.post("/{amenity_id}/block", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def block_amenity(
    amenity_id: uuid.UUID,
    payload: BlockCreate,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    """Take the amenity out of service — a booking nobody can book over."""
    booking = await facilities_service.book_amenity(
        db,
        context,
        amenity_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        tenancy_id=None,
        purpose=payload.reason,
        status_override=BookingStatus.BLOCKED,
    )
    return BookingRead.model_validate(booking)


@amenities_router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking = await facilities_service.cancel_booking(db, context, booking_id)
    return BookingRead.model_validate(booking)


@amenities_router.get("/usage/{property_id}", response_model=list[AmenityUsageRow])
async def amenity_usage(
    property_id: uuid.UUID,
    months: int = Query(default=1, ge=1, le=24),
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AmenityUsageRow]:
    rows = await facilities_service.amenity_usage(db, context, property_id, months=months)
    return [AmenityUsageRow(**row) for row in rows]


# ------------------------------------------------------------ utility accounts


@utilities_router.get("", response_model=list[UtilityAccountRead])
async def list_utility_accounts(
    property_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[UtilityAccountRead]:
    rows = await facilities_service.list_utility_accounts(db, context, property_id=property_id)
    return [UtilityAccountRead.model_validate(row) for row in rows]


@utilities_router.put("", response_model=UtilityAccountRead)
async def upsert_utility_account(
    payload: UtilityAccountUpsert,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> UtilityAccountRead:
    account = await facilities_service.upsert_utility_account(db, context, payload, request)
    return UtilityAccountRead.model_validate(account)


@utilities_router.post("/{account_id}/status", response_model=UtilityAccountRead)
async def update_utility_status(
    account_id: uuid.UUID,
    payload: UtilityStatusUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_STATUS_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> UtilityAccountRead:
    """A caretaker can mark the KPLC bill paid — they are the one at the counter."""
    account = await facilities_service.update_utility_status(
        db,
        context,
        account_id,
        payment_status=payload.payment_status,
        last_paid_on=payload.last_paid_on,
        last_amount=payload.last_amount,
        next_due_on=payload.next_due_on,
        request=request,
    )
    return UtilityAccountRead.model_validate(account)
