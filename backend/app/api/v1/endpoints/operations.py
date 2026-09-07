import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.audit import AuditLog
from app.models.file import StoredFile
from app.models.operations import (
    MaintenancePriority,
    MaintenanceRequest,
    MaintenanceStatus,
    MeterReading,
    MeterType,
    VacateNotice,
    VisitorLog,
)
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.maintenance import (
    MaintenanceApprove,
    MaintenanceAssign,
    MaintenanceCancel,
    MaintenanceComplete,
    MaintenanceInfoRequest,
    MaintenanceReject,
    MaintenanceTimelineEntry,
    VendorSummary,
)
from app.schemas.operations import (
    ActivityEntry,
    CaretakerTaskList,
    MaintenanceCreate,
    MaintenanceDetail,
    MaintenanceRead,
    MaintenanceUpdate,
    MeterContext,
    MeterPhotoReadRequest,
    MeterPhotoReadResult,
    MeterReadingCreate,
    MeterReadingDetail,
    MeterReadingRead,
    VacateNoticeCreate,
    VacateNoticeDetail,
    VacateNoticeRead,
    VisitorLogCreate,
    VisitorLogDetail,
    VisitorLogRead,
)
from app.services import (
    caretaker_performance_service,
    file_service,
    maintenance_service,
    ocr_service,
    operations_service,
)

meters_router = APIRouter()
maintenance_router = APIRouter()
notices_router = APIRouter()
caretaker_router = APIRouter()
visitor_logs_router = APIRouter()


async def _reading_detail(db: AsyncSession, reading: MeterReading) -> MeterReadingDetail:
    unit = await db.get(Unit, reading.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    recorded_by = await db.get(User, reading.recorded_by_id) if reading.recorded_by_id else None

    photo_url = None
    if reading.photo_file_id:
        record = await db.get(StoredFile, reading.photo_file_id)
        if record:
            photo_url = file_service.to_url(record)

    return MeterReadingDetail(
        **MeterReadingRead.model_validate(reading).model_dump(),
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        photo_url=photo_url,
        recorded_by_name=recorded_by.full_name if recorded_by else None,
    )


async def _maintenance_detail(
    db: AsyncSession, record: MaintenanceRequest, *, with_timeline: bool = False
) -> MaintenanceDetail:
    unit = await db.get(Unit, record.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None

    reporter = None
    if record.reported_by_user_id:
        user = await db.get(User, record.reported_by_user_id)
        reporter = user.full_name if user else None
    elif record.reported_by_tenant_id:
        tenant = await db.get(Tenant, record.reported_by_tenant_id)
        reporter = tenant.full_name if tenant else None

    approver = None
    if record.approved_by_id:
        user = await db.get(User, record.approved_by_id)
        approver = user.full_name if user else None

    urls = []
    for file_id in record.photo_file_ids:
        stored = await db.get(StoredFile, uuid.UUID(str(file_id)))
        if stored:
            urls.append(file_service.to_url(stored))

    vendor = await db.get(Vendor, record.vendor_id) if record.vendor_id else None
    ended = record.completed_at or record.closed_at
    days_open = ((ended or datetime.now(UTC)) - record.created_at).days

    return MaintenanceDetail(
        **MaintenanceRead.model_validate(record).model_dump(),
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        property_id=property_record.id if property_record else None,
        reported_by_name=reporter,
        approved_by_name=approver,
        photo_urls=urls,
        vendor=(
            VendorSummary(
                id=vendor.id,
                name=vendor.name,
                phone_number=vendor.phone_number,
                average_rating=vendor.average_rating,
                jobs_completed=vendor.jobs_completed,
            )
            if vendor
            else None
        ),
        cost_variance=record.cost_variance,
        days_open=max(days_open, 0),
        timeline=await _maintenance_timeline(db, record) if with_timeline else [],
    )


async def _maintenance_timeline(
    db: AsyncSession, record: MaintenanceRequest
) -> list[MaintenanceTimelineEntry]:
    """The job's history, read straight off the audit log rather than kept in a
    second table — the audit trail is already the authoritative record."""
    rows = await db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == record.organization_id,
            AuditLog.entity_type == "maintenance_request",
            AuditLog.entity_id == record.id,
        )
        .order_by(AuditLog.created_at.asc())
    )
    return [
        MaintenanceTimelineEntry(
            action=row.action,
            summary=row.summary or row.action,
            actor_name=row.actor_name,
            occurred_at=row.created_at,
        )
        for row in rows
    ]


