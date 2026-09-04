"""Vacancy listings, the lead pipeline and vacancy cost (US-074, US-075).

The number this module exists to make visible is the one nobody tracks: what an
empty unit costs. Days vacant times the daily rent is money the owner did not
earn, and putting it next to the listing is the difference between "we'll get
round to it" and filling the unit.
"""

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.application import ApplicationStatus, TenantApplication
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, Unit, UnitStatus
from app.models.user import User, UserRole
from app.models.vacancy import (
    OPEN_LEAD_STAGES,
    Inquiry,
    LeadStage,
    ListingStatus,
    VacancyListing,
)
from app.services import audit_service, file_service, notification_service
from app.services.notifications import normalize_phone

ZERO = Decimal("0.00")

# Slugs are read aloud and retyped, so they avoid the characters that get
# misread — the same alphabet the reference codes use.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
STALE_LEAD_DAYS = 3


def _slug() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(10))


async def _unique_slug(db: AsyncSession) -> str:
    for _ in range(10):
        candidate = _slug()
        if not await db.scalar(select(VacancyListing.id).where(VacancyListing.slug == candidate)):
            return candidate
    raise RuntimeError("Could not allocate a unique listing slug")


async def ensure_listing(
    db: AsyncSession, context: OrgContext, unit: Unit, *, publish: bool = True
) -> VacancyListing:
    """Get this unit's listing, creating it the first time it is needed.

    Listings are created rather than pre-generated for every unit: a portfolio of
    2,000 units should not carry 2,000 dormant adverts.
    """
    listing = await db.scalar(select(VacancyListing).where(VacancyListing.unit_id == unit.id))
    if listing is not None:
        return listing

    listing = VacancyListing(
        organization_id=context.organization_id,
        unit_id=unit.id,
        slug=await _unique_slug(db),
        status=ListingStatus.PUBLISHED if publish else ListingStatus.DRAFT,
        vacant_since=unit.vacancy_date or date.today(),
        published_at=datetime.now(UTC) if publish else None,
    )
    db.add(listing)
    await db.flush()
    return listing


async def get_listing_for_unit(db: AsyncSession, context: OrgContext, unit_id: uuid.UUID) -> VacancyListing:
    unit = assert_in_org(await db.get(Unit, unit_id), context, label="unit")
    if unit.status == UnitStatus.OCCUPIED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This unit is occupied, so it has nothing to advertise",
        )
    listing = await ensure_listing(db, context, unit)
    await db.commit()
    await db.refresh(listing)
    return listing


async def update_listing(
    db: AsyncSession,
    context: OrgContext,
    listing_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> VacancyListing:
    listing = assert_in_org(await db.get(VacancyListing, listing_id), context, label="listing")
    fields = payload.model_dump(exclude_unset=True)

    was = listing.status
    for field, value in fields.items():
        setattr(listing, field, value)

    if listing.status == ListingStatus.PUBLISHED and listing.published_at is None:
        listing.published_at = datetime.now(UTC)
    if listing.status == ListingStatus.CLOSED and listing.closed_at is None:
        listing.closed_at = datetime.now(UTC)
    if was == ListingStatus.CLOSED and listing.status != ListingStatus.CLOSED:
        listing.closed_at = None

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="listing.updated",
        entity_type="vacancy_listing",
        entity_id=listing.id,
        actor=context.user,
        summary=f"Listing updated ({listing.status.value})",
        request=request,
    )
    await db.commit()
    await db.refresh(listing)
    return listing


async def rotate_slug(db: AsyncSession, context: OrgContext, listing_id: uuid.UUID) -> VacancyListing:
    """Replace an over-shared link. The old one stops resolving immediately."""
    listing = assert_in_org(await db.get(VacancyListing, listing_id), context, label="listing")
    listing.slug = await _unique_slug(db)
    await db.commit()
    await db.refresh(listing)
    return listing


async def close_listing_for_unit(db: AsyncSession, unit_id: uuid.UUID) -> None:
    """Called when a unit becomes occupied — the advert stops being true (US-074)."""
    listing = await db.scalar(select(VacancyListing).where(VacancyListing.unit_id == unit_id))
    if listing is None or listing.status == ListingStatus.CLOSED:
        return
    listing.status = ListingStatus.CLOSED
    listing.closed_at = datetime.now(UTC)


