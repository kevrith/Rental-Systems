"""Vacancy listings, the lead pipeline and data export (US-074 to US-077)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.file import StoredFile
from app.models.property import Property, Unit
from app.models.user import User
from app.models.vacancy import DataExport, ExportFormat, Inquiry, LeadStage
from app.schemas.vacancy import (
    ConversionReport,
    ExportDetail,
    ExportRead,
    ExportRequest,
    InquiryCreate,
    InquiryDetail,
    InquiryRead,
    InquiryUpdate,
    ListingRead,
    ListingUpdate,
    PublicListing,
    VacancyReport,
)
from app.services import export_service, file_service, vacancy_service

router = APIRouter()
public_router = APIRouter()

MEDIA_TYPES = {
    ExportFormat.CSV: "text/csv",
    ExportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.PARQUET: "application/vnd.apache.parquet",
}


async def _inquiry_detail(db: AsyncSession, inquiry: Inquiry) -> InquiryDetail:
    unit = await db.get(Unit, inquiry.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    return InquiryDetail(
        **InquiryRead.model_validate(inquiry).model_dump(),
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
    )


# ---------------------------------------------------------------- the desk


@router.get("", response_model=VacancyReport)
async def vacancy_desk(
    context: OrgContext = Depends(require(Permission.UNIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> VacancyReport:
    """Every empty unit, how long it has been empty, and what that has cost."""
    return VacancyReport(**await vacancy_service.vacancy_report(db, context))


@router.get("/conversion", response_model=ConversionReport)
async def conversion(
    context: OrgContext = Depends(require(Permission.DASHBOARD_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ConversionReport:
    return ConversionReport(**await vacancy_service.conversion_report(db, context))


@router.get("/units/{unit_id}/listing", response_model=ListingRead)
async def listing_for_unit(
    unit_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.UNIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ListingRead:
    """The unit's listing, created on first use."""
    listing = await vacancy_service.get_listing_for_unit(db, context, unit_id)
    return ListingRead.model_validate(listing)


@router.patch("/listings/{listing_id}", response_model=ListingRead)
async def update_listing(
    listing_id: uuid.UUID,
    payload: ListingUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.UNIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ListingRead:
    listing = await vacancy_service.update_listing(db, context, listing_id, payload, request)
    return ListingRead.model_validate(listing)


@router.post("/listings/{listing_id}/rotate-link", response_model=ListingRead)
async def rotate_link(
    listing_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.UNIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ListingRead:
    """Replace an over-shared link. The old one stops working immediately."""
    listing = await vacancy_service.rotate_slug(db, context, listing_id)
    return ListingRead.model_validate(listing)


# ------------------------------------------------------------------- leads


@router.get("/inquiries", response_model=list[InquiryDetail])
async def list_inquiries(
    unit_id: uuid.UUID | None = None,
    stage: LeadStage | None = None,
    stale_only: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.TENANT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[InquiryDetail]:
    rows = await vacancy_service.list_inquiries(
        db, context, unit_id=unit_id, stage=stage, stale_only=stale_only, limit=limit
    )
    return [await _inquiry_detail(db, row) for row in rows]


@router.patch("/inquiries/{inquiry_id}", response_model=InquiryDetail)
async def update_inquiry(
    inquiry_id: uuid.UUID,
    payload: InquiryUpdate,
    context: OrgContext = Depends(require_write(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> InquiryDetail:
    inquiry = await vacancy_service.update_inquiry(
        db,
        context,
        inquiry_id,
        stage=payload.stage,
        notes=payload.notes,
        mark_contacted=payload.mark_contacted,
    )
    return await _inquiry_detail(db, inquiry)


# ------------------------------------------------------------------ export


@router.post("/exports")
async def create_export(
    payload: ExportRequest,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Build the export and stream it back. Every export is logged (US-077)."""
    data, filename, row_count = await export_service.build(
        db,
        context,
        payload.kind,
        payload.export_format,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    await export_service.record_export(
        db,
        context,
        payload.kind,
        payload.export_format,
        row_count,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    return Response(
        content=data,
        media_type=MEDIA_TYPES[payload.export_format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Row-Count": str(row_count),
        },
    )


@router.get("/exports", response_model=list[ExportDetail])
async def list_exports(
    limit: int = Query(default=50, ge=1, le=200),
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ExportDetail]:
    rows = await db.scalars(
        select(DataExport)
        .where(DataExport.organization_id == context.organization_id)
        .order_by(DataExport.created_at.desc())
        .limit(limit)
    )

    details = []
    for record in rows:
        stored = await db.get(StoredFile, record.file_id) if record.file_id else None
        requester = await db.get(User, record.requested_by_id) if record.requested_by_id else None
        details.append(
            ExportDetail(
                **ExportRead.model_validate(record).model_dump(),
                download_url=file_service.to_url(stored) if stored else None,
                requested_by_name=requester.full_name if requester else None,
            )
        )
    return details


# ------------------------------------------------------------------ public


@public_router.get("/{slug}", response_model=PublicListing)
async def read_listing(slug: str, db: AsyncSession = Depends(get_db)) -> PublicListing:
    """The advert. No auth — this is meant to be shared (US-074)."""
    return PublicListing(**await vacancy_service.public_listing(db, slug))


@public_router.post("/{slug}/inquire", status_code=status.HTTP_201_CREATED)
async def make_inquiry(slug: str, payload: InquiryCreate, db: AsyncSession = Depends(get_db)) -> dict:
    inquiry = await vacancy_service.capture_inquiry(
        db,
        slug,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        message=payload.message,
    )
    return {
        "status": inquiry.stage.value,
        "message": (
            "Thank you. The landlord has your details and will be in touch shortly. "
            "You can also apply online now if you would like to."
        ),
    }
