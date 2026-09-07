"""Field operations: meter readings, maintenance requests and vacating notices
(Sprints 5 and 6).

The recurring theme is that the caretaker or tenant supplies evidence — a meter
photo, a photo of the fault, a dated notice — and the system turns it into
something billable or actionable without anyone re-keying it.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.file import FileCategory, StoredFile, UploadStatus
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import (
    OPEN_STATUSES,
    MaintenancePriority,
    MaintenanceRequest,
    MaintenanceStatus,
    MeterReading,
    MeterType,
    VacateNotice,
    VacateNoticeStatus,
    VisitorLog,
)
from app.models.organization import Organization
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import User, UserRole
from app.schemas.operations import (
    MaintenanceCreate,
    MaintenanceUpdate,
    MeterContext,
    MeterReadingCreate,
    VacateNoticeCreate,
    VisitorLogCreate,
)
from app.services import (
    audit_service,
    file_service,
    notification_service,
    pdf_service,
    reference_service,
    tenant_pii,
)

ZERO = Decimal("0.00")


async def _unit_in_scope(db: AsyncSession, context: OrgContext, unit_id: uuid.UUID) -> Unit:
    unit = assert_in_org(await db.get(Unit, unit_id), context, label="unit")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None and unit.property_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )
    return unit


async def _active_tenancy(db: AsyncSession, unit_id: uuid.UUID) -> Tenancy | None:
    return await db.scalar(
        select(Tenancy).where(
            Tenancy.unit_id == unit_id,
            Tenancy.status.in_(
                [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]
            ),
        )
    )


# ------------------------------------------------------------------ meter readings


def _configured_rate(property_record: Property, meter_type: MeterType) -> Decimal | None:
    rate = (
        property_record.water_rate_per_unit
        if meter_type == MeterType.WATER
        else property_record.electricity_rate_per_unit
    )
    return Decimal(rate) if rate is not None else None


async def meter_context(
    db: AsyncSession, context: OrgContext, unit_id: uuid.UUID, meter_type: MeterType
) -> MeterContext:
    """Pre-fill the capture form with the last reading and the configured rate."""
    unit = await _unit_in_scope(db, context, unit_id)
    property_record = await db.get(Property, unit.property_id)

    last = await db.scalar(
        select(MeterReading)
        .where(MeterReading.unit_id == unit.id, MeterReading.meter_type == meter_type)
        .order_by(MeterReading.reading_date.desc(), MeterReading.created_at.desc())
        .limit(1)
    )
    rate = _configured_rate(property_record, meter_type) if property_record else None

    return MeterContext(
        unit_id=unit.id,
        unit_number=unit.unit_number,
        property_name=property_record.name if property_record else "",
        meter_type=meter_type,
        previous_reading=Decimal(last.current_reading) if last else ZERO,
        previous_reading_date=last.reading_date if last else None,
        rate=rate or ZERO,
        has_rate_configured=rate is not None,
    )


async def record_meter_reading(
    db: AsyncSession, context: OrgContext, payload: MeterReadingCreate, request: Request | None = None
) -> MeterReading:
    unit = await _unit_in_scope(db, context, payload.unit_id)
    property_record = await db.get(Property, unit.property_id)

    photo = await db.get(StoredFile, payload.photo_file_id)
    if photo is None or photo.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meter photo not found")
    if photo.status != UploadStatus.UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Finish uploading the meter photo before submitting the reading",
        )

    existing = await meter_context(db, context, unit.id, payload.meter_type)
    previous = (
        Decimal(payload.previous_reading)
        if payload.previous_reading is not None
        else existing.previous_reading
    )

    if payload.current_reading < previous:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Current reading ({payload.current_reading}) is below the previous reading "
                f"({previous}). Check the meter, or record a meter replacement first."
            ),
        )

    duplicate = await db.scalar(
        select(MeterReading.id).where(
            MeterReading.unit_id == unit.id,
            MeterReading.meter_type == payload.meter_type,
            MeterReading.reading_date == payload.reading_date,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A reading for this meter and date already exists",
        )

    rate = (
        payload.rate
        if payload.rate is not None
        else (_configured_rate(property_record, payload.meter_type) if property_record else None) or ZERO
    )
    consumption = Decimal(payload.current_reading) - previous
    amount = (consumption * Decimal(rate)).quantize(Decimal("0.01"))

    reading = MeterReading(
        organization_id=context.organization_id,
        unit_id=unit.id,
        meter_type=payload.meter_type,
        previous_reading=previous,
        current_reading=payload.current_reading,
        consumption=consumption,
        rate=rate,
        amount=amount,
        reading_date=payload.reading_date,
        photo_file_id=photo.id,
        recorded_by_id=context.user.id,
        gps_latitude=payload.gps_latitude,
        gps_longitude=payload.gps_longitude,
        notes=payload.notes,
        ocr_reading=payload.ocr_reading,
        ocr_confidence=payload.ocr_confidence,
        # None, not False, when no suggestion was offered: "the caretaker
        # rejected the machine" and "the machine never spoke" are different
        # facts, and only the first says anything about OCR accuracy.
        ocr_accepted=(
            None
            if payload.ocr_reading is None
            else Decimal(payload.ocr_reading) == Decimal(payload.current_reading)
        ),
    )
    db.add(reading)
    await db.flush()

    photo.entity_type = "meter_reading"
    photo.entity_id = reading.id
    photo.category = FileCategory.METER_READING

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="meter_reading.recorded",
        entity_type="meter_reading",
        entity_id=reading.id,
        actor=context.user,
        summary=(
            f"{payload.meter_type.value.title()} reading for unit {unit.unit_number}: "
            f"{consumption} units, KES {pdf_service.format_kes(amount)}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(reading)
    return reading


async def list_meter_readings(
    db: AsyncSession,
    context: OrgContext,
    *,
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    meter_type: MeterType | None = None,
    limit: int = 100,
) -> list[MeterReading]:
    query = select(MeterReading).where(MeterReading.organization_id == context.organization_id)

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(MeterReading.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed))))
    if unit_id:
        query = query.where(MeterReading.unit_id == unit_id)
    if property_id:
        query = query.where(MeterReading.unit_id.in_(select(Unit.id).where(Unit.property_id == property_id)))
    if meter_type:
        query = query.where(MeterReading.meter_type == meter_type)

    rows = await db.scalars(query.order_by(MeterReading.reading_date.desc()).limit(limit))
    return list(rows)


async def readings_due(db: AsyncSession, context: OrgContext, limit: int = 25) -> list[MeterContext]:
    """Occupied units with no reading in the current calendar month."""
    today = date.today()
    month_start = today.replace(day=1)

    query = select(Unit).where(
        Unit.organization_id == context.organization_id,
        Unit.is_archived.is_(False),
        Unit.status.in_([UnitStatus.OCCUPIED, UnitStatus.VACATING]),
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Unit.property_id.in_(allowed))

    due: list[MeterContext] = []
    for unit in await db.scalars(query.limit(limit * 2)):
        property_record = await db.get(Property, unit.property_id)
        if property_record is None:
            continue
        for meter_type in (MeterType.WATER, MeterType.ELECTRICITY):
            if _configured_rate(property_record, meter_type) is None:
                continue  # This property doesn't meter this utility.
            recorded = await db.scalar(
                select(MeterReading.id).where(
                    MeterReading.unit_id == unit.id,
                    MeterReading.meter_type == meter_type,
                    MeterReading.reading_date >= month_start,
                )
            )
            if not recorded:
                due.append(await meter_context(db, context, unit.id, meter_type))
            if len(due) >= limit:
                return due
    return due


# -------------------------------------------------------------------- maintenance


async def create_maintenance_request(
    db: AsyncSession,
    context: OrgContext,
    payload: MaintenanceCreate,
    request: Request | None = None,
    *,
    tenant: Tenant | None = None,
) -> MaintenanceRequest:
    unit = (
        await _unit_in_scope(db, context, payload.unit_id)
        if tenant is None
        else assert_in_org(await db.get(Unit, payload.unit_id), context, label="unit")
    )
    tenancy = await _active_tenancy(db, unit.id)

    reference = await reference_service.generate_reference(
        db, MaintenanceRequest, context.organization_id, "MNT"
    )
    record = MaintenanceRequest(
        organization_id=context.organization_id,
        reference_code=reference,
        unit_id=unit.id,
        tenancy_id=tenancy.id if tenancy else None,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
        status=MaintenanceStatus.SUBMITTED,
        photo_file_ids=[str(fid) for fid in payload.photo_file_ids],
        reported_by_user_id=None if tenant else context.user.id,
        reported_by_tenant_id=tenant.id if tenant else None,
    )
    db.add(record)
    await db.flush()

    if payload.photo_file_ids:
        await file_service.attach(db, context, payload.photo_file_ids, "maintenance", record.id)

    reporter = tenant.full_name if tenant else context.user.full_name
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="maintenance.submitted",
        entity_type="maintenance_request",
        entity_id=record.id,
        actor=None if tenant else context.user,
        summary=f"{reporter} reported: {record.title} ({record.priority.value})",
        request=request,
    )

    await _alert_owners_of_maintenance(db, context, record, unit, reporter)
    await db.commit()
    await db.refresh(record)
    return record


async def _alert_owners_of_maintenance(
    db: AsyncSession, context: OrgContext, record: MaintenanceRequest, unit: Unit, reporter: str
) -> None:
    property_record = await db.get(Property, unit.property_id)
    urgent = record.priority == MaintenancePriority.EMERGENCY

    owners = await db.scalars(
        select(User).where(
            User.organization_id == context.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.MAINTENANCE_SUBMITTED,
            title=("URGENT: emergency maintenance" if urgent else "New maintenance request"),
            body=(
                f"{'*** EMERGENCY *** ' if urgent else ''}{reporter} reported "
                f"'{record.title}' ({record.category.value}) for unit {unit.unit_number} at "
                f"{property_record.name if property_record else 'your property'}. "
                f"Reference {record.reference_code}."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.PUSH, NotificationChannel.IN_APP],
            link_path=f"/maintenance/{record.id}",
            entity_type="maintenance_request",
            entity_id=record.id,
        )


async def update_maintenance_request(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    payload: MaintenanceUpdate,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    """Edit the request's own detail. State changes live in `maintenance_service`,
    which is why nothing here touches `status`."""
    record = assert_in_org(await db.get(MaintenanceRequest, request_id), context, label="maintenance request")
    fields = payload.model_dump(exclude_unset=True)

    for field, value in fields.items():
        setattr(record, field, value)

    # Editing a due date forward clears a stale overdue flag; the nightly sweep
    # will re-raise it if the new date passes too.
    if record.is_overdue and record.expected_completion_date:
        if record.expected_completion_date >= date.today():
            record.is_overdue = False
            record.overdue_flagged_at = None

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="maintenance.updated",
        entity_type="maintenance_request",
        entity_id=record.id,
        actor=context.user,
        summary=f"{record.reference_code}: updated {', '.join(sorted(fields)) or 'nothing'}",
        request=http_request,
    )

    await db.commit()
    await db.refresh(record)
    return record


async def list_maintenance_requests(
    db: AsyncSession,
    context: OrgContext,
    *,
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    request_status: MaintenanceStatus | None = None,
    priority: MaintenancePriority | None = None,
    tenant_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    open_only: bool = False,
    overdue_only: bool = False,
    limit: int = 100,
) -> list[MaintenanceRequest]:
    query = select(MaintenanceRequest).where(MaintenanceRequest.organization_id == context.organization_id)

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(
            MaintenanceRequest.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed)))
        )
    if unit_id:
        query = query.where(MaintenanceRequest.unit_id == unit_id)
    if property_id:
        query = query.where(
            MaintenanceRequest.unit_id.in_(select(Unit.id).where(Unit.property_id == property_id))
        )
    if request_status:
        query = query.where(MaintenanceRequest.status == request_status)
    if open_only:
        query = query.where(MaintenanceRequest.status.in_(OPEN_STATUSES))
    if overdue_only:
        query = query.where(MaintenanceRequest.is_overdue.is_(True))
    if priority:
        query = query.where(MaintenanceRequest.priority == priority)
    if tenant_id:
        query = query.where(MaintenanceRequest.reported_by_tenant_id == tenant_id)
    if vendor_id:
        query = query.where(MaintenanceRequest.vendor_id == vendor_id)

    # Overdue and emergency work floats to the top — the list is a work queue,
    # not a filing cabinet.
    rows = await db.scalars(
        query.order_by(
            MaintenanceRequest.is_overdue.desc(),
            MaintenanceRequest.created_at.desc(),
        ).limit(limit)
    )
    return list(rows)


# ------------------------------------------------------------------ vacate notice


async def submit_vacate_notice(
    db: AsyncSession,
    context: OrgContext,
    payload: VacateNoticeCreate,
    *,
    tenant: Tenant | None = None,
    request: Request | None = None,
) -> VacateNotice:
    """Tenant's digital notice to vacate (US-033)."""
    tenancy = assert_in_org(await db.get(Tenancy, payload.tenancy_id), context, label="tenancy")
    if tenancy.status == TenancyStatus.VACATED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This tenancy has already ended")
    if tenant is not None and tenancy.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This is not your tenancy")

    existing = await db.scalar(
        select(VacateNotice).where(
            VacateNotice.tenancy_id == tenancy.id,
            VacateNotice.status.notin_([VacateNoticeStatus.WITHDRAWN]),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A notice to vacate has already been submitted for this tenancy",
        )

    days_given = (payload.move_out_date - date.today()).days
    notice = VacateNotice(
        organization_id=context.organization_id,
        tenancy_id=tenancy.id,
        move_out_date=payload.move_out_date,
        reason=payload.reason,
        notice_days_given=days_given,
        meets_notice_period=days_given >= tenancy.notice_period_days,
        status=VacateNoticeStatus.SUBMITTED,
        submitted_by_tenant_id=tenancy.tenant_id,
    )
    db.add(notice)
    await db.flush()

    tenancy.notice_given_at = datetime.now(UTC)
    tenancy.move_out_date = payload.move_out_date
    tenancy.status = TenancyStatus.NOTICE_GIVEN

    unit = await db.get(Unit, tenancy.unit_id)
    if unit:
        unit.status = UnitStatus.VACATING
        unit.expected_vacancy_date = payload.move_out_date

    await _render_notice_pdf(db, notice, tenancy)
    await _alert_team_of_notice(db, context, notice, tenancy)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="tenancy.notice_given",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=None if tenant else context.user,
        summary=(
            f"Notice to vacate on {payload.move_out_date.isoformat()} "
            f"({days_given} days given, {tenancy.notice_period_days} required)"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(notice)
    return notice


async def _render_notice_pdf(db: AsyncSession, notice: VacateNotice, tenancy: Tenancy) -> None:
    organization = await db.get(Organization, notice.organization_id)
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    if not (organization and tenant and unit and property_record):
        return

    tenant.national_id = await tenant_pii.decrypt_national_id(db, tenant)

    pdf_bytes = pdf_service.render_pdf(
        "vacate_notice.html",
        {
            "organization": organization,
            "logo_url": None,
            "notice": notice,
            "tenancy": tenancy,
            "tenant": tenant,
            "unit": unit,
            "property": property_record,
            "submitted_at": datetime.now(UTC).strftime("%d %b %Y, %H:%M"),
            "generated_at": date.today(),
        },
    )
    record = await file_service.register_generated(
        db,
        notice.organization_id,
        data=pdf_bytes,
        filename=f"Notice-to-Vacate-{tenancy.reference_code}.pdf",
        category=FileCategory.NOTICE,
        entity_type="tenant",
        entity_id=tenant.id,
    )
    notice.document_id = record.id


async def _alert_team_of_notice(
    db: AsyncSession, context: OrgContext, notice: VacateNotice, tenancy: Tenancy
) -> None:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None

    staff = await db.scalars(
        select(User).where(
            User.organization_id == context.organization_id,
            User.role.in_(
                [UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER, UserRole.CARETAKER]
            ),
            User.is_active.is_(True),
        )
    )
    short = "" if notice.meets_notice_period else " (SHORT NOTICE)"
    for member in staff:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(member),
            notification_type=NotificationType.VACATE_NOTICE,
            title=f"Notice to vacate{short}",
            body=(
                f"{tenant.full_name if tenant else 'A tenant'} has given notice to vacate unit "
                f"{unit.unit_number if unit else '?'} at "
                f"{property_record.name if property_record else 'your property'} on "
                f"{notice.move_out_date.strftime('%d %b %Y')} "
                f"({notice.notice_days_given} days' notice). Schedule the move-out inspection."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.PUSH, NotificationChannel.IN_APP],
            link_path=f"/tenancies/{tenancy.id}",
            entity_type="vacate_notice",
            entity_id=notice.id,
        )


async def acknowledge_vacate_notice(
    db: AsyncSession, context: OrgContext, notice_id: uuid.UUID, request: Request | None = None
) -> VacateNotice:
    notice = assert_in_org(await db.get(VacateNotice, notice_id), context, label="notice")
    notice.status = VacateNoticeStatus.ACKNOWLEDGED
    notice.acknowledged_at = datetime.now(UTC)
    notice.acknowledged_by_id = context.user.id

    tenancy = await db.get(Tenancy, notice.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    if tenant:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_tenant(tenant),
            notification_type=NotificationType.VACATE_NOTICE,
            title="Notice acknowledged",
            body=(
                f"Your notice to vacate on {notice.move_out_date.strftime('%d %b %Y')} has been "
                "acknowledged. A move-out inspection will be scheduled before that date."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="vacate_notice.acknowledged",
        entity_type="vacate_notice",
        entity_id=notice.id,
        actor=context.user,
        summary="Acknowledged notice to vacate",
        request=request,
    )
    await db.commit()
    await db.refresh(notice)
    return notice


async def list_vacate_notices(
    db: AsyncSession, context: OrgContext, *, tenancy_id: uuid.UUID | None = None
) -> list[VacateNotice]:
    query = select(VacateNotice).where(VacateNotice.organization_id == context.organization_id)
    if tenancy_id:
        query = query.where(VacateNotice.tenancy_id == tenancy_id)
    rows = await db.scalars(query.order_by(VacateNotice.created_at.desc()))
    return list(rows)


# ------------------------------------------------------------------- visitor log


async def log_visitor(
    db: AsyncSession, context: OrgContext, payload: VisitorLogCreate, request: Request | None = None
) -> VisitorLog:
    unit = await _unit_in_scope(db, context, payload.unit_id)
    checked_in_at = payload.checked_in_at or datetime.now(UTC)

    if payload.checked_out_at is not None and payload.checked_out_at < checked_in_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Check-out time cannot be before check-in time"
        )

    entry = VisitorLog(
        organization_id=context.organization_id,
        property_id=unit.property_id,
        unit_id=unit.id,
        visitor_name=payload.visitor_name,
        visitor_phone=payload.visitor_phone,
        purpose=payload.purpose,
        checked_in_at=checked_in_at,
        checked_out_at=payload.checked_out_at,
        recorded_by_id=context.user.id,
        gps_latitude=payload.gps_latitude,
        gps_longitude=payload.gps_longitude,
    )
    db.add(entry)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="visitor_log.recorded",
        entity_type="visitor_log",
        entity_id=entry.id,
        actor=context.user,
        summary=f"Visitor {entry.visitor_name} logged for unit {unit.unit_number}",
        request=request,
    )
    await db.commit()
    await db.refresh(entry)
    return entry


