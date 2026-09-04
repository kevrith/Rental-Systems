"""Lease renewal automation — Phase 2 (US-057).

A tenancy approaching its end date gets a concrete offer rather than a reminder:
an agreement generated on the landlord's configured terms, sent to the tenant on
WhatsApp with a signing link, and answerable with one tap.

The design keeps three things separate:

  * the *offer* (this module) — terms, deadline, and the tenant's answer;
  * the *signature* (`signature_service`) — OTP-verified assent to the document;
  * the *tenancy* — only mutated when an offer is accepted.

An offer is answerable by a public, unauthenticated link, so the token is
single-use, hashed at rest, and expires. Accepting extends the tenancy in place;
declining flips it to NOTICE_GIVEN so the existing move-out workflow takes over.
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

from app.api.deps import OrgContext, assert_in_org
from app.core.config import settings
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.models.renewal import LeaseRenewal, RenewalStatus
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import User, UserRole
from app.services import (
    audit_service,
    file_service,
    notification_service,
    pdf_service,
    reference_service,
)

logger = logging.getLogger("rentflow.renewal")

# An offer is generated 30 days out and chased at 14, which leaves the tenant a
# clear fortnight to answer before anyone escalates.
OFFER_DAYS_BEFORE_EXPIRY = 30
ESCALATE_DAYS_BEFORE_EXPIRY = 14
LINK_VALIDITY_DAYS = 45


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _add_months(anchor: date, months: int) -> date:
    """Calendar month arithmetic, clamped so 31 Jan + 1 month is 28/29 Feb."""
    total = anchor.year * 12 + (anchor.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    if month == 12:
        last_day = 31
    else:
        last_day = (date(year if month < 12 else year + 1, month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(anchor.day, last_day))


def proposed_terms(tenancy: Tenancy, organization: Organization) -> dict:
    """What the landlord's configured defaults imply for this tenancy."""
    increase = Decimal(organization.renewal_rent_increase_percent or 0)
    current = Decimal(tenancy.monthly_rent)
    proposed = (current * (Decimal("100") + increase) / Decimal("100")).quantize(Decimal("0.01"))
    term_months = int(organization.renewal_term_months or 12)

    # The new term starts the day after the current one ends, so there is no gap
    # in occupation and no day the tenant is in the unit without an agreement.
    start = (tenancy.end_date or date.today()) + timedelta(days=1)
    return {
        "current_rent": current,
        "proposed_rent": proposed,
        "rent_increase_percent": increase,
        "term_months": term_months,
        "new_start_date": start,
        "new_end_date": _add_months(start, term_months) - timedelta(days=1),
    }


# ----------------------------------------------------------------- creating an offer