async def public_listing(db: AsyncSession, slug: str) -> dict:
    """What a stranger sees. No ids beyond what they need to apply."""
    listing = await db.scalar(select(VacancyListing).where(VacancyListing.slug == slug))
    if listing is None or listing.status != ListingStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This listing is no longer available"
        )

    unit = await db.get(Unit, listing.unit_id)
    if unit is None or unit.status == UnitStatus.OCCUPIED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This unit has already been let")
    property_record = await db.get(Property, unit.property_id)

    listing.view_count += 1
    await db.commit()

    photos = await file_service.list_for_entity(db, unit.organization_id, "unit", unit.id)
    property_photos = (
        await file_service.list_for_entity(db, unit.organization_id, "property", property_record.id)
        if property_record
        else []
    )

    return {
        "slug": listing.slug,
        "unit_id": str(unit.id),
        "unit_number": unit.unit_number,
        "unit_type": unit.unit_type,
        "bedrooms": unit.bedrooms,
        "bathrooms": unit.bathrooms,
        "size_sqm": unit.size_sqm,
        "features": list(unit.features),
        "monthly_rent": float(unit.monthly_rent),
        "deposit_amount": float(unit.deposit_amount),
        "headline": listing.headline,
        "description": listing.description or (property_record.description if property_record else None),
        "property_name": property_record.name if property_record else "",
        "property_address": property_record.address if property_record else "",
        "county": property_record.county if property_record else None,
        "latitude": property_record.latitude if property_record else None,
        "longitude": property_record.longitude if property_record else None,
        "amenities": list(property_record.amenities) if property_record else [],
        "contact_name": listing.contact_name,
        "contact_phone": listing.contact_phone,
        "photo_urls": [file_service.to_url(photo) for photo in (photos or property_photos)],
    }


# ---------------------------------------------------------------------- leads


async def capture_inquiry(
    db: AsyncSession, slug: str, *, full_name: str, phone_number: str, email: str | None, message: str | None
) -> Inquiry:
    """Someone asked about the unit from the public listing (US-075)."""
    listing = await db.scalar(select(VacancyListing).where(VacancyListing.slug == slug))
    if listing is None or listing.status != ListingStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This listing is no longer available"
        )

    phone = normalize_phone(phone_number)
    existing = await db.scalar(
        select(Inquiry).where(
            Inquiry.listing_id == listing.id,
            Inquiry.phone_number == phone,
            Inquiry.stage.in_(OPEN_LEAD_STAGES),
        )
    )
    if existing is not None:
        # Asking twice is enthusiasm, not a new lead. Refresh the contact time so
        # the follow-up sweep does not chase them for something they just did.
        existing.last_contacted_at = datetime.now(UTC)
        if message:
            existing.message = message
        await db.commit()
        await db.refresh(existing)
        return existing

    inquiry = Inquiry(
        organization_id=listing.organization_id,
        listing_id=listing.id,
        unit_id=listing.unit_id,
        full_name=full_name,
        phone_number=phone,
        email=email,
        message=message,
        stage=LeadStage.INQUIRED,
    )
    db.add(inquiry)
    await db.flush()

    await _confirm_inquiry(db, listing, inquiry)
    await _alert_managers(db, listing, inquiry)
    await db.commit()
    await db.refresh(inquiry)
    return inquiry


async def _confirm_inquiry(db: AsyncSession, listing: VacancyListing, inquiry: Inquiry) -> None:
    unit = await db.get(Unit, listing.unit_id)
    property_record = await db.get(Property, unit.property_id) if unit else None
    apply_link = f"{_frontend()}/apply/{listing.unit_id}"

    await notification_service.send(
        db,
        recipient=notification_service.Recipient(
            phone_number=inquiry.phone_number, organization_id=listing.organization_id
        ),
        notification_type=NotificationType.INQUIRY_RECEIVED,
        title="Thanks for your interest",
        body=(
            f"Hi {inquiry.full_name}, thanks for asking about unit "
            f"{unit.unit_number if unit else ''} at "
            f"{property_record.name if property_record else 'our property'}. "
            f"Someone will call you shortly. If you would like to get ahead, you can apply "
            f"here: {apply_link}"
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        entity_type="inquiry",
        entity_id=inquiry.id,
        organization_id=listing.organization_id,
    )


async def _alert_managers(db: AsyncSession, listing: VacancyListing, inquiry: Inquiry) -> None:
    unit = await db.get(Unit, listing.unit_id)
    managers = await db.scalars(
        select(User).where(
            User.organization_id == listing.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
            User.is_active.is_(True),
        )
    )
    for manager in managers:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(manager),
            notification_type=NotificationType.INQUIRY_RECEIVED,
            title="New enquiry on a vacancy",
            body=(
                f"{inquiry.full_name} ({inquiry.phone_number}) asked about unit "
                f"{unit.unit_number if unit else ''}." + (f' "{inquiry.message}"' if inquiry.message else "")
            ),
            channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
            link_path=f"/vacancies/{listing.unit_id}",
            entity_type="inquiry",
            entity_id=inquiry.id,
        )


