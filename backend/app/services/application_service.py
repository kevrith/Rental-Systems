"""The tenant application lifecycle (US-064, US-067).

An application arrives — from the public form or keyed in by staff — is scored,
reviewed, and ends as either a real tenancy or a documented rejection. The two
rules that matter throughout: a decision always records who made it and why, and
a unit with several applicants keeps them ranked rather than first-come.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.application import (
    APPLICATION_TRANSITIONS,
    OPEN_APPLICATION_STATUSES,
    ApplicationRejectionReason,
    ApplicationStatus,
    Guarantor,
    GuarantorStatus,
    ReferenceCheck,
    ReferenceStatus,
    TenantApplication,
)
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import User, UserRole
from app.schemas.application import (
    ApplicationApprove,
    ApplicationCreate,
    ApplicationReject,
    ApplicationUpdate,
)
from app.services import (
    audit_service,
    notification_service,
    reference_service,
    screening_service,
    tenant_pii,
)
from app.services.notifications import normalize_phone

ZERO = Decimal("0.00")

LIVE_TENANCY_STATUSES = [
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
]


def assert_transition(current: ApplicationStatus, target: ApplicationStatus) -> None:
    if target == current:
        return
    if target not in APPLICATION_TRANSITIONS.get(current, ()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An application that is {current.value.replace('_', ' ')} cannot become "
                f"{target.value.replace('_', ' ')}."
            ),
        )


async def _assert_unit_open(db: AsyncSession, unit: Unit) -> None:
    if unit.status == UnitStatus.OCCUPIED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This unit is already occupied and is not accepting applications",
        )


async def _find_duplicate(
    db: AsyncSession, organization_id: uuid.UUID, unit_id: uuid.UUID, phone: str, national_id: str | None
) -> TenantApplication | None:
    """The same person applying twice for the same unit (US-064).

    Matched on phone or ID rather than name — names are typed differently every
    time, phone numbers are not.
    """
    conditions = [TenantApplication.phone_number == phone]
    if national_id:
        conditions.append(TenantApplication.national_id == national_id)

    return await db.scalar(
        select(TenantApplication).where(
            TenantApplication.organization_id == organization_id,
            TenantApplication.unit_id == unit_id,
            TenantApplication.status.in_(OPEN_APPLICATION_STATUSES),
            or_(*conditions),
        )
    )


async def create_application(
    db: AsyncSession,
    organization_id: uuid.UUID,
    payload: ApplicationCreate,
    *,
    actor: User | None = None,
    submitted_online: bool = True,
    request: Request | None = None,
) -> TenantApplication:
    """Take an application. Used by both the public form and the staff screen,
    which is why it takes an organization id rather than an `OrgContext`."""
    unit = await db.get(Unit, payload.unit_id)
    if unit is None or unit.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    await _assert_unit_open(db, unit)

    phone = normalize_phone(payload.phone_number)
    duplicate = await _find_duplicate(db, organization_id, unit.id, phone, payload.national_id)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You already have an application open for this unit "
                f"({duplicate.reference_code}). We will be in touch."
            ),
        )

    code = await reference_service.generate_reference(db, TenantApplication, organization_id, "APP")
    application = TenantApplication(
        organization_id=organization_id,
        reference_code=code,
        status=ApplicationStatus.SUBMITTED,
        submitted_online=submitted_online,
        **payload.model_dump(
            exclude={"phone_number", "guarantors", "reference_landlords", "payslip_file_ids"}
        ),
        phone_number=phone,
        payslip_file_ids=[str(f) for f in payload.payslip_file_ids],
    )
    db.add(application)
    await db.flush()

    for guarantor in payload.guarantors:
        await screening_service.add_guarantor(
            db,
            application,
            full_name=guarantor.full_name,
            relationship_to_applicant=guarantor.relationship_to_applicant,
            phone_number=normalize_phone(guarantor.phone_number),
            email=guarantor.email,
            national_id=guarantor.national_id,
            id_document_id=guarantor.id_document_id,
            employer_name=guarantor.employer_name,
            occupation=guarantor.occupation,
            monthly_income=guarantor.monthly_income,
        )

    # The applicant's own previous landlord is asked automatically — the whole
    # point of US-068 is that nobody has to remember to do it.
    if payload.current_landlord_phone and payload.current_landlord_name:
        await screening_service.request_reference(
            db,
            application,
            landlord_name=payload.current_landlord_name,
            landlord_phone=normalize_phone(payload.current_landlord_phone),
            property_reference=payload.current_address,
        )

    await db.refresh(application, ["guarantors", "references"])
    await screening_service.rescore(db, application)

    audit_service.record(
        db,
        organization_id=organization_id,
        action="application.submitted",
        entity_type="tenant_application",
        entity_id=application.id,
        actor=actor,
        summary=(
            f"{application.full_name} applied for unit {unit.unit_number} "
            f"({code}), scoring {application.score}/100"
        ),
        request=request,
    )

    # If this person already enquired about the unit, the lead becomes the
    # application rather than a second row (US-075).
    from app.services import vacancy_service

    await vacancy_service.link_application_to_inquiry(db, application)

    await _confirm_to_applicant(db, application, unit)
    await _alert_managers_of_application(db, application, unit)

    await db.commit()
    await db.refresh(application)
    return application


async def _confirm_to_applicant(db: AsyncSession, application: TenantApplication, unit: Unit) -> None:
    property_record = await db.get(Property, unit.property_id)
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=application.phone_number, organization_id=application.organization_id
        ),
        notification_type=NotificationType.APPLICATION_RECEIVED,
        title="We have your application",
        body=(
            f"Thank you {application.full_name}. Your application for unit "
            f"{unit.unit_number} at {property_record.name if property_record else 'our property'} "
            f"has been received. Your reference is {application.reference_code}. "
            "We will let you know as soon as it has been reviewed."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="tenant_application",
        entity_id=application.id,
        organization_id=application.organization_id,
    )


async def _alert_managers_of_application(
    db: AsyncSession, application: TenantApplication, unit: Unit
) -> None:
    managers = await db.scalars(
        select(User).where(
            User.organization_id == application.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
            User.is_active.is_(True),
        )
    )
    for manager in managers:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(manager),
            notification_type=NotificationType.APPLICATION_RECEIVED,
            title="New tenant application",
            body=(
                f"{application.full_name} applied for unit {unit.unit_number}. "
                f"Screening score {application.score}/100 "
                f"({screening_service.band(application.score)})."
            ),
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
            link_path=f"/applications/{application.id}",
            entity_type="tenant_application",
            entity_id=application.id,
        )


async def get_application(
    db: AsyncSession, context: OrgContext, application_id: uuid.UUID
) -> TenantApplication:
    application = assert_in_org(await db.get(TenantApplication, application_id), context, label="application")
    unit = await db.get(Unit, application.unit_id)
    allowed = await accessible_property_ids(db, context)
    if unit is not None and allowed is not None and unit.property_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )
    return application


async def list_applications(
    db: AsyncSession,
    context: OrgContext,
    *,
    unit_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    application_status: ApplicationStatus | None = None,
    open_only: bool = False,
    search: str | None = None,
    limit: int = 100,
) -> list[TenantApplication]:
    query = select(TenantApplication).where(TenantApplication.organization_id == context.organization_id)

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(
            TenantApplication.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed)))
        )
    if unit_id:
        query = query.where(TenantApplication.unit_id == unit_id)
    if property_id:
        query = query.where(
            TenantApplication.unit_id.in_(select(Unit.id).where(Unit.property_id == property_id))
        )
    if application_status:
        query = query.where(TenantApplication.status == application_status)
    if open_only:
        query = query.where(TenantApplication.status.in_(OPEN_APPLICATION_STATUSES))
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                TenantApplication.full_name.ilike(term),
                TenantApplication.phone_number.ilike(term),
                TenantApplication.reference_code.ilike(term),
            )
        )

    # Best applicant first — the waiting list ordering from US-067, with the
    # earlier application winning a tie.
    rows = await db.scalars(
        query.order_by(TenantApplication.score.desc(), TenantApplication.created_at.asc()).limit(limit)
    )
    return list(rows)


async def waiting_list(db: AsyncSession, context: OrgContext, unit_id: uuid.UUID) -> list[dict]:
    """Everyone still in the running for one unit, ranked (US-067)."""
    rows = await list_applications(db, context, unit_id=unit_id, open_only=True, limit=100)
    return [
        {
            "rank": index + 1,
            "application_id": str(application.id),
            "reference_code": application.reference_code,
            "full_name": application.full_name,
            "phone_number": application.phone_number,
            "score": application.score,
            "band": screening_service.band(application.score),
            "status": application.status.value,
            "applied_at": application.created_at.isoformat(),
        }
        for index, application in enumerate(rows)
    ]


async def update_application(
    db: AsyncSession,
    context: OrgContext,
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    request: Request | None = None,
) -> TenantApplication:
    application = await get_application(db, context, application_id)
    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(application, field, value)

    await screening_service.rescore(db, application)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="application.updated",
        entity_type="tenant_application",
        entity_id=application.id,
        actor=context.user,
        summary=f"{application.reference_code}: updated {', '.join(sorted(fields)) or 'nothing'}",
        request=request,
    )
    await db.commit()
    await db.refresh(application)
    return application


async def _move(
    db: AsyncSession,
    context: OrgContext,
    application: TenantApplication,
    target: ApplicationStatus,
    *,
    action: str,
    summary: str,
    request: Request | None = None,
) -> None:
    from app.services import vacancy_service

    assert_transition(application.status, target)
    application.status = target
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action=action,
        entity_type="tenant_application",
        entity_id=application.id,
        actor=context.user,
        summary=f"{application.reference_code}: {summary}",
        request=request,
    )
    # Keep the vacancy pipeline in step: the lead this application came from
    # moves with it, so the conversion report never contradicts the file.
    await vacancy_service.sync_stage_from_application(db, application)


async def start_review(
    db: AsyncSession, context: OrgContext, application_id: uuid.UUID, request: Request | None = None
) -> TenantApplication:
    application = await get_application(db, context, application_id)
    await _move(
        db,
        context,
        application,
        ApplicationStatus.UNDER_REVIEW,
        action="application.review_started",
        summary=f"{context.user.full_name} started the review",
        request=request,
    )
    application.reviewed_at = datetime.now(UTC)
    await screening_service.rescore(db, application)
    await db.commit()
    await db.refresh(application)
    return application


async def schedule_interview(
    db: AsyncSession,
    context: OrgContext,
    application_id: uuid.UUID,
    when: datetime,
    note: str | None = None,
    request: Request | None = None,
) -> TenantApplication:
    application = await get_application(db, context, application_id)
    await _move(
        db,
        context,
        application,
        ApplicationStatus.INTERVIEW_SCHEDULED,
        action="application.interview_scheduled",
        summary=f"interview set for {when:%d %b %Y %H:%M} by {context.user.full_name}",
        request=request,
    )
    application.interview_at = when
    application.interview_notes = note

    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=application.phone_number, organization_id=application.organization_id
        ),
        notification_type=NotificationType.APPLICATION_RECEIVED,
        title="Interview scheduled",
        body=(
            f"Hi {application.full_name}, we would like to meet about your application "
            f"{application.reference_code} on {when:%d %b %Y at %H:%M}." + (f" {note}" if note else "")
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="tenant_application",
        entity_id=application.id,
        organization_id=application.organization_id,
    )
    await db.commit()
    await db.refresh(application)
    return application


async def approve(
    db: AsyncSession,
    context: OrgContext,
    application_id: uuid.UUID,
    payload: ApplicationApprove,
    request: Request | None = None,
) -> TenantApplication:
    """Approve: create the tenant from the application, reserve the unit, and
    tell everyone else on the waiting list where they stand (US-067).

    The tenancy itself is created separately, through the normal tenancy wizard —
    approval reserves the unit and hands over a real `Tenant` record, which is
    where screening ends and letting begins.
    """
    application = await get_application(db, context, application_id)
    unit = await db.get(Unit, application.unit_id)
    if unit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")

    occupied = await db.scalar(
        select(Tenancy).where(Tenancy.unit_id == unit.id, Tenancy.status.in_(LIVE_TENANCY_STATUSES))
    )
    if occupied is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This unit now has a live tenancy. Reject the application or pick another unit.",
        )

    await _move(
        db,
        context,
        application,
        ApplicationStatus.APPROVED,
        action="application.approved",
        summary=(
            f"approved by {context.user.full_name} at {application.score}/100"
            + (f" — {payload.note}" if payload.note else "")
        ),
        request=request,
    )
    application.decided_at = datetime.now(UTC)
    application.decided_by_id = context.user.id
    application.decision_note = payload.note

    tenant = await _tenant_from_application(db, application)
    application.tenant_id = tenant.id

    unit.status = UnitStatus.RESERVED

    property_record = await db.get(Property, unit.property_id)
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=application.phone_number, organization_id=application.organization_id
        ),
        notification_type=NotificationType.APPLICATION_APPROVED,
        title="Your application was approved",
        body=(
            f"Good news {application.full_name} — your application for unit "
            f"{unit.unit_number} at {property_record.name if property_record else 'our property'} "
            f"has been approved. We will be in touch to sign the lease and arrange your deposit."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="tenant_application",
        entity_id=application.id,
        organization_id=application.organization_id,
    )

    if payload.reject_others:
        await _reject_remaining(db, context, application, unit, request=request)

    await db.commit()
    await db.refresh(application)
    return application


async def _tenant_from_application(db: AsyncSession, application: TenantApplication) -> Tenant:
    """Turn the application into a tenant record, reusing an existing one if this
    person has rented from this organisation before."""
    existing = await db.scalar(
        select(Tenant).where(
            Tenant.organization_id == application.organization_id,
            Tenant.phone_number == application.phone_number,
        )
    )
    if existing is not None:
        return existing

    code = await reference_service.generate_reference(db, Tenant, application.organization_id, "TNT")
    tenant = Tenant(
        organization_id=application.organization_id,
        reference_code=code,
        full_name=application.full_name,
        phone_number=application.phone_number,
        email=application.email,
        id_photo_front_id=application.id_document_id,
        passport_photo_id=application.passport_photo_id,
        employer_name=application.employer_name,
        occupation=application.job_title,
        monthly_income=application.monthly_income,
        notes=(
            f"Created from application {application.reference_code} "
            f"(screening score {application.score}/100)."
        ),
    )
    await tenant_pii.set_national_id(db, tenant, application.national_id)
    db.add(tenant)
    await db.flush()
    return tenant


async def _reject_remaining(
    db: AsyncSession,
    context: OrgContext,
    approved: TenantApplication,
    unit: Unit,
    request: Request | None = None,
) -> None:
    """Close out the rest of the waiting list once the unit is taken.

    Leaving other applicants hanging is the most common complaint about how
    letting is done here, so it is the default rather than a follow-up task.
    """
    others = await db.scalars(
        select(TenantApplication).where(
            TenantApplication.organization_id == approved.organization_id,
            TenantApplication.unit_id == unit.id,
            TenantApplication.id != approved.id,
            TenantApplication.status.in_(OPEN_APPLICATION_STATUSES),
        )
    )
    for other in others:
        other.status = ApplicationStatus.REJECTED
        other.rejection_reason = ApplicationRejectionReason.UNIT_TAKEN
        other.decided_at = datetime.now(UTC)
        other.decided_by_id = context.user.id
        other.decision_note = f"Unit let to another applicant ({approved.reference_code})."

        audit_service.record(
            db,
            organization_id=approved.organization_id,
            action="application.rejected",
            entity_type="tenant_application",
            entity_id=other.id,
            actor=context.user,
            summary=f"{other.reference_code}: closed — unit taken",
            request=request,
        )
        await notification_service.send(
            db,
            recipient=notification_service.Recipient(
                phone_number=other.phone_number, organization_id=other.organization_id
            ),
            notification_type=NotificationType.APPLICATION_REJECTED,
            title="Your application",
            body=(
                f"Hi {other.full_name}, unit {unit.unit_number} has now been let to another "
                f"applicant. Thank you for applying — we will keep your details for the next "
                f"vacancy if you would like us to."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
            entity_type="tenant_application",
            entity_id=other.id,
            organization_id=other.organization_id,
        )


async def reject(
    db: AsyncSession,
    context: OrgContext,
    application_id: uuid.UUID,
    payload: ApplicationReject,
    request: Request | None = None,
) -> TenantApplication:
    application = await get_application(db, context, application_id)
    await _move(
        db,
        context,
        application,
        ApplicationStatus.REJECTED,
        action="application.rejected",
        summary=(
            f"rejected by {context.user.full_name} ({payload.reason.value})"
            + (f" — {payload.note}" if payload.note else "")
        ),
        request=request,
    )
    application.decided_at = datetime.now(UTC)
    application.decided_by_id = context.user.id
    application.rejection_reason = payload.reason
    application.decision_note = payload.note

    reason_text = payload.reason.value.replace("_", " ")
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=application.phone_number, organization_id=application.organization_id
        ),
        notification_type=NotificationType.APPLICATION_REJECTED,
        title="Your application",
        body=(
            f"Hi {application.full_name}, we are unable to proceed with your application "
            f"{application.reference_code}. Reason: {reason_text}."
            + (f" {payload.note}" if payload.note else "")
            + " Thank you for your interest."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="tenant_application",
        entity_id=application.id,
        organization_id=application.organization_id,
    )
    await db.commit()
    await db.refresh(application)
    return application


async def withdraw(
    db: AsyncSession,
    context: OrgContext,
    application_id: uuid.UUID,
    reason: str | None = None,
    request: Request | None = None,
) -> TenantApplication:
    application = await get_application(db, context, application_id)
    await _move(
        db,
        context,
        application,
        ApplicationStatus.WITHDRAWN,
        action="application.withdrawn",
        summary=f"withdrawn{f': {reason}' if reason else ''}",
        request=request,
    )
    application.decided_at = datetime.now(UTC)
    application.decision_note = reason
    await db.commit()
    await db.refresh(application)
    return application


async def screening_summary(db: AsyncSession, context: OrgContext) -> dict:
    """Counts for the applications screen header."""
    allowed = await accessible_property_ids(db, context)

    def scoped(query):
        query = query.where(TenantApplication.organization_id == context.organization_id)
        if allowed is not None:
            query = query.where(
                TenantApplication.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed)))
            )
        return query

    counts = {}
    for label, condition in (
        ("open", TenantApplication.status.in_(OPEN_APPLICATION_STATUSES)),
        ("awaiting_review", TenantApplication.status == ApplicationStatus.SUBMITTED),
        ("approved", TenantApplication.status == ApplicationStatus.APPROVED),
        ("rejected", TenantApplication.status == ApplicationStatus.REJECTED),
    ):
        counts[label] = int(
            await db.scalar(scoped(select(func.count(TenantApplication.id))).where(condition)) or 0
        )

    since = date.today() - timedelta(days=30)
    counts["last_30_days"] = int(
        await db.scalar(
            scoped(select(func.count(TenantApplication.id))).where(
                func.date(TenantApplication.created_at) >= since
            )
        )
        or 0
    )
    counts["awaiting_guarantor"] = int(
        await db.scalar(
            select(func.count(func.distinct(Guarantor.application_id))).where(
                Guarantor.organization_id == context.organization_id,
                Guarantor.status == GuarantorStatus.PENDING,
            )
        )
        or 0
    )
    counts["awaiting_reference"] = int(
        await db.scalar(
            select(func.count(func.distinct(ReferenceCheck.application_id))).where(
                ReferenceCheck.organization_id == context.organization_id,
                ReferenceCheck.status == ReferenceStatus.SENT,
            )
        )
        or 0
    )
    return counts