async def create_offer(
    db: AsyncSession,
    tenancy: Tenancy,
    *,
    proposed_rent: Decimal | None = None,
    term_months: int | None = None,
    notify: bool = True,
    actor: User | None = None,
) -> LeaseRenewal:
    """Generate a renewal agreement and offer it to the tenant.

    Returns the existing open offer rather than creating a second one — the
    nightly sweep and a manager pressing the button must not race into two.
    """
    if tenancy.is_open_ended or tenancy.end_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An open-ended tenancy has no end date to renew",
        )

    existing = await db.scalar(
        select(LeaseRenewal).where(
            LeaseRenewal.tenancy_id == tenancy.id,
            LeaseRenewal.status == RenewalStatus.OFFERED,
        )
    )
    if existing is not None:
        return existing

    organization = await db.get(Organization, tenancy.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organisation not found")

    terms = proposed_terms(tenancy, organization)
    if proposed_rent is not None:
        terms["proposed_rent"] = Decimal(proposed_rent)
        current = terms["current_rent"]
        terms["rent_increase_percent"] = (
            ((Decimal(proposed_rent) - current) / current * Decimal("100")).quantize(Decimal("0.01"))
            if current > 0
            else Decimal("0.00")
        )
    if term_months is not None:
        terms["term_months"] = term_months
        terms["new_end_date"] = _add_months(terms["new_start_date"], term_months) - timedelta(days=1)

    raw_token = secrets.token_urlsafe(32)
    code = await reference_service.generate_reference(db, LeaseRenewal, tenancy.organization_id, "RNW")
    renewal = LeaseRenewal(
        organization_id=tenancy.organization_id,
        reference_code=code,
        tenancy_id=tenancy.id,
        current_rent=terms["current_rent"],
        proposed_rent=terms["proposed_rent"],
        rent_increase_percent=terms["rent_increase_percent"],
        term_months=terms["term_months"],
        new_start_date=terms["new_start_date"],
        new_end_date=terms["new_end_date"],
        status=RenewalStatus.OFFERED,
        respond_by=tenancy.end_date - timedelta(days=ESCALATE_DAYS_BEFORE_EXPIRY),
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=LINK_VALIDITY_DAYS),
    )
    db.add(renewal)
    await db.flush()

    document = await _render_agreement(db, renewal, tenancy)
    if document is not None:
        renewal.document_id = document.id

    audit_service.record(
        db,
        organization_id=tenancy.organization_id,
        action="renewal.offered",
        entity_type="tenancy",
        entity_id=tenancy.id,
        actor=actor,
        summary=(
            f"Renewal {code} offered: KES {pdf_service.format_kes(terms['current_rent'])} → "
            f"KES {pdf_service.format_kes(terms['proposed_rent'])} for "
            f"{terms['term_months']} months"
        ),
    )

    if notify:
        await _notify_offer(db, renewal, tenancy, raw_token, document)

    return renewal


async def _render_agreement(db: AsyncSession, renewal: LeaseRenewal, tenancy: Tenancy) -> StoredFile | None:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, tenancy.organization_id)
    if not (tenant and unit and property_record and organization):
        return None

    try:
        pdf_bytes = pdf_service.render_pdf(
            "lease_renewal.html",
            {
                "organization": organization,
                "logo_url": None,
                "renewal": renewal,
                "tenancy": tenancy,
                "tenant": tenant,
                "unit": unit,
                "property": property_record,
                "generated_at": date.today(),
            },
        )
    except Exception:  # noqa: BLE001 — the offer itself stands without the PDF
        logger.exception("Renewal agreement rendering failed for %s", renewal.reference_code)
        return None

    return await file_service.register_generated(
        db,
        tenancy.organization_id,
        data=pdf_bytes,
        filename=f"Renewal-{renewal.reference_code}.pdf",
        category=FileCategory.RENEWAL_AGREEMENT,
        entity_type="tenant",
        entity_id=tenant.id,
    )


async def _notify_offer(
    db: AsyncSession,
    renewal: LeaseRenewal,
    tenancy: Tenancy,
    raw_token: str,
    document: StoredFile | None,
) -> None:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    if tenant is None:
        return

    link = f"{settings.FRONTEND_URL}/renew/{raw_token}"
    change = (
        f"Rent stays at KES {pdf_service.format_kes(renewal.current_rent)}."
        if Decimal(renewal.proposed_rent) == Decimal(renewal.current_rent)
        else (
            f"Rent changes from KES {pdf_service.format_kes(renewal.current_rent)} to "
            f"KES {pdf_service.format_kes(renewal.proposed_rent)}."
        )
    )

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.LEASE_RENEWAL,
        title="Your lease renewal is ready",
        body=(
            f"Dear {tenant.full_name.split()[0]}, your lease for unit "
            f"{unit.unit_number if unit else 'your unit'} ends on "
            f"{tenancy.end_date:%d %b %Y}. {change} "
            f"The new term runs to {renewal.new_end_date:%d %b %Y}. "
            f"Accept or decline by {renewal.respond_by:%d %b %Y}: {link}"
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        attachment=(
            notification_service.Attachment(url=file_service.to_url(document), filename=document.filename)
            if document
            else None
        ),
        entity_type="tenancy",
        entity_id=tenancy.id,
        organization_id=tenancy.organization_id,
    )