def _frontend() -> str:
    from app.core.config import settings

    return settings.FRONTEND_URL


async def list_inquiries(
    db: AsyncSession,
    context: OrgContext,
    *,
    unit_id: uuid.UUID | None = None,
    stage: LeadStage | None = None,
    stale_only: bool = False,
    limit: int = 200,
) -> list[Inquiry]:
    query = select(Inquiry).where(Inquiry.organization_id == context.organization_id)

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Inquiry.unit_id.in_(select(Unit.id).where(Unit.property_id.in_(allowed))))
    if unit_id:
        query = query.where(Inquiry.unit_id == unit_id)
    if stage:
        query = query.where(Inquiry.stage == stage)

    rows = list(await db.scalars(query.order_by(Inquiry.created_at.desc()).limit(limit)))
    return [row for row in rows if row.is_stale] if stale_only else rows


async def update_inquiry(
    db: AsyncSession,
    context: OrgContext,
    inquiry_id: uuid.UUID,
    *,
    stage: LeadStage | None = None,
    notes: str | None = None,
    mark_contacted: bool = False,
) -> Inquiry:
    inquiry = assert_in_org(await db.get(Inquiry, inquiry_id), context, label="inquiry")
    if stage is not None:
        inquiry.stage = stage
    if notes is not None:
        inquiry.notes = notes
    if mark_contacted:
        inquiry.last_contacted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(inquiry)
    return inquiry


async def link_application_to_inquiry(db: AsyncSession, application: TenantApplication) -> Inquiry | None:
    """When an applicant turns out to be a lead we already had, join them up so the
    conversion rate counts the same person once."""
    inquiry = await db.scalar(
        select(Inquiry).where(
            Inquiry.organization_id == application.organization_id,
            Inquiry.unit_id == application.unit_id,
            Inquiry.phone_number == application.phone_number,
            Inquiry.stage.in_(OPEN_LEAD_STAGES),
        )
    )
    if inquiry is None:
        return None

    inquiry.application_id = application.id
    inquiry.stage = LeadStage.APPLIED
    inquiry.last_contacted_at = datetime.now(UTC)
    return inquiry


async def sync_stage_from_application(db: AsyncSession, application: TenantApplication) -> None:
    """Keep the pipeline honest as the application moves through review."""
    inquiry = await db.scalar(select(Inquiry).where(Inquiry.application_id == application.id))
    if inquiry is None:
        return

    mapping = {
        ApplicationStatus.UNDER_REVIEW: LeadStage.UNDER_REVIEW,
        ApplicationStatus.INTERVIEW_SCHEDULED: LeadStage.UNDER_REVIEW,
        ApplicationStatus.APPROVED: LeadStage.APPROVED,
        ApplicationStatus.REJECTED: LeadStage.REJECTED,
        ApplicationStatus.WITHDRAWN: LeadStage.LOST,
    }
    stage = mapping.get(application.status)
    if stage is not None:
        inquiry.stage = stage


# ----------------------------------------------------------- the vacancy desk