async def _notice_detail(db: AsyncSession, notice: VacateNotice) -> VacateNoticeDetail:
    tenancy = await db.get(Tenancy, notice.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None

    document_url = None
    if notice.document_id:
        record = await db.get(StoredFile, notice.document_id)
        if record:
            document_url = file_service.to_url(record)

    return VacateNoticeDetail(
        **VacateNoticeRead.model_validate(notice).model_dump(),
        tenant_name=tenant.full_name if tenant else None,
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        required_notice_days=tenancy.notice_period_days if tenancy else 30,
        document_url=document_url,
    )


# ------------------------------------------------------------------ meter readings


@meters_router.get("/context", response_model=MeterContext)
async def get_meter_context(
    unit_id: uuid.UUID,
    meter_type: MeterType,
    context: OrgContext = Depends(require(Permission.METER_READING_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> MeterContext:
    """Previous reading and configured rate, so the form opens pre-filled."""
    return await operations_service.meter_context(db, context, unit_id, meter_type)


@meters_router.get("/due", response_model=list[MeterContext])
async def readings_due(
    limit: int = Query(default=25, ge=1, le=100),
    context: OrgContext = Depends(require(Permission.METER_READING_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[MeterContext]:
    return await operations_service.readings_due(db, context, limit)


@meters_router.post("/read-photo", response_model=MeterPhotoReadResult)
async def read_meter_photo(
    payload: MeterPhotoReadRequest,
    context: OrgContext = Depends(require(Permission.METER_READING_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> MeterPhotoReadResult:
    """Suggest a reading from the meter photo just uploaded (Module 5).

    Read-permission gated rather than `require_write`: nothing is written, and
    an expired trial should still be able to look at its own photograph.
    """
    result = await ocr_service.read_meter_photo(
        db, context, photo_file_id=payload.photo_file_id, meter_type=payload.meter_type
    )
    return MeterPhotoReadResult(**result)


@meters_router.post("", response_model=MeterReadingDetail, status_code=status.HTTP_201_CREATED)
async def record_reading(
    payload: MeterReadingCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.METER_READING_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> MeterReadingDetail:
    reading = await operations_service.record_meter_reading(db, context, payload, request)
    return await _reading_detail(db, reading)


@meters_router.get("", response_model=list[MeterReadingDetail])
async def list_readings(
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    meter_type: MeterType | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.METER_READING_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[MeterReadingDetail]:
    rows = await operations_service.list_meter_readings(
        db, context, unit_id=unit_id, property_id=property_id, meter_type=meter_type, limit=limit
    )
    return [await _reading_detail(db, reading) for reading in rows]


# -------------------------------------------------------------------- maintenance


@maintenance_router.post("", response_model=MaintenanceDetail, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: MaintenanceCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await operations_service.create_maintenance_request(db, context, payload, request)
    return await _maintenance_detail(db, record)


@maintenance_router.get("", response_model=list[MaintenanceDetail])
async def list_requests(
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    request_status: MaintenanceStatus | None = None,
    priority: MaintenancePriority | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.MAINTENANCE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[MaintenanceDetail]:
    rows = await operations_service.list_maintenance_requests(
        db,
        context,
        unit_id=unit_id,
        property_id=property_id,
        request_status=request_status,
        priority=priority,
        limit=limit,
    )
    return [await _maintenance_detail(db, record) for record in rows]


@maintenance_router.get("/analytics")
async def maintenance_analytics(
    months: int = Query(default=12, ge=1, le=36),
    context: OrgContext = Depends(require(Permission.MAINTENANCE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cost analytics for the maintenance dashboard (US-062)."""
    return await maintenance_service.maintenance_overview(db, context, months=months)


@maintenance_router.get("/unit/{unit_id}/history", response_model=list[MaintenanceDetail])
async def unit_history(
    unit_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.MAINTENANCE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[MaintenanceDetail]:
    rows = await maintenance_service.unit_history(db, context, unit_id, limit=limit)
    return [await _maintenance_detail(db, record) for record in rows]


@maintenance_router.get("/{request_id}", response_model=MaintenanceDetail)
async def get_request(
    request_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.MAINTENANCE_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = assert_in_org(await db.get(MaintenanceRequest, request_id), context, label="maintenance request")
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.patch("/{request_id}", response_model=MaintenanceDetail)
async def update_request(
    request_id: uuid.UUID,
    payload: MaintenanceUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await operations_service.update_maintenance_request(db, context, request_id, payload, request)
    return await _maintenance_detail(db, record, with_timeline=True)


# --- lifecycle actions (US-061). Each state change is its own endpoint so the
# fields a move requires — a rejection reason, a final cost — cannot be skipped.


@maintenance_router.post("/{request_id}/review", response_model=MaintenanceDetail)
async def review_request(
    request_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.start_review(db, context, request_id, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/request-info", response_model=MaintenanceDetail)
async def request_more_info(
    request_id: uuid.UUID,
    payload: MaintenanceInfoRequest,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.request_more_info(db, context, request_id, payload, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/approve", response_model=MaintenanceDetail)
async def approve_request(
    request_id: uuid.UUID,
    payload: MaintenanceApprove,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.approve(db, context, request_id, payload, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/reject", response_model=MaintenanceDetail)
async def reject_request(
    request_id: uuid.UUID,
    payload: MaintenanceReject,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.reject(db, context, request_id, payload, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/assign", response_model=MaintenanceDetail)
async def assign_request(
    request_id: uuid.UUID,
    payload: MaintenanceAssign,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.assign_vendor(db, context, request_id, payload, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/start", response_model=MaintenanceDetail)
async def start_request(
    request_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.start_work(db, context, request_id, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/complete", response_model=MaintenanceDetail)
async def complete_request(
    request_id: uuid.UUID,
    payload: MaintenanceComplete,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.complete(db, context, request_id, payload, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/close", response_model=MaintenanceDetail)
async def close_request(
    request_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.close(db, context, request_id, request)
    return await _maintenance_detail(db, record, with_timeline=True)


@maintenance_router.post("/{request_id}/cancel", response_model=MaintenanceDetail)
async def cancel_request(
    request_id: uuid.UUID,
    payload: MaintenanceCancel,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.MAINTENANCE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceDetail:
    record = await maintenance_service.cancel(db, context, request_id, payload.reason, request)
    return await _maintenance_detail(db, record, with_timeline=True)


# ------------------------------------------------------------------ vacate notices


@notices_router.post("", response_model=VacateNoticeDetail, status_code=status.HTTP_201_CREATED)
async def submit_notice(
    payload: VacateNoticeCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> VacateNoticeDetail:
    notice = await operations_service.submit_vacate_notice(db, context, payload, request=request)
    return await _notice_detail(db, notice)


@notices_router.get("", response_model=list[VacateNoticeDetail])
async def list_notices(
    tenancy_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[VacateNoticeDetail]:
    rows = await operations_service.list_vacate_notices(db, context, tenancy_id=tenancy_id)
    return [await _notice_detail(db, notice) for notice in rows]


@notices_router.post("/{notice_id}/acknowledge", response_model=VacateNoticeDetail)
async def acknowledge_notice(
    notice_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> VacateNoticeDetail:
    notice = await operations_service.acknowledge_vacate_notice(db, context, notice_id, request)
    return await _notice_detail(db, notice)


# --------------------------------------------------------------------- visitor log


async def _visitor_log_detail(db: AsyncSession, entry: VisitorLog) -> VisitorLogDetail:
    unit = await db.get(Unit, entry.unit_id)
    property_record = await db.get(Property, entry.property_id)
    recorded_by = await db.get(User, entry.recorded_by_id) if entry.recorded_by_id else None

    return VisitorLogDetail(
        **VisitorLogRead.model_validate(entry).model_dump(),
        unit_number=unit.unit_number if unit else None,
        property_name=property_record.name if property_record else None,
        recorded_by_name=recorded_by.full_name if recorded_by else None,
    )


@visitor_logs_router.post("", response_model=VisitorLogDetail, status_code=status.HTTP_201_CREATED)
async def log_visitor(
    payload: VisitorLogCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.VISITOR_LOG_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> VisitorLogDetail:
    entry = await operations_service.log_visitor(db, context, payload, request)
    return await _visitor_log_detail(db, entry)


@visitor_logs_router.get("", response_model=list[VisitorLogDetail])
async def list_visitor_logs(
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    since: date | None = None,
    open_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.VISITOR_LOG_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[VisitorLogDetail]:
    rows = await operations_service.list_visitor_logs(
        db,
        context,
        unit_id=unit_id,
        property_id=property_id,
        since=since,
        open_only=open_only,
        limit=limit,
    )
    return [await _visitor_log_detail(db, entry) for entry in rows]


@visitor_logs_router.post("/{visitor_log_id}/check-out", response_model=VisitorLogDetail)
async def check_out_visitor(
    visitor_log_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.VISITOR_LOG_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> VisitorLogDetail:
    entry = await operations_service.check_out_visitor(db, context, visitor_log_id, request)
    return await _visitor_log_detail(db, entry)


# ------------------------------------------------------------------ caretaker home


@caretaker_router.get("/today", response_model=CaretakerTaskList)
async def caretaker_today(
    context: OrgContext = Depends(require(Permission.UNIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> CaretakerTaskList:
    """Today's tasks, open jobs and recent activity for the mobile home screen."""
    data = await operations_service.caretaker_tasks(db, context)
    return CaretakerTaskList(
        readings_due=data["readings_due"],
        open_maintenance=[await _maintenance_detail(db, r) for r in data["open_maintenance"]],
        units_vacant=data["units_vacant"],
        tenants_in_arrears=data["tenants_in_arrears"],
        recent_activity=[
            ActivityEntry(
                id=entry.id,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                summary=entry.summary,
                actor_name=entry.actor_name,
                user_id=entry.user_id,
                created_at=entry.created_at,
                gps_latitude=entry.gps_latitude,
                gps_longitude=entry.gps_longitude,
            )
            for entry in data["recent_activity"]
        ],
    )


# ------------------------------------------------- caretaker performance (US-058)


@caretaker_router.get("/performance")
async def caretaker_performance(
    window_days: int = Query(default=30, ge=7, le=365),
    context: OrgContext = Depends(require(Permission.USER_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Every caretaker scored over the window, whoever needs attention first."""
    return await caretaker_performance_service.list_caretakers(db, context, window_days=window_days)


@caretaker_router.get("/performance/{user_id}")
async def caretaker_performance_detail(
    user_id: uuid.UUID,
    window_days: int = Query(default=30, ge=7, le=365),
    context: OrgContext = Depends(require(Permission.USER_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """One caretaker's numbers, their six-month trend, and their properties."""
    return await caretaker_performance_service.caretaker_detail(db, context, user_id, window_days=window_days)


@caretaker_router.get("/performance/{user_id}/open-jobs")
async def caretaker_open_jobs(
    user_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.USER_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """The unacknowledged jobs pulling this caretaker's response score down."""
    return await caretaker_performance_service.open_maintenance_ages(db, context, user_id)