# ----------------------------------------------------------------- the tenant's answer


async def get_by_token(db: AsyncSession, raw_token: str) -> LeaseRenewal:
    renewal = await db.scalar(select(LeaseRenewal).where(LeaseRenewal.token_hash == _hash_token(raw_token)))
    if renewal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Renewal link not found")
    if datetime.now(UTC) > renewal.expires_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This renewal link has expired")
    if renewal.status != RenewalStatus.OFFERED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This renewal has already been {renewal.status.value}",
        )
    return renewal


async def describe(db: AsyncSession, renewal: LeaseRenewal) -> dict:
    """What the public renewal page shows. No ids that are not already the token's."""
    tenancy = await db.get(Tenancy, renewal.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, renewal.organization_id)
    document = await db.get(StoredFile, renewal.document_id) if renewal.document_id else None

    return {
        "reference_code": renewal.reference_code,
        "status": renewal.status.value,
        "tenant_name": tenant.full_name if tenant else None,
        "landlord_name": ((organization.legal_name or organization.name) if organization else None),
        "unit_number": unit.unit_number if unit else None,
        "property_name": property_record.name if property_record else None,
        "current_rent": str(renewal.current_rent),
        "proposed_rent": str(renewal.proposed_rent),
        "rent_increase_percent": str(renewal.rent_increase_percent),
        "term_months": renewal.term_months,
        "current_end_date": tenancy.end_date.isoformat() if tenancy and tenancy.end_date else None,
        "new_start_date": renewal.new_start_date.isoformat(),
        "new_end_date": renewal.new_end_date.isoformat(),
        "respond_by": renewal.respond_by.isoformat(),
        "agreement_url": file_service.to_url(document) if document else None,
    }


async def accept(db: AsyncSession, raw_token: str) -> LeaseRenewal:
    """The tenant accepts: extend the tenancy in place on the offered terms."""
    renewal = await get_by_token(db, raw_token)
    tenancy = await db.get(Tenancy, renewal.tenancy_id)
    if tenancy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenancy not found")

    renewal.status = RenewalStatus.ACCEPTED
    renewal.responded_at = datetime.now(UTC)

    tenancy.monthly_rent = Decimal(renewal.proposed_rent)
    tenancy.end_date = renewal.new_end_date
    tenancy.status = TenancyStatus.ACTIVE

    audit_service.record(
        db,
        organization_id=renewal.organization_id,
        action="renewal.accepted",
        entity_type="tenancy",
        entity_id=tenancy.id,
        summary=(
            f"Tenant accepted renewal {renewal.reference_code}; tenancy now runs to "
            f"{renewal.new_end_date:%d %b %Y} at KES "
            f"{pdf_service.format_kes(renewal.proposed_rent)}"
        ),
    )
    await _notify_response(db, renewal, tenancy, accepted=True)
    await db.commit()
    await db.refresh(renewal)
    return renewal


async def decline(db: AsyncSession, raw_token: str, reason: str | None = None) -> LeaseRenewal:
    """The tenant declines: the tenancy ends as scheduled and move-out begins."""
    renewal = await get_by_token(db, raw_token)
    tenancy = await db.get(Tenancy, renewal.tenancy_id)
    if tenancy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenancy not found")

    renewal.status = RenewalStatus.DECLINED
    renewal.responded_at = datetime.now(UTC)
    renewal.decline_reason = (reason or "")[:2000] or None

    # NOTICE_GIVEN is what the move-out workflow already keys off, so declining a
    # renewal drops the tenancy straight into it rather than inventing a state.
    tenancy.status = TenancyStatus.NOTICE_GIVEN
    tenancy.notice_given_at = datetime.now(UTC)
    tenancy.move_out_date = tenancy.end_date

    audit_service.record(
        db,
        organization_id=renewal.organization_id,
        action="renewal.declined",
        entity_type="tenancy",
        entity_id=tenancy.id,
        summary=(
            f"Tenant declined renewal {renewal.reference_code}; tenancy ends "
            f"{tenancy.end_date:%d %b %Y}" + (f" — {reason}" if reason else "")
        ),
    )
    await _notify_response(db, renewal, tenancy, accepted=False)
    await db.commit()
    await db.refresh(renewal)
    return renewal


