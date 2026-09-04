"""Inspection API endpoints — Phase 2 (US-049–US-052)."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.inspection import InspectionType
from app.services import inspection_service

router = APIRouter()


class RoomData(BaseModel):
    name: str
    condition: str | None = None
    notes: str | None = None
    photo_file_ids: list[str] = []


class InspectionCreate(BaseModel):
    unit_id: uuid.UUID
    tenancy_id: uuid.UUID | None = None
    inspection_type: InspectionType
    rooms_data: list[RoomData] | None = None
    notes: str | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None


class InspectionRoomsUpdate(BaseModel):
    rooms_data: list[RoomData]
    notes: str | None = None


class DeductionSet(BaseModel):
    deduction_amount: Decimal
    deduction_notes: str


@router.get("")
async def list_inspections(
    unit_id: uuid.UUID | None = None,
    tenancy_id: uuid.UUID | None = None,
    inspection_type: InspectionType | None = None,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await inspection_service.list_inspections(
        db, context, unit_id=unit_id, tenancy_id=tenancy_id, inspection_type=inspection_type
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_inspection(
    body: InspectionCreate,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    rooms = [r.model_dump() for r in body.rooms_data] if body.rooms_data else None
    return await inspection_service.create_inspection(
        db,
        context,
        unit_id=body.unit_id,
        tenancy_id=body.tenancy_id,
        inspection_type=body.inspection_type,
        rooms_data=rooms,
        notes=body.notes,
        gps_latitude=body.gps_latitude,
        gps_longitude=body.gps_longitude,
    )


@router.get("/compliance")
async def inspection_compliance(
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await inspection_service.compliance_summary(db, context)


@router.get("/{report_id}")
async def get_inspection(
    report_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """The report, with each room's photo ids resolved into signed URLs."""
    report = await inspection_service.get_inspection(db, context, report_id)
    return {
        "id": str(report.id),
        "reference_code": report.reference_code,
        "unit_id": str(report.unit_id),
        "tenancy_id": str(report.tenancy_id) if report.tenancy_id else None,
        "inspection_type": report.inspection_type.value,
        "status": report.status.value,
        "rooms_data": report.rooms_data,
        "rooms": await inspection_service.hydrate_rooms(db, report),
        "inspector_name": report.inspector_name,
        "gps_latitude": float(report.gps_latitude) if report.gps_latitude is not None else None,
        "gps_longitude": float(report.gps_longitude) if report.gps_longitude is not None else None,
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
        "notes": report.notes,
        "move_in_report_id": str(report.move_in_report_id) if report.move_in_report_id else None,
        "deposit_deduction": str(report.deposit_deduction) if report.deposit_deduction else None,
        "deduction_notes": report.deduction_notes,
        "tenant_acknowledged": report.tenant_acknowledged,
        "created_at": report.created_at.isoformat(),
    }


@router.get("/{report_id}/comparison")
async def inspection_comparison(
    report_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Move-out against move-in, room by room, for the review screen."""
    return await inspection_service.comparison(db, context, report_id)


@router.get("/{report_id}/documents")
async def inspection_documents(
    report_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Signed links to the report PDF and, for a move-out, the comparison PDF."""
    return await inspection_service.documents(db, context, report_id)


@router.patch("/{report_id}/rooms")
async def update_rooms(
    report_id: uuid.UUID,
    body: InspectionRoomsUpdate,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await inspection_service.update_inspection_rooms(
        db, context, report_id, [r.model_dump() for r in body.rooms_data], body.notes
    )


@router.post("/{report_id}/submit")
async def submit_inspection(
    report_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await inspection_service.submit_inspection(db, context, report_id)


@router.post("/{report_id}/deduction")
async def set_deposit_deduction(
    report_id: uuid.UUID,
    body: DeductionSet,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await inspection_service.set_deposit_deduction(
        db, context, report_id, body.deduction_amount, body.deduction_notes
    )


@router.post("/{report_id}/acknowledge")
async def acknowledge_inspection(
    report_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Tenant acknowledges their inspection report."""
    return await inspection_service.acknowledge_inspection(
        db, context.user.id, report_id, context.organization_id
    )