async def check_out_visitor(
    db: AsyncSession, context: OrgContext, visitor_log_id: uuid.UUID, request: Request | None = None
) -> VisitorLog:
    entry = assert_in_org(await db.get(VisitorLog, visitor_log_id), context, label="visitor log entry")
    if entry.checked_out_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This visitor is already checked out"
        )

    entry.checked_out_at = datetime.now(UTC)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="visitor_log.checked_out",
        entity_type="visitor_log",
        entity_id=entry.id,
        actor=context.user,
        summary=f"Visitor {entry.visitor_name} checked out",
        request=request,
    )
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_visitor_logs(
    db: AsyncSession,
    context: OrgContext,
    *,
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    since: date | None = None,
    open_only: bool = False,
    limit: int = 100,
) -> list[VisitorLog]:
    query = select(VisitorLog).where(VisitorLog.organization_id == context.organization_id)

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(VisitorLog.property_id.in_(allowed))
    if unit_id:
        query = query.where(VisitorLog.unit_id == unit_id)
    if property_id:
        query = query.where(VisitorLog.property_id == property_id)
    if since:
        query = query.where(func.date(VisitorLog.checked_in_at) >= since)
    if open_only:
        query = query.where(VisitorLog.checked_out_at.is_(None))

    rows = await db.scalars(query.order_by(VisitorLog.checked_in_at.desc()).limit(limit))
    return list(rows)


