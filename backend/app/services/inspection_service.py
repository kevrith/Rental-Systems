"""Inspection service — Phase 2 (US-049, US-050, US-051, US-052).

Handles move-in, move-out, and routine inspections with photo capture,
GPS tagging, and before/after comparison report generation.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.developer import WebhookEvent
from app.models.inspection import InspectionReport, InspectionStatus, InspectionType
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Unit
from app.models.tenant import Tenancy, Tenant
from app.services import audit_service, notification_service, reference_service, webhook_service

DEFAULT_ROOMS = {
    "bedsitter": ["Main Room", "Bathroom", "Kitchen Area"],
    "1br": ["Living Room", "Bedroom", "Bathroom", "Kitchen"],
    "2br": ["Living Room", "Bedroom 1", "Bedroom 2", "Bathroom", "Kitchen"],
    "3br": ["Living Room", "Bedroom 1", "Bedroom 2", "Bedroom 3", "Bathroom", "Kitchen"],
    "default": ["Living Room", "Bedroom", "Bathroom", "Kitchen"],
}


def _default_rooms(unit_type: str | None) -> list[dict]:
    key = (unit_type or "").lower().replace(" ", "")
    room_names = DEFAULT_ROOMS.get(key, DEFAULT_ROOMS["default"])
    return [{"name": name, "condition": None, "notes": "", "photo_file_ids": []} for name in room_names]


async def create_inspection(
    db: AsyncSession,
    context: OrgContext,
    *,
    unit_id: uuid.UUID,
    tenancy_id: uuid.UUID | None,
    inspection_type: InspectionType,
    rooms_data: list[dict] | None = None,
    notes: str | None = None,
    gps_latitude: float | None = None,
    gps_longitude: float | None = None,
) -> InspectionReport:
    unit = assert_in_org(await db.get(Unit, unit_id), context, label="unit")

    code = await reference_service.generate_reference(db, InspectionReport, context.organization_id, "INS")
    report = InspectionReport(
        organization_id=context.organization_id,
        reference_code=code,
        unit_id=unit_id,
        tenancy_id=tenancy_id,
        inspection_type=inspection_type,
        status=InspectionStatus.DRAFT,
        rooms_data=rooms_data or _default_rooms(unit.unit_type),
        inspector_id=context.user.id,
        inspector_name=context.user.full_name,
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
        notes=notes,
    )
    db.add(report)
    await db.flush()
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="inspection.created",
        entity_type="inspection_report",
        entity_id=report.id,
        actor=context.user,
        summary=f"{inspection_type.value} inspection created for unit {unit.unit_number}",
    )
    await db.commit()
    await db.refresh(report)
    return report


async def update_inspection_rooms(
    db: AsyncSession,
    context: OrgContext,
    report_id: uuid.UUID,
    rooms_data: list[dict],
    notes: str | None = None,
) -> InspectionReport:
    report = assert_in_org(await db.get(InspectionReport, report_id), context, label="inspection report")
    if report.status == InspectionStatus.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Submitted inspections cannot be modified"
        )
    report.rooms_data = rooms_data
    if notes is not None:
        report.notes = notes
    await db.commit()
    await db.refresh(report)
    return report


async def submit_inspection(
    db: AsyncSession,
    context: OrgContext,
    report_id: uuid.UUID,
) -> InspectionReport:
    """Submit an inspection — makes it immutable and generates the PDF."""
    report = assert_in_org(await db.get(InspectionReport, report_id), context, label="inspection report")
    if report.status == InspectionStatus.SUBMITTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already submitted")

    # Validate: every room must have at least one photo
    for room in report.rooms_data:
        if not room.get("photo_file_ids"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Room '{room.get('name', 'unknown')}' requires at least one photo",
            )
        if not room.get("condition"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Room '{room.get('name', 'unknown')}' requires a condition rating",
            )

    report.status = InspectionStatus.SUBMITTED
    report.submitted_at = datetime.now(UTC)

    # For move-out: find the matching move-in report and link it
    if report.inspection_type == InspectionType.MOVE_OUT and report.tenancy_id:
        move_in = await db.scalar(
            select(InspectionReport).where(
                InspectionReport.organization_id == context.organization_id,
                InspectionReport.tenancy_id == report.tenancy_id,
                InspectionReport.inspection_type == InspectionType.MOVE_IN,
                InspectionReport.status == InspectionStatus.SUBMITTED,
            )
        )
        if move_in:
            report.move_in_report_id = move_in.id

    await db.flush()

    # Generate the PDF report, and for a move-out the comparison against move-in.
    # The evidence is the `rooms_data` and its photos; the PDFs are a convenience
    # rendering of it, so a rendering failure is logged rather than fatal.
    try:
        from app.services.inspection_pdf_service import (
            generate_comparison_pdf,
            generate_inspection_pdf,
        )

        report.report_document_id = await generate_inspection_pdf(db, report, context.organization_id)
        if report.move_in_report_id:
            move_in_report = await db.get(InspectionReport, report.move_in_report_id)
            if move_in_report is not None:
                report.comparison_document_id = await generate_comparison_pdf(
                    db, report, move_in_report, context.organization_id
                )
    except Exception:  # noqa: BLE001 — the inspection record itself is already saved
        logging.getLogger("rentflow.inspection").exception(
            "Inspection PDF generation failed for %s", report.reference_code
        )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="inspection.submitted",
        entity_type="inspection_report",
        entity_id=report.id,
        actor=context.user,
        summary=f"{report.inspection_type.value} inspection submitted for unit {report.unit_id}",
    )

    # Notify tenant and owners
    await _notify_inspection_submitted(db, report, context.organization_id)

    await db.commit()
    await db.refresh(report)
    await webhook_service.dispatch(
        db,
        context.organization_id,
        WebhookEvent.INSPECTION_COMPLETED,
        {
            "id": str(report.id),
            "reference_code": report.reference_code,
            "inspection_type": report.inspection_type.value,
            "unit_id": str(report.unit_id),
            "tenancy_id": str(report.tenancy_id) if report.tenancy_id else None,
            "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
        },
    )
    return report


async def set_deposit_deduction(
    db: AsyncSession,
    context: OrgContext,
    report_id: uuid.UUID,
    deduction_amount: Decimal,
    deduction_notes: str,
) -> InspectionReport:
    report = assert_in_org(await db.get(InspectionReport, report_id), context, label="inspection report")
    if report.inspection_type != InspectionType.MOVE_OUT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit deductions only apply to move-out inspections",
        )
    if report.status != InspectionStatus.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submit the inspection before deducting from the deposit",
        )
    if deduction_amount < Decimal("0"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A deduction cannot be negative")

    # A deduction may never exceed the deposit actually held.
    if report.tenancy_id:
        tenancy = await db.get(Tenancy, report.tenancy_id)
        if tenancy is not None and deduction_amount > Decimal(tenancy.deposit_amount):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"The deduction is more than the deposit held "
                    f"(KES {Decimal(tenancy.deposit_amount):,.2f})"
                ),
            )

    report.deposit_deduction = deduction_amount
    report.deduction_notes = deduction_notes
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="inspection.deduction_set",
        entity_type="inspection_report",
        entity_id=report.id,
        actor=context.user,
        summary=f"Deposit deduction of KES {deduction_amount} set",
    )
    await db.commit()
    await db.refresh(report)
    return report


async def acknowledge_inspection(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    report_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> InspectionReport:
    """Tenant acknowledges receipt of their inspection report."""
    report = await db.get(InspectionReport, report_id)
    if not report or report.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection report not found")
    report.tenant_acknowledged = True
    report.tenant_acknowledged_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(report)
    return report


async def list_inspections(
    db: AsyncSession,
    context: OrgContext,
    unit_id: uuid.UUID | None = None,
    tenancy_id: uuid.UUID | None = None,
    inspection_type: InspectionType | None = None,
) -> list[InspectionReport]:
    query = select(InspectionReport).where(InspectionReport.organization_id == context.organization_id)
    if unit_id:
        query = query.where(InspectionReport.unit_id == unit_id)
    if tenancy_id:
        query = query.where(InspectionReport.tenancy_id == tenancy_id)
    if inspection_type:
        query = query.where(InspectionReport.inspection_type == inspection_type)
    rows = await db.scalars(query.order_by(InspectionReport.created_at.desc()))
    return list(rows)


async def get_inspection(db: AsyncSession, context: OrgContext, report_id: uuid.UUID) -> InspectionReport:
    report = await db.get(InspectionReport, report_id)
    return assert_in_org(report, context, label="inspection report")


async def compliance_summary(db: AsyncSession, context: OrgContext) -> dict:
    """Where the inspection record is incomplete, named well enough to act on.

    Two gaps matter. A tenancy with no move-in inspection has no baseline, so any
    later deposit deduction is unarguable in the tenant's favour. A tenancy that
    has not been inspected in over a year is a property nobody has looked at.
    """
    from app.models.property import Property
    from app.models.tenant import TenancyStatus

    active_tenancies = list(
        await db.scalars(
            select(Tenancy).where(
                Tenancy.organization_id == context.organization_id,
                Tenancy.status.in_([TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON]),
            )
        )
    )
    if not active_tenancies:
        return {
            "total_active_tenancies": 0,
            "missing_move_in_inspection": 0,
            "overdue_routine_inspection": 0,
            "coverage_percent": 100.0,
            "missing_move_in": [],
            "overdue_routine": [],
        }

    tenancy_ids = [t.id for t in active_tenancies]
    unit_ids = list({t.unit_id for t in active_tenancies})

    # One pass over every submitted inspection for these tenancies, rather than a
    # query per tenancy — this runs on the dashboard.
    rows = list(
        await db.execute(
            select(
                InspectionReport.tenancy_id,
                InspectionReport.inspection_type,
                InspectionReport.submitted_at,
            ).where(
                InspectionReport.organization_id == context.organization_id,
                InspectionReport.tenancy_id.in_(tenancy_ids),
                InspectionReport.status == InspectionStatus.SUBMITTED,
            )
        )
    )
    has_move_in: set[uuid.UUID] = set()
    last_seen: dict[uuid.UUID, datetime] = {}
    for tenancy_id, inspection_type, submitted_at in rows:
        if inspection_type == InspectionType.MOVE_IN:
            has_move_in.add(tenancy_id)
        if submitted_at and submitted_at > last_seen.get(tenancy_id, submitted_at - timedelta(days=1)):
            last_seen[tenancy_id] = submitted_at

    units = {unit.id: unit for unit in await db.scalars(select(Unit).where(Unit.id.in_(unit_ids)))}
    properties = {
        record.id: record
        for record in await db.scalars(
            select(Property).where(Property.id.in_({u.property_id for u in units.values()}))
        )
    }
    tenants = {
        tenant.id: tenant
        for tenant in await db.scalars(
            select(Tenant).where(Tenant.id.in_({t.tenant_id for t in active_tenancies}))
        )
    }

    def describe(tenancy: Tenancy) -> dict:
        unit = units.get(tenancy.unit_id)
        property_record = properties.get(unit.property_id) if unit else None
        tenant = tenants.get(tenancy.tenant_id)
        return {
            "tenancy_id": str(tenancy.id),
            "tenancy_reference": tenancy.reference_code,
            "unit_id": str(tenancy.unit_id),
            "unit_number": unit.unit_number if unit else "—",
            "property_id": str(unit.property_id) if unit else None,
            "property_name": property_record.name if property_record else "—",
            "tenant_name": tenant.full_name if tenant else "—",
            "start_date": tenancy.start_date.isoformat(),
        }

    stale_before = datetime.now(UTC) - timedelta(days=365)
    missing_move_in = []
    overdue_routine = []
    for tenancy in active_tenancies:
        if tenancy.id not in has_move_in:
            missing_move_in.append(describe(tenancy))
        seen = last_seen.get(tenancy.id)
        if seen is None or seen < stale_before:
            entry = describe(tenancy)
            entry["last_inspected_at"] = seen.isoformat() if seen else None
            overdue_routine.append(entry)

    covered = len(active_tenancies) - len(missing_move_in)
    return {
        "total_active_tenancies": len(active_tenancies),
        "missing_move_in_inspection": len(missing_move_in),
        "overdue_routine_inspection": len(overdue_routine),
        "coverage_percent": round(covered / len(active_tenancies) * 100, 1),
        "missing_move_in": missing_move_in,
        "overdue_routine": overdue_routine,
    }


# ------------------------------------------------------------- comparison (US-050)

_CONDITION_RANK = {"excellent": 4, "good": 3, "fair": 2, "poor": 1}


def _rank(condition: str | None) -> int:
    return _CONDITION_RANK.get((condition or "").lower(), 0)


async def _photo_urls(db: AsyncSession, file_ids: list) -> list[dict]:
    """Resolve stored photo ids into signed URLs the viewer can render."""
    from app.models.file import StoredFile
    from app.services import file_service

    resolved: list[dict] = []
    for raw in file_ids or []:
        try:
            file_id = uuid.UUID(str(raw))
        except (ValueError, AttributeError):
            continue
        record = await db.get(StoredFile, file_id)
        if record is None:
            continue
        resolved.append(
            {"id": str(record.id), "filename": record.filename, "url": file_service.to_url(record)}
        )
    return resolved


async def hydrate_rooms(db: AsyncSession, report: InspectionReport) -> list[dict]:
    """`rooms_data` with each photo id turned into a signed URL."""
    rooms = []
    for room in report.rooms_data or []:
        rooms.append(
            {
                **room,
                "photos": await _photo_urls(db, room.get("photo_file_ids", [])),
            }
        )
    return rooms


async def comparison(db: AsyncSession, context: OrgContext, report_id: uuid.UUID) -> dict:
    """Move-out against move-in, room by room, for the review screen.

    Rooms are matched by name — the move-out report is seeded from the unit's own
    room list, so the names line up — and a room present in only one report is
    still shown, with the missing side left null.
    """
    report = await get_inspection(db, context, report_id)
    if report.inspection_type != InspectionType.MOVE_OUT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a move-out inspection can be compared against a move-in",
        )

    baseline: InspectionReport | None = None
    if report.move_in_report_id:
        baseline = await db.get(InspectionReport, report.move_in_report_id)
    if baseline is None and report.tenancy_id:
        baseline = await db.scalar(
            select(InspectionReport).where(
                InspectionReport.organization_id == context.organization_id,
                InspectionReport.tenancy_id == report.tenancy_id,
                InspectionReport.inspection_type == InspectionType.MOVE_IN,
                InspectionReport.status == InspectionStatus.SUBMITTED,
            )
        )

    move_out_rooms = await hydrate_rooms(db, report)
    move_in_rooms = await hydrate_rooms(db, baseline) if baseline else []
    before_by_name = {str(room.get("name", "")).lower(): room for room in move_in_rooms}

    rows = []
    degraded = 0
    for after in move_out_rooms:
        name = str(after.get("name", ""))
        before = before_by_name.pop(name.lower(), None)
        delta = _rank(after.get("condition")) - _rank(before.get("condition") if before else None)
        # A room with no baseline has no meaningful delta — it is not damage.
        changed = "unchanged" if before is None or delta == 0 else ("worse" if delta < 0 else "better")
        if changed == "worse":
            degraded += 1
        rows.append({"name": name, "before": before, "after": after, "change": changed})

    # Anything only the move-in recorded — a room that was not re-inspected.
    for leftover in before_by_name.values():
        rows.append(
            {
                "name": str(leftover.get("name", "")),
                "before": leftover,
                "after": None,
                "change": "not_inspected",
            }
        )

    unit = await db.get(Unit, report.unit_id)
    tenancy = await db.get(Tenancy, report.tenancy_id) if report.tenancy_id else None
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None

    return {
        "move_out": {
            "id": str(report.id),
            "reference_code": report.reference_code,
            "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
            "inspector_name": report.inspector_name,
            "notes": report.notes,
        },
        "move_in": (
            {
                "id": str(baseline.id),
                "reference_code": baseline.reference_code,
                "submitted_at": baseline.submitted_at.isoformat() if baseline.submitted_at else None,
                "inspector_name": baseline.inspector_name,
                "notes": baseline.notes,
            }
            if baseline
            else None
        ),
        "unit_number": unit.unit_number if unit else "—",
        "tenant_name": tenant.full_name if tenant else None,
        "deposit_held": str(tenancy.deposit_amount) if tenancy else None,
        "deposit_deduction": str(report.deposit_deduction) if report.deposit_deduction else None,
        "deduction_notes": report.deduction_notes,
        "rooms_degraded": degraded,
        "rooms": rows,
    }


async def documents(db: AsyncSession, context: OrgContext, report_id: uuid.UUID) -> dict:
    """Signed links to the report PDF and, for a move-out, the comparison PDF."""
    from app.models.file import StoredFile
    from app.services import file_service

    report = await get_inspection(db, context, report_id)

    async def link(file_id: uuid.UUID | None) -> dict | None:
        if file_id is None:
            return None
        record = await db.get(StoredFile, file_id)
        if record is None or record.organization_id != context.organization_id:
            return None
        return {"id": str(record.id), "filename": record.filename, "url": file_service.to_url(record)}

    return {
        "report": await link(report.report_document_id),
        "comparison": await link(report.comparison_document_id),
    }


async def _notify_inspection_submitted(
    db: AsyncSession, report: InspectionReport, organization_id: uuid.UUID
) -> None:
    from app.models.user import User, UserRole

    if report.tenancy_id:
        tenancy = await db.get(Tenancy, report.tenancy_id)
        if tenancy:
            tenant = await db.get(Tenant, tenancy.tenant_id)
            if tenant:
                await notification_service.send(
                    db,
                    recipient=notification_service.Recipient.for_tenant(tenant),
                    notification_type=NotificationType.INSPECTION_COMPLETED,
                    title=f"{report.inspection_type.value.replace('_', '-').title()} inspection completed",
                    body=(
                        f"Your {report.inspection_type.value.replace('_', ' ')} inspection report "
                        f"(ref: {report.reference_code}) has been submitted. "
                        f"You can view it in your tenant portal."
                    ),
                    channels=[NotificationChannel.WHATSAPP],
                    entity_type="inspection_report",
                    entity_id=report.id,
                    organization_id=organization_id,
                )

    owners = await db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.INSPECTION_COMPLETED,
            title="Inspection report submitted",
            body=(
                f"{report.inspection_type.value.replace('_', ' ').title()} inspection "
                f"{report.reference_code} submitted by {report.inspector_name}."
            ),
            channels=[NotificationChannel.PUSH],
            entity_type="inspection_report",
            entity_id=report.id,
            organization_id=organization_id,
        )