async def vacancy_report(db: AsyncSession, context: OrgContext) -> dict:
    """Every empty unit, how long it has been empty, and what that has cost (US-074)."""
    allowed = await accessible_property_ids(db, context)

    query = select(Unit).where(
        Unit.organization_id == context.organization_id,
        Unit.is_archived.is_(False),
        Unit.status.in_([UnitStatus.VACANT, UnitStatus.VACATING, UnitStatus.RESERVED]),
    )
    if allowed is not None:
        query = query.where(Unit.property_id.in_(allowed))

    units = list(await db.scalars(query))
    listings = {
        listing.unit_id: listing
        for listing in await db.scalars(
            select(VacancyListing).where(
                VacancyListing.unit_id.in_([unit.id for unit in units] or [uuid.uuid4()])
            )
        )
    }

    rows = []
    total_lost = ZERO
    for unit in units:
        listing = listings.get(unit.id)
        since = (listing.vacant_since if listing else None) or unit.vacancy_date
        days = (date.today() - since).days if since else None

        # A month's rent spread over 30 days is close enough, and far more
        # honest than pretending the calendar is uniform.
        daily = Decimal(unit.monthly_rent) / 30
        lost = (daily * days).quantize(Decimal("0.01")) if days else ZERO
        total_lost += lost

        property_record = await db.get(Property, unit.property_id)
        open_leads = int(
            await db.scalar(
                select(func.count(Inquiry.id)).where(
                    Inquiry.unit_id == unit.id, Inquiry.stage.in_(OPEN_LEAD_STAGES)
                )
            )
            or 0
        )
        applications = int(
            await db.scalar(
                select(func.count(TenantApplication.id)).where(
                    TenantApplication.unit_id == unit.id,
                    TenantApplication.status.in_(
                        [
                            ApplicationStatus.SUBMITTED,
                            ApplicationStatus.UNDER_REVIEW,
                            ApplicationStatus.INTERVIEW_SCHEDULED,
                        ]
                    ),
                )
            )
            or 0
        )

        rows.append(
            {
                "unit_id": str(unit.id),
                "unit_number": unit.unit_number,
                "property_name": property_record.name if property_record else "",
                "status": unit.status.value,
                "monthly_rent": float(unit.monthly_rent),
                "vacant_since": since.isoformat() if since else None,
                "days_vacant": days,
                "revenue_lost": float(lost),
                "listing_slug": listing.slug if listing else None,
                "listing_status": listing.status.value if listing else None,
                "views": listing.view_count if listing else 0,
                "open_leads": open_leads,
                "applications": applications,
            }
        )

    rows.sort(key=lambda row: row["days_vacant"] or 0, reverse=True)
    return {
        "vacant_units": len(rows),
        "total_revenue_lost": float(total_lost),
        "monthly_revenue_at_risk": float(sum((Decimal(str(row["monthly_rent"])) for row in rows), ZERO)),
        "units": rows,
    }


async def conversion_report(db: AsyncSession, context: OrgContext) -> dict:
    """Enquiries to applications to approvals (US-075)."""
    inquiries = int(
        await db.scalar(
            select(func.count(Inquiry.id)).where(Inquiry.organization_id == context.organization_id)
        )
        or 0
    )
    applied = int(
        await db.scalar(
            select(func.count(Inquiry.id)).where(
                Inquiry.organization_id == context.organization_id,
                Inquiry.application_id.is_not(None),
            )
        )
        or 0
    )
    approved = int(
        await db.scalar(
            select(func.count(Inquiry.id)).where(
                Inquiry.organization_id == context.organization_id,
                Inquiry.stage == LeadStage.APPROVED,
            )
        )
        or 0
    )
    stale = len(await list_inquiries(db, context, stale_only=True, limit=500))

    return {
        "inquiries": inquiries,
        "applications": applied,
        "approvals": approved,
        "stale_leads": stale,
        "inquiry_to_application_percent": round(applied / inquiries * 100, 1) if inquiries else None,
        "application_to_approval_percent": round(approved / applied * 100, 1) if applied else None,
    }


async def chase_stale_leads(db: AsyncSession) -> int:
    """Nudge the office about leads nobody has touched in three days (US-075)."""
    cutoff = datetime.now(UTC) - timedelta(days=STALE_LEAD_DAYS)

    rows = list(
        await db.scalars(
            select(Inquiry).where(
                Inquiry.stage.in_(OPEN_LEAD_STAGES),
                Inquiry.follow_up_sent_at.is_(None),
                Inquiry.created_at < cutoff,
            )
        )
    )
    chased = 0
    for inquiry in rows:
        last = inquiry.last_contacted_at or inquiry.created_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last > cutoff:
            continue

        unit = await db.get(Unit, inquiry.unit_id)
        managers = await db.scalars(
            select(User).where(
                User.organization_id == inquiry.organization_id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
                User.is_active.is_(True),
            )
        )
        for manager in managers:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_user(manager),
                notification_type=NotificationType.INQUIRY_RECEIVED,
                title="A lead has gone cold",
                body=(
                    f"{inquiry.full_name} ({inquiry.phone_number}) asked about unit "
                    f"{unit.unit_number if unit else ''} "
                    f"{(datetime.now(UTC) - last).days} days ago and has not been followed up."
                ),
                channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH],
                link_path=f"/vacancies/{inquiry.unit_id}",
                entity_type="inquiry",
                entity_id=inquiry.id,
            )
        inquiry.follow_up_sent_at = datetime.now(UTC)
        chased += 1

    if chased:
        await db.commit()
    return chased