# ---------------------------------------------------------------------- activity


async def caretaker_activity_counts(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, since: datetime
) -> dict[str, int]:
    from app.models.audit import AuditLog

    rows = (
        await db.execute(
            select(AuditLog.action, func.count(AuditLog.id))
            .where(
                AuditLog.organization_id == organization_id,
                AuditLog.user_id == user_id,
                AuditLog.created_at >= since,
            )
            .group_by(AuditLog.action)
        )
    ).all()
    counts = {action: int(count) for action, count in rows}
    return {
        "payments_recorded": counts.get("payment.recorded", 0),
        "meter_readings": counts.get("meter_reading.recorded", 0),
        "maintenance_requests": counts.get("maintenance.submitted", 0),
        "unit_status_changes": counts.get("unit.status_changed", 0),
        "total_actions": sum(counts.values()),
    }


async def caretaker_tasks(db: AsyncSession, context: OrgContext) -> dict:
    """The caretaker's home screen payload (US-024)."""
    from app.models.audit import AuditLog
    from app.services import arrears_service

    due = await readings_due(db, context, limit=10)
    open_requests = await list_maintenance_requests(db, context, open_only=True, limit=10)

    vacant_query = select(func.count(Unit.id)).where(
        Unit.organization_id == context.organization_id,
        Unit.is_archived.is_(False),
        Unit.status == UnitStatus.VACANT,
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        vacant_query = vacant_query.where(Unit.property_id.in_(allowed))
    vacant = int(await db.scalar(vacant_query) or 0)

    arrears = await arrears_service.build_report(db, context)

    recent = list(
        await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.organization_id == context.organization_id,
                AuditLog.user_id == context.user.id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(15)
        )
    )

    return {
        "readings_due": due,
        "open_maintenance": open_requests,
        "units_vacant": vacant,
        "tenants_in_arrears": arrears.tenants_in_arrears,
        "recent_activity": recent,
    }


__all__ = [
    "acknowledge_vacate_notice",
    "caretaker_activity_counts",
    "caretaker_tasks",
    "create_maintenance_request",
    "list_maintenance_requests",
    "list_meter_readings",
    "list_vacate_notices",
    "meter_context",
    "readings_due",
    "record_meter_reading",
    "submit_vacate_notice",
    "update_maintenance_request",
]
