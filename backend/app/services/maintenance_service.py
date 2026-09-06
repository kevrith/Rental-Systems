"""The maintenance job lifecycle (US-061) and its cost reporting (US-062).

Submission and listing still live in `operations_service` — a caretaker
reporting a leak is a field-operations act. Everything that happens *after* a
request exists is here, because from the review step onwards a maintenance
request is a spending decision: someone approves it, a vendor is engaged, money
is committed and then settled against the owner.

The state machine is declared once, in `app.models.operations.ALLOWED_TRANSITIONS`.
Every mutation below goes through `_transition`, so an invalid move is a 409 and
every valid one leaves an audit row behind.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import Numeric, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.agency import OwnerProfile
from app.models.developer import WebhookEvent
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import (
    ALLOWED_TRANSITIONS,
    BILLABLE_STATUSES,
    OPEN_STATUSES,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
)
from app.models.organization import OperatingMode
from app.models.property import Property, Unit
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.schemas.maintenance import (
    MaintenanceApprove,
    MaintenanceAssign,
    MaintenanceComplete,
    MaintenanceInfoRequest,
    MaintenanceReject,
)
from app.services import audit_service, notification_service, vendor_service, webhook_service

ZERO = Decimal("0.00")

# How long a job of each priority is expected to take when the approver does not
# name a date themselves. Emergencies are same-day by definition.
DEFAULT_TURNAROUND_DAYS = {"emergency": 1, "urgent": 3, "routine": 14}


# ------------------------------------------------------------------ transitions


def assert_transition(current: MaintenanceStatus, target: MaintenanceStatus) -> None:
    if target == current:
        return
    if target not in ALLOWED_TRANSITIONS.get(current, ()):
        allowed = ", ".join(s.value.replace("_", " ") for s in ALLOWED_TRANSITIONS.get(current, ()))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A request that is {current.value.replace('_', ' ')} cannot become "
                f"{target.value.replace('_', ' ')}."
                + (f" Allowed from here: {allowed}." if allowed else " This request is closed.")
            ),
        )


async def _load(db: AsyncSession, context: OrgContext, request_id: uuid.UUID) -> MaintenanceRequest:
    record = assert_in_org(await db.get(MaintenanceRequest, request_id), context, label="maintenance request")
    unit = await db.get(Unit, record.unit_id)
    allowed = await accessible_property_ids(db, context)
    if unit is not None and allowed is not None and unit.property_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )
    return record


async def _transition(
    db: AsyncSession,
    context: OrgContext,
    record: MaintenanceRequest,
    target: MaintenanceStatus,
    *,
    action: str,
    summary: str,
    request: Request | None = None,
) -> MaintenanceStatus:
    previous = record.status
    assert_transition(previous, target)
    record.status = target

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action=action,
        entity_type="maintenance_request",
        entity_id=record.id,
        actor=context.user,
        summary=f"{record.reference_code}: {summary}",
        request=request,
    )
    await webhook_service.dispatch(
        db,
        context.organization_id,
        WebhookEvent.MAINTENANCE_STATUS_CHANGED,
        {
            "id": str(record.id),
            "reference_code": record.reference_code,
            "previous_status": previous.value,
            "status": target.value,
            "unit_id": str(record.unit_id),
        },
    )
    return previous


async def _notify_reporter(
    db: AsyncSession,
    record: MaintenanceRequest,
    *,
    notification_type: NotificationType,
    title: str,
    body: str,
) -> None:
    """Keep whoever raised the job informed. Tenants get WhatsApp/SMS; a staff
    reporter gets the in-app feed they are already looking at."""
    if record.reported_by_tenant_id:
        tenant = await db.get(Tenant, record.reported_by_tenant_id)
        if tenant is None:
            return
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_tenant(tenant),
            notification_type=notification_type,
            title=title,
            body=body,
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
            entity_type="maintenance_request",
            entity_id=record.id,
            organization_id=record.organization_id,
        )
        return

    if record.reported_by_user_id:
        reporter = await db.get(User, record.reported_by_user_id)
        if reporter is None:
            return
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(reporter),
            notification_type=notification_type,
            title=title,
            body=body,
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
            link_path=f"/maintenance/{record.id}",
            entity_type="maintenance_request",
            entity_id=record.id,
        )


async def _job_context(db: AsyncSession, record: MaintenanceRequest) -> tuple[Unit | None, Property | None]:
    unit = await db.get(Unit, record.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    return unit, property_record


# ------------------------------------------------------------------- lifecycle


async def start_review(
    db: AsyncSession, context: OrgContext, request_id: uuid.UUID, http_request: Request | None = None
) -> MaintenanceRequest:
    record = await _load(db, context, request_id)
    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.UNDER_REVIEW,
        action="maintenance.review_started",
        summary=f"{context.user.full_name} started reviewing",
        request=http_request,
    )
    record.reviewed_at = datetime.now(UTC)
    # Legacy column, kept in step so pre-Sprint-13 reports still read correctly.
    record.acknowledged_at = record.acknowledged_at or record.reviewed_at

    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_UPDATE,
        title="Your request is being reviewed",
        body=(
            f"'{record.title}' ({record.reference_code}) is now with the manager for review. "
            "You will hear from us once it is approved."
        ),
    )
    await db.commit()
    await db.refresh(record)
    return record


async def request_more_info(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    payload: MaintenanceInfoRequest,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    """Bounce the request back to the reporter without changing its state — the
    job is still under review, it is just waiting on an answer."""
    record = await _load(db, context, request_id)
    if record.status not in (MaintenanceStatus.SUBMITTED, MaintenanceStatus.UNDER_REVIEW):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="More information can only be requested while a job is still under review",
        )

    if record.status == MaintenanceStatus.SUBMITTED:
        record.status = MaintenanceStatus.UNDER_REVIEW
        record.reviewed_at = datetime.now(UTC)

    record.info_requested = payload.question
    record.info_requested_at = datetime.now(UTC)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="maintenance.info_requested",
        entity_type="maintenance_request",
        entity_id=record.id,
        actor=context.user,
        summary=f"{record.reference_code}: asked the reporter for more detail",
        request=http_request,
    )
    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_UPDATE,
        title="More detail needed",
        body=(
            f"About '{record.title}' ({record.reference_code}): {payload.question} "
            "Please reply through the portal so we can get this moving."
        ),
    )
    await db.commit()
    await db.refresh(record)
    return record


async def approve(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    payload: MaintenanceApprove,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    """Approve the spend, and optionally engage a vendor in the same step —
    which is what an owner actually does when they already know who to call."""
    record = await _load(db, context, request_id)
    now = datetime.now(UTC)

    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.APPROVED,
        action="maintenance.approved",
        summary=(
            f"approved by {context.user.full_name}"
            + (
                f", estimate KES {payload.estimated_cost:,.2f}"
                if payload.estimated_cost is not None
                else " with no estimate"
            )
        ),
        request=http_request,
    )
    record.approved_at = now
    record.approved_by_id = context.user.id
    record.reviewed_at = record.reviewed_at or now
    record.info_requested = None
    if payload.estimated_cost is not None:
        record.estimated_cost = payload.estimated_cost
    record.expected_completion_date = payload.expected_completion_date or _default_due_date(record)

    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_APPROVED,
        title="Your request was approved",
        body=(
            f"'{record.title}' ({record.reference_code}) has been approved and is being scheduled. "
            f"Expected completion: {record.expected_completion_date:%d %b %Y}."
        ),
    )

    if payload.vendor_id is not None:
        await _assign(db, context, record, payload.vendor_id, http_request=http_request)

    await db.commit()
    await db.refresh(record)
    return record


def _default_due_date(record: MaintenanceRequest) -> date:
    from datetime import timedelta

    days = DEFAULT_TURNAROUND_DAYS.get(record.priority.value, 14)
    return date.today() + timedelta(days=days)


async def reject(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    payload: MaintenanceReject,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    record = await _load(db, context, request_id)
    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.REJECTED,
        action="maintenance.rejected",
        summary=f"rejected by {context.user.full_name} ({payload.reason.value})",
        request=http_request,
    )
    record.rejection_reason = payload.reason
    record.rejection_note = payload.note
    record.info_requested = None

    reason_text = payload.reason.value.replace("_", " ")
    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_REJECTED,
        title="Your request was not approved",
        body=(
            f"'{record.title}' ({record.reference_code}) was not approved. "
            f"Reason: {reason_text}." + (f" {payload.note}" if payload.note else "")
        ),
    )
    await db.commit()
    await db.refresh(record)
    return record


async def assign_vendor(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    payload: MaintenanceAssign,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    record = await _load(db, context, request_id)
    if payload.estimated_cost is not None:
        record.estimated_cost = payload.estimated_cost
    if payload.expected_completion_date is not None:
        record.expected_completion_date = payload.expected_completion_date

    await _assign(db, context, record, payload.vendor_id, http_request=http_request)
    await db.commit()
    await db.refresh(record)
    return record


async def _assign(
    db: AsyncSession,
    context: OrgContext,
    record: MaintenanceRequest,
    vendor_id: uuid.UUID,
    *,
    http_request: Request | None = None,
) -> None:
    """Engage a vendor and WhatsApp them the job. Shared by `approve` (one-step)
    and `assign_vendor` (assigning after the fact or reassigning)."""
    vendor = assert_in_org(await db.get(Vendor, vendor_id), context, label="vendor")
    if not vendor.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{vendor.name} is not an active vendor",
        )

    previous_vendor_id = record.vendor_id
    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.ASSIGNED,
        action="maintenance.assigned",
        summary=(
            f"{'reassigned' if previous_vendor_id else 'assigned'} to {vendor.name}"
            f" by {context.user.full_name}"
        ),
        request=http_request,
    )
    record.vendor_id = vendor.id
    record.assigned_at = datetime.now(UTC)
    record.assigned_by_id = context.user.id
    record.expected_completion_date = record.expected_completion_date or _default_due_date(record)

    unit, property_record = await _job_context(db, record)
    estimate = (
        f" Approved estimate: KES {record.estimated_cost:,.0f}." if record.estimated_cost is not None else ""
    )
    # The reporter's own words, punctuated so they do not run into the estimate.
    description = record.description.strip()
    if description and description[-1] not in ".!?":
        description += "."
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=vendor.phone_number, organization_id=record.organization_id
        ),
        notification_type=NotificationType.VENDOR_ASSIGNED,
        title="New job assigned",
        body=(
            f"Job {record.reference_code}: {record.title}. "
            f"{property_record.name if property_record else 'Property'}"
            f"{f', unit {unit.unit_number}' if unit else ''}"
            f"{f' — {property_record.address}' if property_record else ''}. "
            f"Priority: {record.priority.value}. {description}"
            f"{estimate} Please complete by "
            f"{record.expected_completion_date:%d %b %Y} and confirm with the office when done."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="maintenance_request",
        entity_id=record.id,
        organization_id=record.organization_id,
    )

    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_UPDATE,
        title="A contractor is on the way",
        body=(
            f"'{record.title}' ({record.reference_code}) has been assigned to {vendor.name}"
            f" ({vendor.phone_number}), expected by "
            f"{record.expected_completion_date:%d %b %Y}."
        ),
    )


async def start_work(
    db: AsyncSession, context: OrgContext, request_id: uuid.UUID, http_request: Request | None = None
) -> MaintenanceRequest:
    record = await _load(db, context, request_id)
    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.IN_PROGRESS,
        action="maintenance.started",
        summary=f"work started, logged by {context.user.full_name}",
        request=http_request,
    )
    record.started_at = datetime.now(UTC)

    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_UPDATE,
        title="Work has started",
        body=f"Work on '{record.title}' ({record.reference_code}) has started.",
    )
    await db.commit()
    await db.refresh(record)
    return record


async def complete(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    payload: MaintenanceComplete,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    """Mark the job done: final cost, resolution notes and the vendor's score.

    The rating is folded into the vendor's counters in this same transaction, so
    the registry's "best plumber" ordering can never drift from the job history.
    """
    record = await _load(db, context, request_id)
    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.COMPLETED,
        action="maintenance.completed",
        summary=(
            f"completed by {context.user.full_name}, actual cost KES {payload.actual_cost:,.2f}"
            + (f", vendor rated {payload.vendor_rating}/5" if payload.vendor_rating else "")
        ),
        request=http_request,
    )
    now = datetime.now(UTC)
    record.completed_at = now
    record.completed_by_id = context.user.id
    record.cost = payload.actual_cost
    record.is_overdue = False
    if payload.resolution_notes:
        record.resolution_notes = payload.resolution_notes
    if payload.vendor_rating is not None:
        record.vendor_rating = payload.vendor_rating
        record.vendor_review = payload.vendor_review

    if record.vendor_id:
        vendor = await db.get(Vendor, record.vendor_id)
        if vendor is not None:
            vendor_service.record_job_result(vendor, cost=payload.actual_cost, rating=payload.vendor_rating)

    variance = record.cost_variance
    if variance is not None and variance > ZERO:
        # Overspend against an approved estimate is the thing an owner most wants
        # flagged, so it gets its own audit line rather than hiding in the diff.
        audit_service.record(
            db,
            organization_id=context.organization_id,
            action="maintenance.cost_overrun",
            entity_type="maintenance_request",
            entity_id=record.id,
            actor=context.user,
            summary=(
                f"{record.reference_code}: actual KES {record.cost:,.2f} exceeded the "
                f"estimate of KES {record.estimated_cost:,.2f} by KES {variance:,.2f}"
            ),
            request=http_request,
        )

    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_UPDATE,
        title="Your request is complete",
        body=(
            f"'{record.title}' ({record.reference_code}) has been completed."
            + (f" {record.resolution_notes}" if record.resolution_notes else "")
            + " If anything is still not right, reply and we will reopen it."
        ),
    )
    await db.commit()
    await db.refresh(record)
    return record


async def close(
    db: AsyncSession, context: OrgContext, request_id: uuid.UUID, http_request: Request | None = None
) -> MaintenanceRequest:
    """Final sign-off. In agency mode this is the point the cost becomes the
    owner's — the statement builder picks it up from the completed job, and the
    flag here stops a second close from double-counting it."""
    record = await _load(db, context, request_id)
    if record.cost is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Record the actual cost before closing this job",
        )

    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.CLOSED,
        action="maintenance.closed",
        summary=f"closed by {context.user.full_name} at KES {record.cost:,.2f}",
        request=http_request,
    )
    record.closed_at = datetime.now(UTC)

    if context.organization.operating_mode == OperatingMode.AGENCY and not record.owner_expense_allocated:
        _, property_record = await _job_context(db, record)
        owner = (
            await db.get(OwnerProfile, property_record.owner_profile_id)
            if property_record and property_record.owner_profile_id
            else None
        )
        if owner is not None:
            record.owner_expense_allocated = True
            audit_service.record(
                db,
                organization_id=context.organization_id,
                action="maintenance.expense_allocated",
                entity_type="maintenance_request",
                entity_id=record.id,
                actor=context.user,
                summary=(
                    f"{record.reference_code}: KES {record.cost:,.2f} allocated to "
                    f"{owner.full_name} and deducted on their next statement"
                ),
                request=http_request,
            )

    await db.commit()
    await db.refresh(record)
    return record


async def cancel(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    reason: str | None = None,
    http_request: Request | None = None,
) -> MaintenanceRequest:
    record = await _load(db, context, request_id)
    await _transition(
        db,
        context,
        record,
        MaintenanceStatus.CANCELLED,
        action="maintenance.cancelled",
        summary=f"cancelled by {context.user.full_name}" + (f": {reason}" if reason else ""),
        request=http_request,
    )
    record.is_overdue = False
    if reason:
        record.resolution_notes = reason

    await _notify_reporter(
        db,
        record,
        notification_type=NotificationType.MAINTENANCE_UPDATE,
        title="Your request was cancelled",
        body=(
            f"'{record.title}' ({record.reference_code}) has been cancelled."
            + (f" {reason}" if reason else "")
        ),
    )
    await db.commit()
    await db.refresh(record)
    return record


async def rate_by_tenant(
    db: AsyncSession,
    record: MaintenanceRequest,
    *,
    rating: int,
    feedback: str | None,
) -> MaintenanceRequest:
    """The tenant's own score for a finished job (US-063).

    Kept separate from `vendor_rating`: the tenant is judging the outcome they
    experienced, the office is judging the contractor's work.
    """
    if record.status not in BILLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You can only rate a job once it has been completed",
        )
    if record.tenant_rating is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already rated this job")

    record.tenant_rating = rating
    record.tenant_feedback = feedback

    audit_service.record(
        db,
        organization_id=record.organization_id,
        action="maintenance.tenant_rated",
        entity_type="maintenance_request",
        entity_id=record.id,
        actor=None,
        summary=f"{record.reference_code}: tenant rated the job {rating}/5",
    )
    await db.commit()
    await db.refresh(record)
    return record


# ------------------------------------------------------------------- analytics


def _scoped(query: Select, organization_id: uuid.UUID, allowed: list[uuid.UUID] | None) -> Select:
    query = query.where(MaintenanceRequest.organization_id == organization_id)
    if allowed is not None:
        query = query.where(
            MaintenanceRequest.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed)))
        )
    return query


async def cost_by_property(db: AsyncSession, context: OrgContext, *, months: int = 12) -> list[dict]:
    """Spend per property over the window, against the budget if one is set (US-062)."""
    allowed = await accessible_property_ids(db, context)
    since = _months_ago(months)
    month_start = date.today().replace(day=1)

    rows = (
        await db.execute(
            _scoped(
                select(
                    Property.id,
                    Property.name,
                    Property.maintenance_budget_monthly,
                    func.coalesce(func.sum(MaintenanceRequest.cost), 0).label("total"),
                    func.count(MaintenanceRequest.id).label("jobs"),
                    func.coalesce(
                        func.sum(func.coalesce(MaintenanceRequest.cost, 0)).filter(
                            func.date(MaintenanceRequest.completed_at) >= month_start
                        ),
                        0,
                    ).label("this_month"),
                )
                .join(Unit, Unit.id == MaintenanceRequest.unit_id)
                .join(Property, Property.id == Unit.property_id),
                context.organization_id,
                allowed,
            )
            .where(
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.cost.is_not(None),
                func.date(MaintenanceRequest.completed_at) >= since,
            )
            .group_by(Property.id, Property.name, Property.maintenance_budget_monthly)
            .order_by(func.coalesce(func.sum(MaintenanceRequest.cost), 0).desc())
        )
    ).all()

    result: list[dict] = []
    for property_id, name, budget, total, jobs, this_month in rows:
        annual = Decimal(str(total or 0))
        monthly_budget = Decimal(str(budget)) if budget is not None else None
        result.append(
            {
                "property_id": str(property_id),
                "property_name": name,
                "jobs": int(jobs or 0),
                "total_cost": float(annual),
                "this_month_cost": float(this_month or 0),
                "average_monthly_cost": float((annual / months).quantize(Decimal("0.01"))),
                "monthly_budget": float(monthly_budget) if monthly_budget is not None else None,
                "budget_variance": (
                    float(monthly_budget - Decimal(str(this_month or 0)))
                    if monthly_budget is not None
                    else None
                ),
                "over_budget": (
                    bool(Decimal(str(this_month or 0)) > monthly_budget)
                    if monthly_budget is not None
                    else False
                ),
            }
        )
    return result


async def most_expensive_units(
    db: AsyncSession, context: OrgContext, *, months: int = 12, limit: int = 10
) -> list[dict]:
    """Units where maintenance is eating the rent (US-062).

    The ratio is annualised maintenance against annualised rent, so a unit that
    costs a month's rent to keep standing shows up as 8.3%, not as a raw number
    an owner has to divide in their head.
    """
    allowed = await accessible_property_ids(db, context)
    since = _months_ago(months)

    rows = (
        await db.execute(
            _scoped(
                select(
                    Unit.id,
                    Unit.unit_number,
                    Unit.monthly_rent,
                    Property.name,
                    func.coalesce(func.sum(MaintenanceRequest.cost), 0).label("total"),
                    func.count(MaintenanceRequest.id).label("jobs"),
                )
                .join(Unit, Unit.id == MaintenanceRequest.unit_id)
                .join(Property, Property.id == Unit.property_id),
                context.organization_id,
                allowed,
            )
            .where(
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.cost.is_not(None),
                func.date(MaintenanceRequest.completed_at) >= since,
            )
            .group_by(Unit.id, Unit.unit_number, Unit.monthly_rent, Property.name)
            .order_by(func.coalesce(func.sum(MaintenanceRequest.cost), 0).desc())
            .limit(limit)
        )
    ).all()

    result = []
    for unit_id, unit_number, rent, property_name, total, jobs in rows:
        cost = Decimal(str(total or 0))
        rent_over_window = Decimal(str(rent or 0)) * months
        ratio = float((cost / rent_over_window * 100).quantize(Decimal("0.01"))) if rent_over_window else None
        result.append(
            {
                "unit_id": str(unit_id),
                "unit_number": unit_number,
                "property_name": property_name,
                "monthly_rent": float(rent or 0),
                "total_cost": float(cost),
                "jobs": int(jobs or 0),
                "cost_to_rent_percent": ratio,
                # A unit swallowing more than a month's rent a year is the line
                # where an owner should be asking whether to refurbish it.
                "needs_attention": bool(ratio is not None and ratio > 100 / months),
            }
        )
    return result


async def issues_by_category(db: AsyncSession, context: OrgContext, *, months: int = 12) -> list[dict]:
    allowed = await accessible_property_ids(db, context)
    since = _months_ago(months)

    rows = (
        await db.execute(
            _scoped(
                select(
                    MaintenanceRequest.category,
                    func.count(MaintenanceRequest.id).label("jobs"),
                    func.coalesce(func.sum(MaintenanceRequest.cost), 0).label("total"),
                ),
                context.organization_id,
                allowed,
            )
            .where(func.date(MaintenanceRequest.created_at) >= since)
            .group_by(MaintenanceRequest.category)
            .order_by(func.count(MaintenanceRequest.id).desc())
        )
    ).all()

    return [
        {
            "category": category.value if isinstance(category, MaintenanceCategory) else str(category),
            "jobs": int(jobs or 0),
            "total_cost": float(total or 0),
            "average_cost": float(Decimal(str(total or 0)) / jobs) if jobs else 0.0,
        }
        for category, jobs, total in rows
    ]


async def vendor_leaderboard(db: AsyncSession, context: OrgContext, *, limit: int = 10) -> list[dict]:
    rows = await db.scalars(
        select(Vendor)
        .where(Vendor.organization_id == context.organization_id, Vendor.jobs_completed > 0)
        .order_by(Vendor.jobs_completed.desc())
        .limit(limit)
    )
    return [
        {
            "vendor_id": str(vendor.id),
            "name": vendor.name,
            "specialties": list(vendor.specialties),
            "jobs_completed": vendor.jobs_completed,
            "total_billed": float(vendor.total_billed),
            "average_cost": float(vendor.average_job_cost),
            "average_rating": vendor.average_rating,
            "is_active": vendor.is_active,
        }
        for vendor in rows
    ]


async def maintenance_overview(db: AsyncSession, context: OrgContext, *, months: int = 12) -> dict:
    """One payload for the maintenance analytics screen (US-062)."""
    allowed = await accessible_property_ids(db, context)
    today = date.today()
    month_start = today.replace(day=1)

    open_count = int(
        await db.scalar(
            _scoped(
                select(func.count(MaintenanceRequest.id)),
                context.organization_id,
                allowed,
            ).where(MaintenanceRequest.status.in_(OPEN_STATUSES))
        )
        or 0
    )
    overdue_count = int(
        await db.scalar(
            _scoped(select(func.count(MaintenanceRequest.id)), context.organization_id, allowed).where(
                MaintenanceRequest.is_overdue.is_(True)
            )
        )
        or 0
    )
    awaiting_approval = int(
        await db.scalar(
            _scoped(select(func.count(MaintenanceRequest.id)), context.organization_id, allowed).where(
                MaintenanceRequest.status.in_([MaintenanceStatus.SUBMITTED, MaintenanceStatus.UNDER_REVIEW])
            )
        )
        or 0
    )
    this_month_cost = float(
        await db.scalar(
            _scoped(
                select(func.coalesce(func.sum(MaintenanceRequest.cost), 0)),
                context.organization_id,
                allowed,
            ).where(
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                func.date(MaintenanceRequest.completed_at) >= month_start,
            )
        )
        or 0
    )
    window_cost = float(
        await db.scalar(
            _scoped(
                select(func.coalesce(func.sum(MaintenanceRequest.cost), 0)),
                context.organization_id,
                allowed,
            ).where(
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                func.date(MaintenanceRequest.completed_at) >= _months_ago(months),
            )
        )
        or 0
    )

    # Median would be more honest against outliers, but Postgres' percentile
    # aggregate does not compose with the filters here as cheaply as this does,
    # and the outliers are exactly what the "most expensive units" table surfaces.
    avg_days = await db.scalar(
        _scoped(
            select(
                func.avg(
                    cast(
                        func.extract(
                            "epoch",
                            MaintenanceRequest.completed_at - MaintenanceRequest.created_at,
                        )
                        / 86400,
                        Numeric(10, 2),
                    )
                )
            ),
            context.organization_id,
            allowed,
        ).where(
            MaintenanceRequest.status.in_(BILLABLE_STATUSES),
            MaintenanceRequest.completed_at.is_not(None),
            func.date(MaintenanceRequest.completed_at) >= _months_ago(months),
        )
    )

    trend = await monthly_cost_trend(db, context, months=min(months, 12))
    monthly_average = window_cost / months if months else 0.0
    budgets = await db.scalar(
        select(func.coalesce(func.sum(Property.maintenance_budget_monthly), 0)).where(
            Property.organization_id == context.organization_id,
            Property.is_archived.is_(False),
            *([Property.id.in_(allowed)] if allowed is not None else []),
        )
    )
    monthly_budget = float(budgets or 0)

    return {
        "window_months": months,
        "open_jobs": open_count,
        "awaiting_approval": awaiting_approval,
        "overdue_jobs": overdue_count,
        "this_month_cost": this_month_cost,
        "window_cost": window_cost,
        "average_monthly_cost": round(monthly_average, 2),
        "monthly_budget": monthly_budget or None,
        "budget_used_percent": (round(this_month_cost / monthly_budget * 100, 1) if monthly_budget else None),
        "average_completion_days": float(round(avg_days, 1)) if avg_days is not None else None,
        # A young account's first repair always beats its own 12-month average, so
        # the alert waits until there are at least three months of history to
        # compare against — otherwise it fires on every new organisation.
        "spike_alert": bool(len(trend) >= 3 and monthly_average and this_month_cost > monthly_average * 1.5),
        "by_property": await cost_by_property(db, context, months=months),
        "by_category": await issues_by_category(db, context, months=months),
        "expensive_units": await most_expensive_units(db, context, months=months),
        "top_vendors": await vendor_leaderboard(db, context),
        "monthly_trend": trend,
    }


async def monthly_cost_trend(db: AsyncSession, context: OrgContext, *, months: int = 12) -> list[dict]:
    allowed = await accessible_property_ids(db, context)
    bucket = func.date_trunc("month", MaintenanceRequest.completed_at)

    rows = (
        await db.execute(
            _scoped(
                select(
                    bucket.label("month"),
                    func.coalesce(func.sum(MaintenanceRequest.cost), 0).label("total"),
                    func.count(MaintenanceRequest.id).label("jobs"),
                ),
                context.organization_id,
                allowed,
            )
            .where(
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.completed_at.is_not(None),
                func.date(MaintenanceRequest.completed_at) >= _months_ago(months),
            )
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()

    return [
        {"month": month.strftime("%Y-%m"), "total_cost": float(total or 0), "jobs": int(jobs or 0)}
        for month, total, jobs in rows
    ]


async def unit_history(
    db: AsyncSession, context: OrgContext, unit_id: uuid.UUID, *, limit: int = 100
) -> list[MaintenanceRequest]:
    """Everything ever raised against one unit, newest first (US-061)."""
    rows = await db.scalars(
        select(MaintenanceRequest)
        .where(
            MaintenanceRequest.organization_id == context.organization_id,
            MaintenanceRequest.unit_id == unit_id,
        )
        .order_by(MaintenanceRequest.created_at.desc())
        .limit(limit)
    )
    return list(rows)


def _months_ago(months: int) -> date:
    today = date.today()
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    return date(year, month + 1, 1)


# --------------------------------------------------------------- overdue sweep


async def flag_overdue_jobs(db: AsyncSession, *, notify: bool = True) -> int:
    """Mark open jobs past their expected completion date and tell the manager.

    Runs across every organisation from the nightly beat, so it deliberately does
    not take an `OrgContext`; the notification is scoped per row instead.
    """
    today = date.today()
    rows = list(
        await db.scalars(
            select(MaintenanceRequest).where(
                MaintenanceRequest.status.in_(OPEN_STATUSES),
                MaintenanceRequest.expected_completion_date.is_not(None),
                MaintenanceRequest.expected_completion_date < today,
                MaintenanceRequest.is_overdue.is_(False),
            )
        )
    )

    for record in rows:
        record.is_overdue = True
        record.overdue_flagged_at = datetime.now(UTC)

        if not notify:
            continue

        unit, property_record = await _job_context(db, record)
        vendor = await db.get(Vendor, record.vendor_id) if record.vendor_id else None
        # The query filtered on a non-null date, so this is only for the checker.
        due = record.expected_completion_date or today
        days_late = (today - due).days
        who = f" with {vendor.name} ({vendor.phone_number})" if vendor else " and has no vendor assigned"

        managers = await db.scalars(
            select(User).where(
                User.organization_id == record.organization_id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
                User.is_active.is_(True),
            )
        )
        for manager in managers:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_user(manager),
                notification_type=NotificationType.MAINTENANCE_OVERDUE,
                title="Maintenance job is overdue",
                body=(
                    f"{record.reference_code} '{record.title}' at "
                    f"{property_record.name if property_record else 'a property'}"
                    f"{f' unit {unit.unit_number}' if unit else ''} is {days_late} day(s) past its "
                    f"expected completion date{who}."
                ),
                channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH, NotificationChannel.WHATSAPP],
                link_path=f"/maintenance/{record.id}",
                entity_type="maintenance_request",
                entity_id=record.id,
                organization_id=record.organization_id,
            )

    if rows:
        await db.commit()
    return len(rows)