async def _notify_response(
    db: AsyncSession, renewal: LeaseRenewal, tenancy: Tenancy, *, accepted: bool
) -> None:
    unit = await db.get(Unit, tenancy.unit_id)
    tenant = await db.get(Tenant, tenancy.tenant_id)
    where = f"unit {unit.unit_number}" if unit else "a unit"
    who = tenant.full_name if tenant else "The tenant"

    recipients = await db.scalars(
        select(User).where(
            User.organization_id == renewal.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
            User.is_active.is_(True),
        )
    )
    for user in recipients:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(user),
            notification_type=NotificationType.LEASE_RENEWAL,
            title="Renewal accepted" if accepted else "Renewal declined",
            body=(
                f"{who} has accepted the renewal for {where}. The tenancy now runs to "
                f"{renewal.new_end_date:%d %b %Y} at KES "
                f"{pdf_service.format_kes(renewal.proposed_rent)}."
                if accepted
                else (
                    f"{who} has declined the renewal for {where}. The tenancy ends on "
                    f"{tenancy.end_date:%d %b %Y} — arrange the move-out inspection."
                )
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.IN_APP],
            link_path=f"/tenancies/{tenancy.id}",
            entity_type="tenancy",
            entity_id=tenancy.id,
            organization_id=renewal.organization_id,
        )


# ----------------------------------------------------------------- management surface


async def list_renewals(
    db: AsyncSession, context: OrgContext, tenancy_id: uuid.UUID | None = None
) -> list[dict]:
    query = select(LeaseRenewal).where(LeaseRenewal.organization_id == context.organization_id)
    if tenancy_id:
        query = query.where(LeaseRenewal.tenancy_id == tenancy_id)
    rows = await db.scalars(query.order_by(LeaseRenewal.created_at.desc()))

    result = []
    for renewal in rows:
        tenancy = await db.get(Tenancy, renewal.tenancy_id)
        tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
        unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
        result.append(
            {
                "id": str(renewal.id),
                "reference_code": renewal.reference_code,
                "tenancy_id": str(renewal.tenancy_id),
                "tenant_name": tenant.full_name if tenant else None,
                "unit_number": unit.unit_number if unit else None,
                "status": renewal.status.value,
                "current_rent": str(renewal.current_rent),
                "proposed_rent": str(renewal.proposed_rent),
                "rent_increase_percent": str(renewal.rent_increase_percent),
                "new_start_date": renewal.new_start_date.isoformat(),
                "new_end_date": renewal.new_end_date.isoformat(),
                "respond_by": renewal.respond_by.isoformat(),
                "responded_at": renewal.responded_at.isoformat() if renewal.responded_at else None,
                "decline_reason": renewal.decline_reason,
                "escalated_at": renewal.escalated_at.isoformat() if renewal.escalated_at else None,
                "document_id": str(renewal.document_id) if renewal.document_id else None,
            }
        )
    return result


async def offer_for_tenancy(
    db: AsyncSession,
    context: OrgContext,
    tenancy_id: uuid.UUID,
    *,
    proposed_rent: Decimal | None = None,
    term_months: int | None = None,
) -> dict:
    """The manual path — a manager offering a renewal before the sweep would."""
    tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
    renewal = await create_offer(
        db,
        tenancy,
        proposed_rent=proposed_rent,
        term_months=term_months,
        actor=context.user,
    )
    await db.commit()
    await db.refresh(renewal)
    return (await list_renewals(db, context, tenancy_id))[0]


