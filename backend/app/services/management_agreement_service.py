"""The owner-agency management agreement (masterplan, Management Agreement Module).

Sprint 7 built the *terms* — `OwnerProfile` carries the fee percentage the
disbursement run charges and the limits maintenance approval checks — and the
document vault to hold whatever paper an agency already had. What it never
built was the instrument itself: a generated contract, signed by both parties,
with a termination workflow that respects the notice period.

Three decisions worth stating, because each is a place this could have been
done differently:

**The terms are copied, not referenced.** `ManagementAgreement` snapshots the
fee, the disbursement day and the authority limits as they stood when both
parties signed. Editing the owner profile afterwards changes what the software
does from that point on; it does not change what was agreed. When the two
disagree, both numbers are on the record and the difference is visible.

**Both signatures are ordinary `DigitalSignature` rows.** The OTP signing
pipeline built for leases (US-044) already does identity verification, audit
capture and PDF attestation. Dual signing is two of those, not a second
mechanism — and `activate_if_fully_signed` below is the only thing that knows
an agreement needs both.

**Termination is a state, not a delete.** Between notice and effective date the
agency is still managing, still collecting rent, still owed its fee. An
agreement in `TERMINATION_NOTICE` is live; only the sweep past the effective
date makes it `TERMINATED`.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.agency import (
    ManagementAgreement,
    ManagementAgreementStatus,
    OwnerProfile,
    TerminationParty,
)
from app.models.file import FileCategory
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import OperatingMode, Organization
from app.models.property import Property, Unit
from app.models.signature import DigitalSignature, SignatureStatus
from app.models.user import User, UserRole
from app.services import (
    audit_service,
    notification_service,
    pdf_service,
    reference_service,
    storage_service,
)

# A month of notice is the shortest either side can sensibly give: tenants have
# to be told where to pay, and deposits have to be reconciled and handed over.
MIN_NOTICE_DAYS = 30


# ------------------------------------------------------------------- loading


async def get(db: AsyncSession, context: OrgContext, agreement_id: uuid.UUID) -> ManagementAgreement:
    return assert_in_org(
        await db.get(ManagementAgreement, agreement_id), context, label="management agreement"
    )


async def list_agreements(
    db: AsyncSession,
    context: OrgContext,
    *,
    owner_profile_id: uuid.UUID | None = None,
    live_only: bool = False,
) -> list[ManagementAgreement]:
    query = select(ManagementAgreement).where(ManagementAgreement.organization_id == context.organization_id)
    if owner_profile_id is not None:
        query = query.where(ManagementAgreement.owner_profile_id == owner_profile_id)
    if live_only:
        query = query.where(
            ManagementAgreement.status.in_(
                [ManagementAgreementStatus.ACTIVE, ManagementAgreementStatus.TERMINATION_NOTICE]
            )
        )
    rows = await db.scalars(query.order_by(ManagementAgreement.created_at.desc()))
    return list(rows)


async def current_for_owner(
    db: AsyncSession, organization_id: uuid.UUID, owner_profile_id: uuid.UUID
) -> ManagementAgreement | None:
    """The agreement in force for this owner, if any."""
    return await db.scalar(
        select(ManagementAgreement)
        .where(
            ManagementAgreement.organization_id == organization_id,
            ManagementAgreement.owner_profile_id == owner_profile_id,
            ManagementAgreement.status.in_(
                [ManagementAgreementStatus.ACTIVE, ManagementAgreementStatus.TERMINATION_NOTICE]
            ),
        )
        .order_by(ManagementAgreement.start_date.desc())
        .limit(1)
    )


# ------------------------------------------------------------------ creation


def _end_date(start: date, term_months: int) -> date | None:
    """None for an open-ended agreement (`term_months` of 0)."""
    if term_months <= 0:
        return None
    total = start.year * 12 + (start.month - 1) + term_months
    year, month = divmod(total, 12)
    # Clamp into a short month rather than rolling into the next one: a
    # 6-month term from 31 August ends on 28 February, not 3 March.
    day = min(start.day, [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month])
    try:
        return date(year, month + 1, day)
    except ValueError:
        return date(year, month + 1, 28)


async def create(
    db: AsyncSession,
    context: OrgContext,
    *,
    owner_profile_id: uuid.UUID,
    start_date: date,
    term_months: int = 12,
    notice_period_days: int = 90,
    scope_of_management: str | None = None,
    property_ids: list[uuid.UUID] | None = None,
    management_fee_percent: Decimal | None = None,
    disbursement_day: int | None = None,
    maintenance_auto_approve_limit: Decimal | None = None,
    maintenance_notify_limit: Decimal | None = None,
    request: Request | None = None,
) -> ManagementAgreement:
    """Draft an agreement from the owner profile's current terms.

    Any term passed explicitly overrides the profile's; anything omitted is
    copied from it. That is what makes the common case one field — the start
    date — while still allowing an agency to agree something different with
    one client without first editing their profile.
    """
    if context.organization.operating_mode != OperatingMode.AGENCY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Management agreements exist between an agency and its owner clients",
        )

    owner = assert_in_org(await db.get(OwnerProfile, owner_profile_id), context, label="owner profile")

    existing = await current_for_owner(db, context.organization_id, owner.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{owner.full_name} already has a live agreement ({existing.reference_code}). "
                "Terminate it before starting a new one."
            ),
        )
    if notice_period_days < MIN_NOTICE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The notice period must be at least {MIN_NOTICE_DAYS} days",
        )

    scoped_ids = [str(pid) for pid in (property_ids or [])]
    if scoped_ids:
        owned = await db.scalars(
            select(Property.id).where(
                Property.organization_id == context.organization_id,
                Property.owner_profile_id == owner.id,
            )
        )
        owned_ids = {str(pid) for pid in owned}
        stray = [pid for pid in scoped_ids if pid not in owned_ids]
        if stray:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Every property on the agreement must belong to this owner",
            )

    reference = await reference_service.generate_reference(
        db, ManagementAgreement, context.organization_id, "MGT"
    )
    agreement = ManagementAgreement(
        organization_id=context.organization_id,
        reference_code=reference,
        owner_profile_id=owner.id,
        status=ManagementAgreementStatus.DRAFT,
        management_fee_percent=(
            management_fee_percent
            if management_fee_percent is not None
            else Decimal(owner.management_fee_percent)
        ),
        disbursement_day=disbursement_day if disbursement_day is not None else owner.disbursement_day,
        maintenance_auto_approve_limit=(
            maintenance_auto_approve_limit
            if maintenance_auto_approve_limit is not None
            else Decimal(owner.maintenance_auto_approve_limit)
        ),
        maintenance_notify_limit=(
            maintenance_notify_limit
            if maintenance_notify_limit is not None
            else Decimal(owner.maintenance_notify_limit)
        ),
        scope_of_management=scope_of_management,
        property_ids=scoped_ids,
        start_date=start_date,
        term_months=term_months,
        end_date=_end_date(start_date, term_months),
        notice_period_days=notice_period_days,
        created_by_id=context.user.id,
    )
    db.add(agreement)
    await db.flush()

    agreement.document_id = await _render_document(db, context.organization, agreement, owner)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="management_agreement.created",
        entity_type="management_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=(
            f"Drafted management agreement {reference} for {owner.full_name} at "
            f"{agreement.management_fee_percent}%"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


async def _render_document(
    db: AsyncSession,
    organization: Organization,
    agreement: ManagementAgreement,
    owner: OwnerProfile,
) -> uuid.UUID:
    """Render the contract PDF and file it as a stored document."""
    query = select(Property).where(
        Property.organization_id == organization.id, Property.owner_profile_id == owner.id
    )
    if agreement.property_ids:
        query = query.where(Property.id.in_([uuid.UUID(pid) for pid in agreement.property_ids]))
    properties = list(await db.scalars(query.order_by(Property.name)))

    unit_counts: dict[uuid.UUID, int] = {}
    if properties:
        rows = await db.execute(
            select(Unit.property_id, func.count(Unit.id))
            .where(Unit.property_id.in_([p.id for p in properties]), Unit.is_archived.is_(False))
            .group_by(Unit.property_id)
        )
        unit_counts = {property_id: count for property_id, count in rows}

    owner_signature = (
        await db.get(DigitalSignature, agreement.owner_signature_id) if agreement.owner_signature_id else None
    )
    agency_signature = (
        await db.get(DigitalSignature, agreement.agency_signature_id)
        if agreement.agency_signature_id
        else None
    )

    pdf_bytes = pdf_service.render_pdf(
        "management_agreement.html",
        {
            "agreement": agreement,
            "owner": owner,
            "agency": {
                "name": organization.legal_name or organization.name,
                "address": organization.address,
                "kra_pin": organization.kra_pin,
            },
            "properties": [
                {
                    "name": prop.name,
                    "address": prop.address,
                    "county": prop.county,
                    "unit_count": unit_counts.get(prop.id, 0),
                }
                for prop in properties
            ],
            "generated_at": date.today(),
            "owner_signed_at": owner_signature.signed_at if owner_signature else None,
            "agency_signed_at": agency_signature.signed_at if agency_signature else None,
            "organization": organization,
        },
    )
    return await storage_service.store_bytes(
        db,
        data=pdf_bytes,
        filename=f"management-agreement-{agreement.reference_code}.pdf",
        content_type="application/pdf",
        category=FileCategory.MANAGEMENT_AGREEMENT,
        organization_id=organization.id,
        entity_type="management_agreement",
        entity_id=agreement.id,
    )


# ------------------------------------------------------------ dual signing


async def send_for_signature(
    db: AsyncSession,
    context: OrgContext,
    agreement_id: uuid.UUID,
    *,
    agency_signatory_name: str,
    agency_signatory_phone: str,
    request: Request | None = None,
) -> ManagementAgreement:
    """Raise one signing request per party and move the agreement to pending.

    Two separate OTP-verified signatures over the same document, each sent to
    a different phone. Neither party can sign for the other, and the agreement
    is not in force until both have — which is what `activate_if_fully_signed`
    enforces on the way back in.
    """
    # Imported lazily to break a cyclic import: signature_service is called
    # from several services like this one, and itself calls webhook_service,
    # which is in turn called from the scheduler that runs some of them.
    from app.services import signature_service

    agreement = await get(db, context, agreement_id)
    if agreement.status not in (
        ManagementAgreementStatus.DRAFT,
        ManagementAgreementStatus.PENDING_SIGNATURES,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agreement that is {agreement.status.value} cannot be sent for signature",
        )
    if agreement.document_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The agreement document has not been generated"
        )

    owner = await db.get(OwnerProfile, agreement.owner_profile_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner profile not found")

    if agreement.owner_signature_id is None:
        owner_signature, _ = await signature_service.create_signing_request(
            db,
            organization_id=context.organization_id,
            document_id=agreement.document_id,
            tenancy_id=None,
            signer_name=owner.full_name,
            signer_phone=owner.phone_number,
            signer_role="owner",
            document_label="property management agreement",
        )
        agreement.owner_signature_id = owner_signature.id
        # `create_signing_request` commits, so the link is already out to the
        # owner. Commit the back-reference before raising the second one, or a
        # failure there would leave a live signing link nothing points at and
        # a retry would send the owner a second one.
        await db.commit()

    if agreement.agency_signature_id is None:
        agency_signature, _ = await signature_service.create_signing_request(
            db,
            organization_id=context.organization_id,
            document_id=agreement.document_id,
            tenancy_id=None,
            signer_name=agency_signatory_name,
            signer_phone=agency_signatory_phone,
            signer_role="agency",
            document_label="property management agreement",
        )
        agreement.agency_signature_id = agency_signature.id
        await db.commit()

    agreement.status = ManagementAgreementStatus.PENDING_SIGNATURES

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="management_agreement.sent_for_signature",
        entity_type="management_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=(
            f"Sent {agreement.reference_code} to {owner.full_name} and "
            f"{agency_signatory_name} for signature"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


async def activate_if_fully_signed(db: AsyncSession, signature: DigitalSignature) -> None:
    """Called after any signature completes; activates once both are in.

    Hooked off `signature_service.verify_otp_and_sign` rather than polled,
    because the moment an agreement becomes binding is exactly when both
    parties should be told. Deliberately tolerant: a signature that belongs to
    a lease, or to an agreement already active, is a no-op.
    """
    agreement = await db.scalar(
        select(ManagementAgreement).where(
            ManagementAgreement.organization_id == signature.organization_id,
            ManagementAgreement.status == ManagementAgreementStatus.PENDING_SIGNATURES,
            ManagementAgreement.document_id == signature.document_id,
        )
    )
    if agreement is None:
        return

    signed_ids = set(
        await db.scalars(
            select(DigitalSignature.id).where(
                DigitalSignature.id.in_(
                    [
                        sid
                        for sid in (agreement.owner_signature_id, agreement.agency_signature_id)
                        if sid is not None
                    ]
                ),
                DigitalSignature.status == SignatureStatus.SIGNED,
            )
        )
    )
    if not (agreement.owner_signature_id in signed_ids and agreement.agency_signature_id in signed_ids):
        return

    agreement.status = ManagementAgreementStatus.ACTIVE
    agreement.activated_at = datetime.now(UTC)

    owner = await db.get(OwnerProfile, agreement.owner_profile_id)
    organization = await db.get(Organization, agreement.organization_id)
    if owner is not None and organization is not None:
        # Re-render so the filed copy carries both signing dates on its face.
        agreement.document_id = await _render_document(db, organization, agreement, owner)
        await _notify_parties(
            db,
            agreement,
            owner,
            title="Management agreement now in force",
            body=(
                f"The management agreement {agreement.reference_code} between {organization.name} "
                f"and {owner.full_name} has been signed by both parties and takes effect from "
                f"{agreement.start_date.strftime('%d %b %Y')}."
            ),
        )

    audit_service.record(
        db,
        organization_id=agreement.organization_id,
        action="management_agreement.activated",
        entity_type="management_agreement",
        entity_id=agreement.id,
        summary=f"Management agreement {agreement.reference_code} signed by both parties",
    )


# ------------------------------------------------------------- termination


async def request_termination(
    db: AsyncSession,
    context: OrgContext,
    agreement_id: uuid.UUID,
    *,
    requested_by: TerminationParty,
    reason: str | None = None,
    effective_date: date | None = None,
    request: Request | None = None,
) -> ManagementAgreement:
    """Serve notice. The agreement stays live until the effective date.

    An effective date earlier than the notice period is accepted only as an
    explicit shortening — both parties can agree to part sooner — but it is
    recorded as such, so a later dispute can see that the contractual notice
    was waived rather than missed.
    """
    agreement = await get(db, context, agreement_id)
    if agreement.status != ManagementAgreementStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only an active agreement can be terminated (this one is {agreement.status.value})",
        )

    today = date.today()
    contractual = today + timedelta(days=agreement.notice_period_days)
    effective = effective_date or contractual
    if effective < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The effective date cannot be in the past"
        )

    agreement.status = ManagementAgreementStatus.TERMINATION_NOTICE
    agreement.termination_requested_at = datetime.now(UTC)
    agreement.termination_requested_by = requested_by
    agreement.termination_requested_by_id = context.user.id
    agreement.termination_reason = reason
    agreement.termination_effective_date = effective

    owner = await db.get(OwnerProfile, agreement.owner_profile_id)
    shortened = effective < contractual
    note = " The parties have agreed to shorten the contractual notice period." if shortened else ""
    if owner is not None:
        await _notify_parties(
            db,
            agreement,
            owner,
            title="Management agreement termination notice",
            body=(
                f"Notice has been served by the {requested_by.value} to terminate management "
                f"agreement {agreement.reference_code}. Management continues until "
                f"{effective.strftime('%d %b %Y')}.{note}"
            ),
        )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="management_agreement.termination_requested",
        entity_type="management_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=(
            f"{requested_by.value.title()} served notice on {agreement.reference_code}, "
            f"effective {effective.isoformat()}"
        ),
        changes={
            "effective_date": effective.isoformat(),
            "contractual_date": contractual.isoformat(),
            "notice_shortened": shortened,
            "reason": reason,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


async def withdraw_termination(
    db: AsyncSession,
    context: OrgContext,
    agreement_id: uuid.UUID,
    *,
    request: Request | None = None,
) -> ManagementAgreement:
    """Take the notice back, while it is still running."""
    agreement = await get(db, context, agreement_id)
    if agreement.status != ManagementAgreementStatus.TERMINATION_NOTICE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This agreement has no notice running"
        )

    agreement.status = ManagementAgreementStatus.ACTIVE
    agreement.termination_requested_at = None
    agreement.termination_requested_by = None
    agreement.termination_requested_by_id = None
    agreement.termination_reason = None
    agreement.termination_effective_date = None

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="management_agreement.termination_withdrawn",
        entity_type="management_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=f"Termination notice on {agreement.reference_code} withdrawn",
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


async def complete_due_terminations(db: AsyncSession, *, today: date | None = None) -> int:
    """Close out agreements whose notice period has run. Returns how many.

    Run from the nightly sweep across every organisation, which is why it takes
    no `OrgContext` — like every other scheduled task in this codebase.
    """
    today = today or date.today()
    due = await db.scalars(
        select(ManagementAgreement).where(
            ManagementAgreement.status == ManagementAgreementStatus.TERMINATION_NOTICE,
            ManagementAgreement.termination_effective_date.is_not(None),
            ManagementAgreement.termination_effective_date <= today,
        )
    )

    completed = 0
    for agreement in due:
        agreement.status = ManagementAgreementStatus.TERMINATED
        agreement.terminated_at = datetime.now(UTC)
        owner = await db.get(OwnerProfile, agreement.owner_profile_id)
        if owner is not None:
            # The agency stops managing today, so the profile stops being the
            # live client relationship too. The row stays for its history.
            owner.is_active = False
            await _notify_parties(
                db,
                agreement,
                owner,
                title="Management agreement ended",
                body=(
                    f"Management agreement {agreement.reference_code} ended today. A final "
                    f"statement and handover pack should now be issued to {owner.full_name}."
                ),
            )
        audit_service.record(
            db,
            organization_id=agreement.organization_id,
            action="management_agreement.terminated",
            entity_type="management_agreement",
            entity_id=agreement.id,
            summary=f"Management agreement {agreement.reference_code} reached its termination date",
        )
        completed += 1

    # Separately, a fixed-term agreement that simply ran out.
    expired = await db.scalars(
        select(ManagementAgreement).where(
            ManagementAgreement.status == ManagementAgreementStatus.ACTIVE,
            ManagementAgreement.end_date.is_not(None),
            ManagementAgreement.end_date < today,
        )
    )
    for agreement in expired:
        agreement.status = ManagementAgreementStatus.EXPIRED
        audit_service.record(
            db,
            organization_id=agreement.organization_id,
            action="management_agreement.expired",
            entity_type="management_agreement",
            entity_id=agreement.id,
            summary=f"Management agreement {agreement.reference_code} reached the end of its term",
        )
        completed += 1

    await db.commit()
    return completed


# ---------------------------------------------------------------- notifying


async def _notify_parties(
    db: AsyncSession,
    agreement: ManagementAgreement,
    owner: OwnerProfile,
    *,
    title: str,
    body: str,
) -> None:
    """Tell the landlord client and the agency's own admins.

    The owner is reached on their phone whether or not they have a portal
    login — most owner clients never do — and the agency's admins in-app,
    where they are already working.
    """
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=owner.phone_number, organization_id=agreement.organization_id
        ),
        notification_type=NotificationType.MANAGEMENT_AGREEMENT,
        title=title,
        body=body,
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="management_agreement",
        entity_id=agreement.id,
        organization_id=agreement.organization_id,
    )

    admins = await db.scalars(
        select(User).where(
            User.organization_id == agreement.organization_id,
            User.role.in_([UserRole.AGENCY_ADMIN, UserRole.OWNER]),
            User.is_active.is_(True),
        )
    )
    for admin in admins:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(admin),
            notification_type=NotificationType.MANAGEMENT_AGREEMENT,
            title=title,
            body=body,
            channels=[NotificationChannel.IN_APP],
            entity_type="management_agreement",
            entity_id=agreement.id,
            organization_id=agreement.organization_id,
        )
