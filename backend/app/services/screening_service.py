"""Creditworthiness scoring, guarantors and reference checks (US-065, US-066, US-068).

The score is deliberately simple arithmetic over things the landlord can see and
argue with, not a black box: four components, each with its own explanation
string, summed to 100. A decision made on a number nobody can explain is a
decision that cannot be defended when a rejected applicant asks why — and in
Kenya, where formal credit data on renters barely exists, the honest answer is
that this is a completeness-and-affordability check, not a credit score.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.application import (
    INCOME_RATIO_THRESHOLD,
    ApplicationStatus,
    EmploymentStatus,
    Guarantor,
    GuarantorStatus,
    ReferenceCheck,
    ReferenceStatus,
    TenantApplication,
)
from app.models.file import FileCategory
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.services import file_service, notification_service, pdf_service

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

LINK_VALIDITY_DAYS = 14

# The four components, and what each is worth. Affordability carries the most
# weight because it is the only one that predicts arrears directly.
WEIGHT_COMPLETENESS = 20
WEIGHT_AFFORDABILITY = 40
WEIGHT_GUARANTOR = 20
WEIGHT_REFERENCE = 20

# Traffic light thresholds (US-066).
GREEN_FROM = 70
AMBER_FROM = 40

# Employment types, and how much of the affordability score survives the risk
# that the income is irregular. A salary is verifiable; a hustle is not.
EMPLOYMENT_STABILITY: dict[EmploymentStatus, Decimal] = {
    EmploymentStatus.EMPLOYED: Decimal("1.00"),
    EmploymentStatus.BUSINESS_OWNER: Decimal("0.90"),
    EmploymentStatus.SELF_EMPLOYED: Decimal("0.80"),
    EmploymentStatus.RETIRED: Decimal("0.80"),
    EmploymentStatus.STUDENT: Decimal("0.50"),
    EmploymentStatus.UNEMPLOYED: Decimal("0.20"),
}

# The fields that make an application reviewable at all.
REQUIRED_FIELDS = (
    "full_name",
    "phone_number",
    "national_id",
    "current_address",
    "employer_name",
    "monthly_income",
    "id_document_id",
    "passport_photo_id",
)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def band(score: int) -> str:
    """The traffic light the review screen paints (US-066)."""
    if score >= GREEN_FROM:
        return "green"
    if score >= AMBER_FROM:
        return "amber"
    return "red"


def _completeness(application: TenantApplication) -> tuple[int, str]:
    present = [field for field in REQUIRED_FIELDS if getattr(application, field, None)]
    ratio = len(present) / len(REQUIRED_FIELDS)
    points = round(WEIGHT_COMPLETENESS * ratio)
    missing = len(REQUIRED_FIELDS) - len(present)
    return points, (
        "Every required field and document supplied"
        if not missing
        else f"{missing} of {len(REQUIRED_FIELDS)} required details still missing"
    )


def _affordability(application: TenantApplication, rent: Decimal) -> tuple[int, str, Decimal | None]:
    """Score the rent-to-income ratio, discounted by how stable the income is."""
    stability = EMPLOYMENT_STABILITY.get(application.employment_status, Decimal("0.50"))

    if not application.monthly_income or application.monthly_income <= ZERO:
        return 0, "No monthly income stated, so affordability cannot be assessed", None

    ratio = (Decimal(rent) / Decimal(application.monthly_income) * 100).quantize(Decimal("0.01"))

    # Full marks at or under the 30% threshold, tapering to nothing at 60% —
    # past which the rent is more than half of everything they earn.
    if ratio <= INCOME_RATIO_THRESHOLD:
        earned = Decimal(WEIGHT_AFFORDABILITY)
    elif ratio >= INCOME_RATIO_THRESHOLD * 2:
        earned = ZERO
    else:
        span = INCOME_RATIO_THRESHOLD
        earned = Decimal(WEIGHT_AFFORDABILITY) * (1 - (ratio - INCOME_RATIO_THRESHOLD) / span)

    points = int((earned * stability).to_integral_value())
    verdict = (
        f"Rent is {ratio}% of stated income"
        + (
            " — comfortably within the 30% guideline"
            if ratio <= INCOME_RATIO_THRESHOLD
            else f" — above the {INCOME_RATIO_THRESHOLD}% guideline"
        )
        + f" ({application.employment_status.value.replace('_', ' ')})"
    )
    return points, verdict, ratio


def _guarantor_points(guarantors: list[Guarantor]) -> tuple[int, str]:
    if not guarantors:
        return 0, "No guarantor named"
    acknowledged = [g for g in guarantors if g.status == GuarantorStatus.ACKNOWLEDGED]
    if any(g.status == GuarantorStatus.DECLINED for g in guarantors) and not acknowledged:
        return 0, "The named guarantor declined"
    if not acknowledged:
        # Named but unconfirmed is worth something — it is a real name and number
        # the landlord can call — but not the full weight of an acknowledgement.
        return WEIGHT_GUARANTOR // 2, f"{len(guarantors)} guarantor(s) named, none confirmed yet"
    signed = [g for g in acknowledged if g.signature_id is not None]
    if signed:
        return WEIGHT_GUARANTOR, f"{len(signed)} guarantor(s) confirmed and signed"
    return (
        WEIGHT_GUARANTOR - 4,
        f"{len(acknowledged)} guarantor(s) confirmed, guarantee not yet signed",
    )


def _reference_points(references: list[ReferenceCheck]) -> tuple[int, str]:
    if not references:
        return 0, "No previous landlord reference requested"
    if any(r.status == ReferenceStatus.NEGATIVE for r in references):
        return 0, "A previous landlord gave a negative reference"
    positive = [r for r in references if r.status == ReferenceStatus.POSITIVE]
    if positive:
        return WEIGHT_REFERENCE, f"{len(positive)} positive landlord reference(s)"
    if all(r.status == ReferenceStatus.NO_RESPONSE for r in references):
        return 0, "The previous landlord never responded"
    return WEIGHT_REFERENCE // 2, "Reference requested, awaiting a reply"


def calculate_score(application: TenantApplication, rent: Decimal) -> dict:
    """The whole assessment, as the review screen shows it (US-066)."""
    completeness, completeness_note = _completeness(application)
    affordability, affordability_note, ratio = _affordability(application, rent)
    guarantor, guarantor_note = _guarantor_points(list(application.guarantors))
    reference, reference_note = _reference_points(list(application.references))

    total = completeness + affordability + guarantor + reference

    return {
        "score": total,
        "band": band(total),
        "income_ratio": float(ratio) if ratio is not None else None,
        "income_ratio_exceeded": bool(ratio is not None and ratio > INCOME_RATIO_THRESHOLD),
        "employment_status": application.employment_status.value,
        "monthly_rent": float(rent),
        "components": [
            {
                "label": "Application completeness",
                "points": completeness,
                "max": WEIGHT_COMPLETENESS,
                "note": completeness_note,
            },
            {
                "label": "Affordability",
                "points": affordability,
                "max": WEIGHT_AFFORDABILITY,
                "note": affordability_note,
            },
            {
                "label": "Guarantor",
                "points": guarantor,
                "max": WEIGHT_GUARANTOR,
                "note": guarantor_note,
            },
            {
                "label": "Landlord reference",
                "points": reference,
                "max": WEIGHT_REFERENCE,
                "note": reference_note,
            },
        ],
    }


async def rescore(db: AsyncSession, application: TenantApplication) -> dict:
    """Recompute and persist the score. Called after anything that could move it."""
    unit = await db.get(Unit, application.unit_id)
    rent = Decimal(unit.monthly_rent) if unit else ZERO
    breakdown = calculate_score(application, rent)
    application.score = breakdown["score"]
    application.score_breakdown = breakdown
    return breakdown


# ------------------------------------------------------------------ guarantors


async def add_guarantor(
    db: AsyncSession,
    application: TenantApplication,
    *,
    full_name: str,
    relationship_to_applicant: str,
    phone_number: str,
    email: str | None = None,
    national_id: str | None = None,
    id_document_id: uuid.UUID | None = None,
    employer_name: str | None = None,
    occupation: str | None = None,
    monthly_income: Decimal | None = None,
) -> Guarantor:
    """Record a guarantor and ask them, over WhatsApp, to confirm they accept.

    Multiple guarantors are supported — a common arrangement is a parent plus an
    employer — and each one confirms independently.
    """
    raw_token = secrets.token_urlsafe(32)
    guarantor = Guarantor(
        organization_id=application.organization_id,
        application_id=application.id,
        full_name=full_name,
        relationship_to_applicant=relationship_to_applicant,
        phone_number=phone_number,
        email=email,
        national_id=national_id,
        id_document_id=id_document_id,
        employer_name=employer_name,
        occupation=occupation,
        monthly_income=monthly_income,
        status=GuarantorStatus.PENDING,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=LINK_VALIDITY_DAYS),
    )
    db.add(guarantor)
    await db.flush()

    await _send_guarantor_request(db, application, guarantor, raw_token)
    return guarantor


async def _send_guarantor_request(
    db: AsyncSession,
    application: TenantApplication,
    guarantor: Guarantor,
    raw_token: str,
) -> None:
    unit = await db.get(Unit, application.unit_id)
    link = f"{settings.FRONTEND_URL}/guarantee/{raw_token}"
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=guarantor.phone_number, organization_id=application.organization_id
        ),
        notification_type=NotificationType.GUARANTOR_REQUEST,
        title="You have been named as a guarantor",
        body=(
            f"Hi {guarantor.full_name}. {application.full_name} has applied to rent "
            f"unit {unit.unit_number if unit else ''} and named you as their guarantor "
            f"({guarantor.relationship_to_applicant}). Please confirm or decline here: {link} "
            f"The link is valid for {LINK_VALIDITY_DAYS} days."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="guarantor",
        entity_id=guarantor.id,
        organization_id=application.organization_id,
    )


async def send_guarantee_for_signing(db: AsyncSession, guarantor: Guarantor) -> Guarantor:
    """Render the deed of guarantee and put it through the same OTP-verified
    signing flow a lease uses (US-065).

    Only offered once the guarantor has acknowledged: asking someone to sign a
    deed before they have said yes gets the order of consent backwards.
    """
    # Imported lazily to break a cyclic import: signature_service itself calls
    # webhook_service, which is in turn called from the scheduler that runs
    # this module's own sweep_stale_references.
    from app.services import signature_service

    if guarantor.status != GuarantorStatus.ACKNOWLEDGED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The guarantor has to confirm before the guarantee can be signed",
        )
    if guarantor.signature_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This guarantee has already been signed"
        )

    application = await db.get(TenantApplication, guarantor.application_id)
    unit = await db.get(Unit, application.unit_id) if application else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, guarantor.organization_id)
    if not (application and unit and property_record and organization):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The application is missing its unit"
        )

    try:
        pdf_bytes = pdf_service.render_pdf(
            "guarantee.html",
            {
                "organization": organization,
                "logo_url": None,
                "application": application,
                "guarantor": guarantor,
                "unit": unit,
                "property": property_record,
                "generated_at": date.today(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Guarantee rendering failed for %s", application.reference_code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The guarantee document could not be generated. Try again shortly.",
        ) from exc

    document = await file_service.register_generated(
        db,
        guarantor.organization_id,
        data=pdf_bytes,
        filename=f"Guarantee-{application.reference_code}-{guarantor.full_name.replace(' ', '-')}.pdf",
        category=FileCategory.GUARANTEE,
        entity_type="guarantor",
        entity_id=guarantor.id,
    )
    guarantor.agreement_document_id = document.id
    await db.flush()

    signature, _ = await signature_service.create_signing_request(
        db,
        organization_id=guarantor.organization_id,
        document_id=document.id,
        tenancy_id=None,
        signer_name=guarantor.full_name,
        signer_phone=guarantor.phone_number,
        signer_role="guarantor",
    )
    guarantor.signature_id = signature.id

    if application is not None:
        await rescore(db, application)

    await db.commit()
    await db.refresh(guarantor)
    return guarantor


async def guarantor_by_token(db: AsyncSession, raw_token: str) -> Guarantor:
    guarantor = await db.scalar(select(Guarantor).where(Guarantor.token_hash == _hash_token(raw_token)))
    if guarantor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is not valid")
    if datetime.now(UTC) > guarantor.expires_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has expired")
    return guarantor


async def respond_as_guarantor(
    db: AsyncSession, raw_token: str, *, accepted: bool, reason: str | None = None
) -> Guarantor:
    guarantor = await guarantor_by_token(db, raw_token)
    if guarantor.status != GuarantorStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You have already {guarantor.status.value} this guarantee",
        )

    guarantor.status = GuarantorStatus.ACKNOWLEDGED if accepted else GuarantorStatus.DECLINED
    guarantor.acknowledged_at = datetime.now(UTC)
    if not accepted:
        guarantor.declined_reason = reason

    application = await db.get(TenantApplication, guarantor.application_id)
    if application is not None:
        await rescore(db, application)

    await db.commit()
    await db.refresh(guarantor)
    return guarantor


# ------------------------------------------------------------- reference checks


async def request_reference(
    db: AsyncSession,
    application: TenantApplication,
    *,
    landlord_name: str,
    landlord_phone: str,
    property_reference: str | None = None,
) -> ReferenceCheck:
    """Ask a previous landlord, over WhatsApp, whether this tenant was reliable."""
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    check = ReferenceCheck(
        organization_id=application.organization_id,
        application_id=application.id,
        landlord_name=landlord_name,
        landlord_phone=landlord_phone,
        property_reference=property_reference,
        status=ReferenceStatus.SENT,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(days=LINK_VALIDITY_DAYS),
        sent_at=now,
    )
    db.add(check)
    await db.flush()

    link = f"{settings.FRONTEND_URL}/reference/{raw_token}"
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=landlord_phone, organization_id=application.organization_id
        ),
        notification_type=NotificationType.REFERENCE_REQUEST,
        title="Reference request",
        body=(
            f"Hi {landlord_name}, you are listed as a previous landlord for "
            f"{application.full_name}, who has applied to rent from us. "
            f"Two quick questions — did they pay rent on time, and would you rent to "
            f"them again? Please answer here: {link} It takes under a minute."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="reference_check",
        entity_id=check.id,
        organization_id=application.organization_id,
    )
    return check


async def reference_by_token(db: AsyncSession, raw_token: str) -> ReferenceCheck:
    check = await db.scalar(select(ReferenceCheck).where(ReferenceCheck.token_hash == _hash_token(raw_token)))
    if check is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is not valid")
    if datetime.now(UTC) > check.expires_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has expired")
    return check


async def record_reference_response(
    db: AsyncSession,
    raw_token: str,
    *,
    paid_on_time: bool,
    would_rent_again: bool,
    note: str | None = None,
) -> ReferenceCheck:
    check = await reference_by_token(db, raw_token)
    if check.status != ReferenceStatus.SENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This reference has already been answered"
        )

    # Either answer being "no" makes the whole reference negative: a landlord who
    # would not take them back is saying something even if the rent did arrive.
    positive = paid_on_time and would_rent_again
    check.status = ReferenceStatus.POSITIVE if positive else ReferenceStatus.NEGATIVE
    check.paid_on_time = paid_on_time
    check.would_rent_again = would_rent_again
    check.response_note = note
    check.responded_at = datetime.now(UTC)

    application = await db.get(TenantApplication, check.application_id)
    if application is not None:
        await rescore(db, application)
        await _alert_on_negative_reference(db, application, check)

    await db.commit()
    await db.refresh(check)
    return check


async def _alert_on_negative_reference(
    db: AsyncSession, application: TenantApplication, check: ReferenceCheck
) -> None:
    """A bad reference is the one screening result nobody should have to go
    looking for, so it is pushed rather than waiting to be noticed."""
    if check.status != ReferenceStatus.NEGATIVE:
        return

    from app.models.user import User, UserRole

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
            notification_type=NotificationType.REFERENCE_REQUEST,
            title="Negative landlord reference",
            body=(
                f"{check.landlord_name} gave a negative reference for applicant "
                f"{application.full_name} ({application.reference_code}): "
                f"paid on time — {'yes' if check.paid_on_time else 'no'}, "
                f"would rent again — {'yes' if check.would_rent_again else 'no'}."
                + (f" Note: {check.response_note}" if check.response_note else "")
            ),
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
            link_path=f"/applications/{application.id}",
            entity_type="tenant_application",
            entity_id=application.id,
        )


async def sweep_stale_references(db: AsyncSession, *, after_days: int = 5) -> int:
    """Mark references nobody answered, so the score stops crediting a maybe."""
    cutoff = datetime.now(UTC) - timedelta(days=after_days)
    rows = list(
        await db.scalars(
            select(ReferenceCheck).where(
                ReferenceCheck.status == ReferenceStatus.SENT,
                ReferenceCheck.sent_at < cutoff,
            )
        )
    )
    for check in rows:
        check.status = ReferenceStatus.NO_RESPONSE
        application = await db.get(TenantApplication, check.application_id)
        if application is not None and application.status in (
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.INTERVIEW_SCHEDULED,
        ):
            await rescore(db, application)

    if rows:
        await db.commit()
    return len(rows)