# ----------------------------------------------------------------- the nightly sweep


async def offer_due_renewals(db: AsyncSession) -> dict[str, int]:
    """Generate offers 30 days out, and escalate silence at 14 days (US-057)."""
    today = date.today()
    offered = 0
    escalated = 0

    offer_on = today + timedelta(days=OFFER_DAYS_BEFORE_EXPIRY)
    tenancies = list(
        await db.scalars(
            select(Tenancy).where(
                Tenancy.end_date == offer_on,
                Tenancy.is_open_ended.is_(False),
                Tenancy.status.in_([TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON]),
            )
        )
    )
    for tenancy in tenancies:
        organization = await db.get(Organization, tenancy.organization_id)
        if organization is None or not organization.auto_offer_renewals:
            continue
        try:
            await create_offer(db, tenancy)
            offered += 1
        except HTTPException:
            continue
        except Exception:  # noqa: BLE001 — one bad tenancy must not stop the sweep
            logger.exception("Renewal offer failed for tenancy %s", tenancy.id)
            await db.rollback()

    # Silence at the 14-day mark: tell the owner and the caretaker once.
    escalate_on = today + timedelta(days=ESCALATE_DAYS_BEFORE_EXPIRY)
    pending = list(
        await db.scalars(
            select(LeaseRenewal)
            .join(Tenancy, Tenancy.id == LeaseRenewal.tenancy_id)
            .where(
                LeaseRenewal.status == RenewalStatus.OFFERED,
                LeaseRenewal.escalated_at.is_(None),
                Tenancy.end_date <= escalate_on,
            )
        )
    )
    for renewal in pending:
        pending_tenancy = await db.get(Tenancy, renewal.tenancy_id)
        if pending_tenancy is None:
            continue
        await _escalate(db, renewal, pending_tenancy)
        renewal.escalated_at = datetime.now(UTC)
        escalated += 1

    await db.commit()
    logger.info("Offered %s renewal(s), escalated %s unanswered", offered, escalated)
    return {"offered": offered, "escalated": escalated}


async def _escalate(db: AsyncSession, renewal: LeaseRenewal, tenancy: Tenancy) -> None:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    unit = await db.get(Unit, tenancy.unit_id)
    where = f"unit {unit.unit_number}" if unit else "a unit"

    recipients = await db.scalars(
        select(User).where(
            User.organization_id == renewal.organization_id,
            User.role.in_(
                [
                    UserRole.OWNER,
                    UserRole.AGENCY_ADMIN,
                    UserRole.PROPERTY_MANAGER,
                    UserRole.CARETAKER,
                ]
            ),
            User.is_active.is_(True),
        )
    )
    for user in recipients:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(user),
            notification_type=NotificationType.LEASE_RENEWAL,
            title="Renewal unanswered — 14 days to expiry",
            body=(
                f"{tenant.full_name if tenant else 'The tenant'} in {where} has not answered "
                f"renewal {renewal.reference_code}. The lease ends on "
                f"{tenancy.end_date:%d %b %Y}. Call them, or start the move-out."
            ),
            channels=[NotificationChannel.WHATSAPP, NotificationChannel.PUSH],
            link_path=f"/tenancies/{tenancy.id}",
            entity_type="tenancy",
            entity_id=tenancy.id,
            organization_id=renewal.organization_id,
        )


async def lapse_expired_offers(db: AsyncSession) -> int:
    """Close out offers whose tenancy has now ended without an answer."""
    today = date.today()
    stale = list(
        await db.scalars(
            select(LeaseRenewal)
            .join(Tenancy, Tenancy.id == LeaseRenewal.tenancy_id)
            .where(LeaseRenewal.status == RenewalStatus.OFFERED, Tenancy.end_date < today)
        )
    )
    for renewal in stale:
        renewal.status = RenewalStatus.LAPSED
    await db.commit()
    return len(stale)
