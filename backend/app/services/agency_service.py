"""Agency mode service — Phase 2 (US-034, US-035, US-036, US-039, US-040, US-041, US-042).

Handles owner profile CRUD, management fee calculation, disbursement
calculation and initiation, and owner statement generation.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.agency import Disbursement, DisbursementStatus, OwnerProfile
from app.models.billing import Payment, PaymentStatus
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import OperatingMode
from app.models.property import Property, Unit
from app.models.tenant import Tenancy
from app.models.user import UserRole
from app.services import (
    audit_service,
    file_service,
    mpesa_service,
    notification_service,
    owner_statement_service,
    reference_service,
)
from app.services.pdf_service import format_kes

ZERO = Decimal("0.00")


def _require_agency(context: OrgContext) -> None:
    if context.organization.operating_mode != OperatingMode.AGENCY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This feature is only available in agency mode",
        )


# ----------------------------------------------------------------- owner profiles


async def create_owner_profile(
    db: AsyncSession,
    context: OrgContext,
    *,
    full_name: str,
    phone_number: str,
    email: str | None = None,
    national_id: str | None = None,
    kra_pin: str | None = None,
    bank_name: str | None = None,
    bank_account_number: str | None = None,
    bank_account_name: str | None = None,
    mpesa_phone: str | None = None,
    management_fee_percent: Decimal = Decimal("8.00"),
    disbursement_day: int = 5,
    maintenance_auto_approve_limit: Decimal = Decimal("5000.00"),
    maintenance_notify_limit: Decimal = Decimal("20000.00"),
    notes: str | None = None,
) -> OwnerProfile:
    _require_agency(context)
    code = await reference_service.generate_reference(db, OwnerProfile, context.organization_id, "OWN")
    profile = OwnerProfile(
        organization_id=context.organization_id,
        reference_code=code,
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        national_id=national_id,
        kra_pin=kra_pin,
        bank_name=bank_name,
        bank_account_number=bank_account_number,
        bank_account_name=bank_account_name,
        mpesa_phone=mpesa_phone,
        management_fee_percent=management_fee_percent,
        disbursement_day=disbursement_day,
        maintenance_auto_approve_limit=maintenance_auto_approve_limit,
        maintenance_notify_limit=maintenance_notify_limit,
        notes=notes,
    )
    db.add(profile)
    await db.flush()
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="owner_profile.created",
        entity_type="owner_profile",
        entity_id=profile.id,
        actor=context.user,
        summary=f"Created owner profile for {full_name}",
    )
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_owner_profiles(db: AsyncSession, context: OrgContext) -> list[OwnerProfile]:
    _require_agency(context)
    rows = await db.scalars(
        select(OwnerProfile)
        .where(OwnerProfile.organization_id == context.organization_id, OwnerProfile.is_active.is_(True))
        .order_by(OwnerProfile.full_name)
    )
    return list(rows)


async def get_owner_profile(db: AsyncSession, context: OrgContext, profile_id: uuid.UUID) -> OwnerProfile:
    profile = await db.get(OwnerProfile, profile_id)
    return assert_in_org(profile, context, label="owner profile")


async def update_owner_profile(
    db: AsyncSession,
    context: OrgContext,
    profile_id: uuid.UUID,
    updates: dict,
) -> OwnerProfile:
    _require_agency(context)
    profile = await get_owner_profile(db, context, profile_id)
    allowed = {
        "full_name",
        "phone_number",
        "email",
        "national_id",
        "kra_pin",
        "bank_name",
        "bank_account_number",
        "bank_account_name",
        "mpesa_phone",
        "management_fee_percent",
        "disbursement_day",
        "maintenance_auto_approve_limit",
        "maintenance_notify_limit",
        "notes",
    }
    for key, value in updates.items():
        if key in allowed:
            setattr(profile, key, value)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="owner_profile.updated",
        entity_type="owner_profile",
        entity_id=profile.id,
        actor=context.user,
        summary=f"Updated owner profile {profile.reference_code}",
        changes={
            k: str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "Decimal" else v
            for k, v in updates.items()
        },
    )
    await db.commit()
    await db.refresh(profile)
    return profile


# ----------------------------------------------------------------- owner portal invite (US-038)


async def invite_owner_to_portal(
    db: AsyncSession,
    context: OrgContext,
    profile_id: uuid.UUID,
) -> OwnerProfile:
    """Create a User with OWNER_PORTAL_USER role and link it to the owner profile."""
    from app.services import auth_service

    _require_agency(context)
    profile = await get_owner_profile(db, context, profile_id)

    if profile.portal_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Owner already has portal access")

    # Create a portal user account for the owner
    portal_user = await auth_service.create_portal_user(
        db,
        organization_id=context.organization_id,
        full_name=profile.full_name,
        phone_number=profile.phone_number,
        email=profile.email,
        role=UserRole.OWNER_PORTAL_USER,
    )
    profile.portal_user_id = portal_user.id
    profile.portal_invited_at = datetime.now(UTC)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="owner_profile.portal_invited",
        entity_type="owner_profile",
        entity_id=profile.id,
        actor=context.user,
        summary=f"Invited {profile.full_name} to owner portal",
    )

    # Notify the owner
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(phone_number=profile.mpesa_phone or profile.phone_number),
        notification_type=NotificationType.OWNER_PORTAL_INVITE,
        title="You've been invited to the owner portal",
        body=(
            f"Dear {profile.full_name}, {context.organization.name} has invited you to view "
            f"your property portfolio on RentFlow. Set up your access at: "
            f"[portal link will be sent separately]"
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        organization_id=context.organization_id,
    )

    await db.commit()
    await db.refresh(profile)
    return profile


# ----------------------------------------------------------------- disbursements (US-039, US-040, US-041)


async def calculate_disbursement(
    db: AsyncSession,
    context: OrgContext,
    owner_profile_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> dict:
    """Calculate what an owner is owed for a period — preview before initiating."""
    _require_agency(context)
    profile = await get_owner_profile(db, context, owner_profile_id)
    return await calculate_for_profile(db, profile, period_start, period_end)


async def calculate_for_profile(
    db: AsyncSession,
    profile: OwnerProfile,
    period_start: date,
    period_end: date,
) -> dict:
    """The calculation itself, with no request context.

    Split out so the nightly disbursement scheduler — which has no logged-in user
    to scope against — arrives at exactly the same numbers as the preview screen.
    """
    owner_profile_id = profile.id
    organization_id = profile.organization_id

    # Get all properties belonging to this owner
    property_ids = list(
        await db.scalars(
            select(Property.id).where(
                Property.organization_id == organization_id,
                Property.owner_profile_id == owner_profile_id,
                Property.is_archived.is_(False),
            )
        )
    )
    if not property_ids:
        return {
            "owner_profile": profile,
            "gross_rent": ZERO,
            "management_fee": ZERO,
            "maintenance_costs": ZERO,
            "other_deductions": ZERO,
            "net_amount": ZERO,
            "payments": [],
        }

    # Get all confirmed payments for this owner's units in the period
    unit_ids = list(
        await db.scalars(
            select(Unit.id).where(Unit.property_id.in_(property_ids), Unit.is_archived.is_(False))
        )
    )

    payments_query = (
        select(Payment)
        .join(Tenancy, Tenancy.id == Payment.tenancy_id)
        .where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.CONFIRMED,
            Tenancy.unit_id.in_(unit_ids),
            Payment.payment_date >= period_start,
            Payment.payment_date <= period_end,
        )
    )
    payments = list(await db.scalars(payments_query))
    gross_rent = sum((Decimal(p.amount) for p in payments), ZERO)

    fee_rate = Decimal(profile.management_fee_percent) / Decimal("100")
    management_fee = (gross_rent * fee_rate).quantize(Decimal("0.01"))

    # Maintenance costs: sum of completed maintenance requests with costs in period
    from app.models.operations import BILLABLE_STATUSES, MaintenanceRequest

    maintenance_rows = await db.scalars(
        select(MaintenanceRequest).where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.unit_id.in_(unit_ids),
            MaintenanceRequest.status.in_(BILLABLE_STATUSES),
            MaintenanceRequest.completed_at
            >= datetime.combine(period_start, datetime.min.time()).replace(tzinfo=UTC),
            MaintenanceRequest.completed_at
            <= datetime.combine(period_end, datetime.max.time()).replace(tzinfo=UTC),
            MaintenanceRequest.cost.is_not(None),
        )
    )
    maintenance_costs = sum((Decimal(r.cost) for r in maintenance_rows if r.cost), ZERO)

    net_amount = gross_rent - management_fee - maintenance_costs

    return {
        "owner_profile": profile,
        "gross_rent": gross_rent,
        "management_fee": management_fee,
        "maintenance_costs": maintenance_costs,
        "other_deductions": ZERO,
        "net_amount": net_amount,
        "payments": payments,
    }


async def create_disbursement(
    db: AsyncSession,
    context: OrgContext,
    owner_profile_id: uuid.UUID,
    period_start: date,
    period_end: date,
    notes: str | None = None,
) -> Disbursement:
    _require_agency(context)
    calc = await calculate_disbursement(db, context, owner_profile_id, period_start, period_end)
    profile: OwnerProfile = calc["owner_profile"]

    code = await reference_service.generate_reference(db, Disbursement, context.organization_id, "DSB")
    disbursement = Disbursement(
        organization_id=context.organization_id,
        reference_code=code,
        owner_profile_id=owner_profile_id,
        period_start=period_start,
        period_end=period_end,
        gross_rent=calc["gross_rent"],
        management_fee=calc["management_fee"],
        maintenance_costs=calc["maintenance_costs"],
        other_deductions=ZERO,
        net_amount=calc["net_amount"],
        status=DisbursementStatus.PENDING,
        initiated_by_id=context.user.id,
        notes=notes,
    )
    db.add(disbursement)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="disbursement.created",
        entity_type="disbursement",
        entity_id=disbursement.id,
        actor=context.user,
        summary=(
            f"Disbursement for {profile.full_name}: gross KES {format_kes(calc['gross_rent'])}, "
            f"fee KES {format_kes(calc['management_fee'])}, net KES {format_kes(calc['net_amount'])}"
        ),
    )

    # Notify owner
    await _notify_disbursement(db, disbursement, profile, context.organization_id)

    await db.commit()
    await db.refresh(disbursement)
    return disbursement


# ----------------------------------------------------------------- approval workflow (US-041)

# Only these states may still be reviewed; everything else has already moved money
# or been decided.
_REVIEWABLE = {DisbursementStatus.PENDING}
# A payout may only leave from a reviewed, approved disbursement.
_PAYABLE = {DisbursementStatus.APPROVED, DisbursementStatus.FAILED}


async def _get_disbursement(
    db: AsyncSession, context: OrgContext, disbursement_id: uuid.UUID
) -> Disbursement:
    return assert_in_org(await db.get(Disbursement, disbursement_id), context, label="disbursement")


async def approve_disbursement(
    db: AsyncSession,
    context: OrgContext,
    disbursement_id: uuid.UUID,
    note: str | None = None,
) -> Disbursement:
    """Sign off on the numbers. Nothing can be paid until this happens."""
    _require_agency(context)
    disbursement = await _get_disbursement(db, context, disbursement_id)

    if disbursement.status not in _REVIEWABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {disbursement.status.value} disbursement cannot be approved",
        )
    if Decimal(disbursement.net_amount) <= ZERO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There is nothing to pay out — the net amount is zero or negative",
        )

    disbursement.status = DisbursementStatus.APPROVED
    disbursement.approved_by_id = context.user.id
    disbursement.approved_at = datetime.now(UTC)
    disbursement.rejection_reason = None
    if note:
        disbursement.notes = note

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="disbursement.approved",
        entity_type="disbursement",
        entity_id=disbursement.id,
        actor=context.user,
        summary=(
            f"Approved disbursement {disbursement.reference_code} "
            f"for KES {format_kes(disbursement.net_amount)}"
        ),
    )
    await db.commit()
    await db.refresh(disbursement)
    return disbursement


async def reject_disbursement(
    db: AsyncSession,
    context: OrgContext,
    disbursement_id: uuid.UUID,
    reason: str,
) -> Disbursement:
    """Send a disbursement back — the numbers are wrong or the period is not closed."""
    _require_agency(context)
    disbursement = await _get_disbursement(db, context, disbursement_id)

    if disbursement.status not in _REVIEWABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {disbursement.status.value} disbursement cannot be rejected",
        )

    disbursement.status = DisbursementStatus.REJECTED
    disbursement.approved_by_id = context.user.id
    disbursement.approved_at = datetime.now(UTC)
    disbursement.rejection_reason = reason

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="disbursement.rejected",
        entity_type="disbursement",
        entity_id=disbursement.id,
        actor=context.user,
        summary=f"Rejected disbursement {disbursement.reference_code}: {reason}",
    )
    await db.commit()
    await db.refresh(disbursement)
    return disbursement


# ----------------------------------------------------------------- payout (US-041, US-042)


async def _settle_payout(
    db: AsyncSession,
    disbursement: Disbursement,
    *,
    success: bool,
    payment_method: str,
    payment_reference: str | None = None,
    failure_reason: str | None = None,
) -> Disbursement:
    """Land a payout in its final state and, when it worked, issue the statement.

    Used by both the manual path and the M-Pesa B2C result callback so a
    disbursement settles identically however the money moved.
    """
    disbursement.payment_method = payment_method
    if success:
        disbursement.status = DisbursementStatus.COMPLETED
        disbursement.payment_reference = payment_reference
        disbursement.paid_at = datetime.now(UTC)
        disbursement.failure_reason = None

        statement = await owner_statement_service.generate_statement(db, disbursement)
        await owner_statement_service.deliver_statement(db, disbursement, statement)
    else:
        disbursement.status = DisbursementStatus.FAILED
        disbursement.failure_reason = (failure_reason or "Payout failed")[:512]

    return disbursement


async def mark_disbursement_paid(
    db: AsyncSession,
    context: OrgContext,
    disbursement_id: uuid.UUID,
    payment_method: str,
    payment_reference: str,
) -> Disbursement:
    """Record a payout made outside the platform — bank transfer, cheque, cash."""
    disbursement = await _get_disbursement(db, context, disbursement_id)
    if disbursement.status == DisbursementStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Disbursement already completed")
    if disbursement.status not in _PAYABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {disbursement.status.value} disbursement must be approved before it is paid",
        )

    await _settle_payout(
        db,
        disbursement,
        success=True,
        payment_method=payment_method,
        payment_reference=payment_reference,
    )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="disbursement.paid",
        entity_type="disbursement",
        entity_id=disbursement.id,
        actor=context.user,
        summary=f"Disbursement {disbursement.reference_code} marked paid via {payment_method}",
    )
    await db.commit()
    await db.refresh(disbursement)
    return disbursement


async def initiate_mpesa_payout(
    db: AsyncSession,
    context: OrgContext,
    disbursement_id: uuid.UUID,
) -> Disbursement:
    """Push an approved disbursement to the owner's M-Pesa number via Daraja B2C.

    Daraja acknowledges the request and reports the outcome later on the result
    callback, so the disbursement parks in PROCESSING. Without B2C credentials the
    stub returns immediately and we settle in the same call, which keeps the whole
    flow exercisable offline.
    """
    _require_agency(context)
    disbursement = await _get_disbursement(db, context, disbursement_id)

    if disbursement.status == DisbursementStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Disbursement already completed")
    if disbursement.status == DisbursementStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A payout for this disbursement is already in flight"
        )
    if disbursement.status not in _PAYABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {disbursement.status.value} disbursement must be approved before it is paid",
        )

    profile = await get_owner_profile(db, context, disbursement.owner_profile_id)
    destination = profile.mpesa_phone or profile.phone_number
    if not destination:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This owner has no M-Pesa number on file — add one or pay them by bank transfer",
        )

    try:
        result = await mpesa_service.initiate_b2c_payment(
            phone_number=destination,
            amount=Decimal(disbursement.net_amount),
            remarks=f"Rent disbursement {disbursement.reference_code}",
            occasion=disbursement.period_start.strftime("%b %Y"),
            disbursement_id=disbursement.id,
        )
    except mpesa_service.MpesaError as exc:
        disbursement.status = DisbursementStatus.FAILED
        disbursement.payment_method = "mpesa"
        disbursement.failure_reason = str(exc)[:512]
        audit_service.record(
            db,
            organization_id=context.organization_id,
            action="disbursement.payout_rejected",
            entity_type="disbursement",
            entity_id=disbursement.id,
            actor=context.user,
            summary=f"M-Pesa rejected the payout for {disbursement.reference_code}: {exc}",
        )
        await db.commit()
        await db.refresh(disbursement)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    disbursement.status = DisbursementStatus.PROCESSING
    disbursement.payment_method = "mpesa"
    disbursement.payout_conversation_id = result.conversation_id
    disbursement.payout_originator_id = result.originator_conversation_id
    disbursement.payout_requested_at = datetime.now(UTC)
    disbursement.failure_reason = None

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="disbursement.payout_initiated",
        entity_type="disbursement",
        entity_id=disbursement.id,
        actor=context.user,
        summary=(
            f"Sent KES {format_kes(disbursement.net_amount)} to {destination} "
            f"for {disbursement.reference_code} ({result.response_description})"
        ),
    )

    if result.simulated:
        # No callback is ever coming for a stubbed payout — settle it now.
        await _settle_payout(
            db,
            disbursement,
            success=True,
            payment_method="mpesa",
            payment_reference=result.conversation_id,
        )

    await db.commit()
    await db.refresh(disbursement)
    return disbursement


async def handle_b2c_result(db: AsyncSession, result: mpesa_service.B2CResult) -> Disbursement | None:
    """Apply a Daraja B2C result callback to the disbursement that requested it.

    Runs outside a request context (Safaricom is the caller), so it matches on the
    conversation ids alone and does its own commit.
    """
    disbursement = await db.scalar(
        select(Disbursement).where(
            Disbursement.payout_conversation_id == result.conversation_id,
        )
    )
    if disbursement is None and result.originator_conversation_id:
        disbursement = await db.scalar(
            select(Disbursement).where(
                Disbursement.payout_originator_id == result.originator_conversation_id,
            )
        )
    if disbursement is None:
        return None

    if disbursement.status == DisbursementStatus.COMPLETED:
        return disbursement  # A retried delivery of a result we already applied.

    await _settle_payout(
        db,
        disbursement,
        success=result.success,
        payment_method="mpesa",
        payment_reference=result.transaction_id or result.conversation_id,
        failure_reason=result.result_description,
    )

    audit_service.record(
        db,
        organization_id=disbursement.organization_id,
        action="disbursement.payout_settled",
        entity_type="disbursement",
        entity_id=disbursement.id,
        actor=None,
        summary=(
            f"M-Pesa reported {disbursement.reference_code} as "
            f"{disbursement.status.value}: {result.result_description}"
        ),
    )
    await db.commit()
    await db.refresh(disbursement)
    return disbursement


async def fail_pending_payout(db: AsyncSession, conversation_id: str, reason: str) -> None:
    """Daraja queue timeout — the request never reached the payment engine."""
    disbursement = await db.scalar(
        select(Disbursement).where(Disbursement.payout_conversation_id == conversation_id)
    )
    if disbursement is None or disbursement.status != DisbursementStatus.PROCESSING:
        return
    disbursement.status = DisbursementStatus.FAILED
    disbursement.failure_reason = reason[:512]
    await db.commit()


# ----------------------------------------------------------------- owner statements (US-042)


async def statement_for_disbursement(
    db: AsyncSession,
    context: OrgContext,
    disbursement_id: uuid.UUID,
    *,
    regenerate: bool = False,
) -> dict:
    """Return a download URL for the statement, rendering it on demand if needed."""
    disbursement = await _get_disbursement(db, context, disbursement_id)
    record = await owner_statement_service.generate_statement(db, disbursement, force=regenerate)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The statement could not be rendered — the PDF backend is unavailable",
        )
    await db.commit()
    return {
        "disbursement_id": str(disbursement.id),
        "document_id": str(record.id),
        "filename": record.filename,
        "url": file_service.to_url(record),
    }


async def list_disbursements(
    db: AsyncSession,
    context: OrgContext,
    owner_profile_id: uuid.UUID | None = None,
) -> list[Disbursement]:
    _require_agency(context)
    query = select(Disbursement).where(Disbursement.organization_id == context.organization_id)
    if owner_profile_id:
        query = query.where(Disbursement.owner_profile_id == owner_profile_id)
    rows = await db.scalars(query.order_by(Disbursement.created_at.desc()))
    return list(rows)


# ----------------------------------------------------------------- agency dashboard (US-037)


async def agency_dashboard_stats(db: AsyncSession, context: OrgContext) -> dict:
    """Aggregate stats for the agency portfolio overview."""
    _require_agency(context)
    org_id = context.organization_id

    total_properties = (
        await db.scalar(
            select(func.count(Property.id)).where(
                Property.organization_id == org_id, Property.is_archived.is_(False)
            )
        )
        or 0
    )

    total_units = (
        await db.scalar(
            select(func.count(Unit.id)).where(Unit.organization_id == org_id, Unit.is_archived.is_(False))
        )
        or 0
    )

    from app.models.property import UnitStatus

    occupied_units = (
        await db.scalar(
            select(func.count(Unit.id)).where(
                Unit.organization_id == org_id,
                Unit.is_archived.is_(False),
                Unit.status == UnitStatus.OCCUPIED,
            )
        )
        or 0
    )

    # Total rent collected this month
    today = date.today()
    month_start = today.replace(day=1)
    collected_this_month = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == org_id,
                Payment.status == PaymentStatus.CONFIRMED,
                Payment.payment_date >= month_start,
            )
        )
        or ZERO
    )

    # Pending disbursements
    pending_disbursements = (
        await db.scalar(
            select(func.count(Disbursement.id)).where(
                Disbursement.organization_id == org_id,
                Disbursement.status == DisbursementStatus.PENDING,
            )
        )
        or 0
    )

    # Management fees earned this month
    disbursements_this_month = list(
        await db.scalars(
            select(Disbursement).where(
                Disbursement.organization_id == org_id,
                Disbursement.period_start >= month_start,
            )
        )
    )
    fees_this_month = sum((Decimal(d.management_fee) for d in disbursements_this_month), ZERO)

    owner_count = (
        await db.scalar(
            select(func.count(OwnerProfile.id)).where(
                OwnerProfile.organization_id == org_id, OwnerProfile.is_active.is_(True)
            )
        )
        or 0
    )

    return {
        "total_properties": total_properties,
        "total_units": total_units,
        "occupied_units": occupied_units,
        "occupancy_rate": round(occupied_units / total_units * 100, 1) if total_units else 0.0,
        "collected_this_month": collected_this_month,
        "pending_disbursements": pending_disbursements,
        "management_fees_this_month": fees_this_month,
        "owner_count": owner_count,
    }


# ----------------------------------------------------------------- owner portal data (US-038)


async def owner_portal_summary(
    db: AsyncSession, portal_user_id: uuid.UUID, organization_id: uuid.UUID
) -> dict:
    """Read-only summary for an owner portal user — scoped to their properties only."""
    profile = await db.scalar(
        select(OwnerProfile).where(
            OwnerProfile.portal_user_id == portal_user_id,
            OwnerProfile.organization_id == organization_id,
        )
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner profile not found")

    properties = list(
        await db.scalars(
            select(Property).where(
                Property.owner_profile_id == profile.id,
                Property.is_archived.is_(False),
            )
        )
    )
    property_ids = [p.id for p in properties]

    from app.models.property import UnitStatus

    units = list(
        await db.scalars(select(Unit).where(Unit.property_id.in_(property_ids), Unit.is_archived.is_(False)))
    )
    unit_ids = [u.id for u in units]
    occupied = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)

    today = date.today()
    month_start = today.replace(day=1)
    collected = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Tenancy, Tenancy.id == Payment.tenancy_id)
            .where(
                Payment.organization_id == organization_id,
                Payment.status == PaymentStatus.CONFIRMED,
                Tenancy.unit_id.in_(unit_ids),
                Payment.payment_date >= month_start,
            )
        )
        or ZERO
    )

    disbursements = list(
        await db.scalars(
            select(Disbursement)
            .where(
                Disbursement.organization_id == organization_id,
                Disbursement.owner_profile_id == profile.id,
            )
            .order_by(Disbursement.created_at.desc())
            .limit(6)
        )
    )

    return {
        "owner_profile": profile,
        "properties": properties,
        "total_units": len(units),
        "occupied_units": occupied,
        "occupancy_rate": round(occupied / len(units) * 100, 1) if units else 0.0,
        "collected_this_month": collected,
        "recent_disbursements": disbursements,
    }


# ----------------------------------------------------------------- helpers


async def _notify_disbursement(
    db: AsyncSession,
    disbursement: Disbursement,
    profile: OwnerProfile,
    organization_id: uuid.UUID,
) -> None:
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(phone_number=profile.mpesa_phone or profile.phone_number),
        notification_type=NotificationType.DISBURSEMENT_SENT,
        title="Disbursement prepared",
        body=(
            f"Dear {profile.full_name}, your disbursement for "
            f"{disbursement.period_start.strftime('%b %Y')} has been prepared.\n"
            f"Gross rent: KES {format_kes(disbursement.gross_rent)}\n"
            f"Management fee: KES {format_kes(disbursement.management_fee)}\n"
            f"Maintenance costs: KES {format_kes(disbursement.maintenance_costs)}\n"
            f"Net payable: KES {format_kes(disbursement.net_amount)}\n"
            f"Reference: {disbursement.reference_code}"
        ),
        channels=[NotificationChannel.WHATSAPP],
        entity_type="disbursement",
        entity_id=disbursement.id,
        organization_id=organization_id,
    )


# ----------------------------------------------------------------- per-owner rollup (US-037)


async def owner_summaries(db: AsyncSession, context: OrgContext) -> list[dict]:
    """Per-owner summary cards for the agency dashboard.

    One row per active owner profile: properties and units managed, occupancy,
    what was collected and billed this month, outstanding arrears, and the state
    of their most recent disbursement.
    """
    _require_agency(context)
    org_id = context.organization_id

    from app.models.billing import Invoice, InvoiceStatus
    from app.models.property import UnitStatus

    profiles = list(
        await db.scalars(
            select(OwnerProfile)
            .where(OwnerProfile.organization_id == org_id, OwnerProfile.is_active.is_(True))
            .order_by(OwnerProfile.full_name)
        )
    )
    if not profiles:
        return []

    today = date.today()
    month_start = today.replace(day=1)

    # Property -> owner, in one pass.
    property_rows = list(
        await db.execute(
            select(Property.id, Property.owner_profile_id).where(
                Property.organization_id == org_id,
                Property.is_archived.is_(False),
                Property.owner_profile_id.is_not(None),
            )
        )
    )
    owner_of_property = {pid: oid for pid, oid in property_rows}

    unit_rows = list(
        await db.execute(
            select(Unit.id, Unit.property_id, Unit.status).where(
                Unit.organization_id == org_id, Unit.is_archived.is_(False)
            )
        )
    )
    owner_of_unit: dict[uuid.UUID, uuid.UUID] = {}
    units_by_owner: dict[uuid.UUID, list[UnitStatus]] = {}
    properties_by_owner: dict[uuid.UUID, set[uuid.UUID]] = {}
    for unit_id, property_id, unit_status in unit_rows:
        owner_id = owner_of_property.get(property_id)
        if owner_id is None:
            continue
        owner_of_unit[unit_id] = owner_id
        units_by_owner.setdefault(owner_id, []).append(unit_status)
        properties_by_owner.setdefault(owner_id, set()).add(property_id)

    # Collected this month, per owner.
    collected_by_owner: dict[uuid.UUID, Decimal] = {}
    payment_rows = list(
        await db.execute(
            select(Tenancy.unit_id, Payment.amount)
            .join(Tenancy, Tenancy.id == Payment.tenancy_id)
            .where(
                Payment.organization_id == org_id,
                Payment.status == PaymentStatus.CONFIRMED,
                Payment.payment_date >= month_start,
            )
        )
    )
    for unit_id, amount in payment_rows:
        owner_id = owner_of_unit.get(unit_id)
        if owner_id is not None:
            collected_by_owner[owner_id] = collected_by_owner.get(owner_id, ZERO) + Decimal(amount)

    # Billed this month and outstanding arrears, per owner.
    billed_by_owner: dict[uuid.UUID, Decimal] = {}
    arrears_by_owner: dict[uuid.UUID, Decimal] = {}
    invoice_rows = list(
        await db.execute(
            select(Tenancy.unit_id, Invoice.total, Invoice.amount_paid, Invoice.status, Invoice.issue_date)
            .join(Tenancy, Tenancy.id == Invoice.tenancy_id)
            .where(
                Invoice.organization_id == org_id,
                Invoice.status != InvoiceStatus.CANCELLED,
            )
        )
    )
    for unit_id, total, amount_paid, invoice_status, issue_date in invoice_rows:
        owner_id = owner_of_unit.get(unit_id)
        if owner_id is None:
            continue
        balance = Decimal(total) - Decimal(amount_paid)
        if issue_date and issue_date >= month_start:
            billed_by_owner[owner_id] = billed_by_owner.get(owner_id, ZERO) + Decimal(total)
        if balance > ZERO and invoice_status != InvoiceStatus.PAID:
            arrears_by_owner[owner_id] = arrears_by_owner.get(owner_id, ZERO) + balance

    # Latest disbursement per owner.
    latest_disbursements = list(
        await db.scalars(
            select(Disbursement)
            .where(Disbursement.organization_id == org_id)
            .order_by(Disbursement.created_at.desc())
        )
    )
    latest_by_owner: dict[uuid.UUID, Disbursement] = {}
    for d in latest_disbursements:
        latest_by_owner.setdefault(d.owner_profile_id, d)

    summaries: list[dict] = []
    for profile in profiles:
        statuses = units_by_owner.get(profile.id, [])
        unit_count = len(statuses)
        occupied = sum(1 for s in statuses if s == UnitStatus.OCCUPIED)
        collected = collected_by_owner.get(profile.id, ZERO)
        billed = billed_by_owner.get(profile.id, ZERO)
        latest = latest_by_owner.get(profile.id)

        summaries.append(
            {
                "owner_profile_id": str(profile.id),
                "reference_code": profile.reference_code,
                "full_name": profile.full_name,
                "phone_number": profile.phone_number,
                "email": profile.email,
                "management_fee_percent": float(profile.management_fee_percent),
                "disbursement_day": profile.disbursement_day,
                "portal_invited": profile.portal_user_id is not None,
                "property_count": len(properties_by_owner.get(profile.id, set())),
                "unit_count": unit_count,
                "occupied_units": occupied,
                "occupancy_rate": round(occupied / unit_count * 100, 1) if unit_count else 0.0,
                "collected_this_month": float(collected),
                "billed_this_month": float(billed),
                "collection_rate": round(float(collected / billed * 100), 1) if billed > ZERO else 0.0,
                "arrears": float(arrears_by_owner.get(profile.id, ZERO)),
                "last_disbursement": (
                    {
                        "id": str(latest.id),
                        "reference_code": latest.reference_code,
                        "status": latest.status.value,
                        "net_amount": float(latest.net_amount),
                        "period_start": latest.period_start.isoformat(),
                        "period_end": latest.period_end.isoformat(),
                        "paid_at": latest.paid_at.isoformat() if latest.paid_at else None,
                    }
                    if latest
                    else None
                ),
            }
        )

    return summaries
