"""Compliance, parking, amenities and utility accounts (US-078 to US-081).

The three rules that recur here are all about refusing to let a system say
something that is not true: a certificate with no expiry date is `MISSING`
rather than silently valid; a bay cannot be double-allocated; and an amenity
slot that overlaps an existing booking is refused rather than accepted and
apologised for later.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.facilities import (
    REMINDER_DAYS,
    Amenity,
    AmenityBooking,
    BookingStatus,
    ComplianceItem,
    ComplianceStatus,
    ParkingAllocation,
    ParkingBay,
    UtilityAccount,
    UtilityPaymentStatus,
)
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.models.user import User, UserRole
from app.services import audit_service, notification_service

ZERO = Decimal("0.00")

LIVE_TENANCY_STATUSES = [
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
]


async def _property_in_scope(db: AsyncSession, context: OrgContext, property_id: uuid.UUID) -> Property:
    record = assert_in_org(await db.get(Property, property_id), context, label="property")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None and record.id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )
    return record


# ------------------------------------------------------------------ compliance


async def create_compliance_item(
    db: AsyncSession, context: OrgContext, payload, request: Request | None = None
) -> ComplianceItem:
    await _property_in_scope(db, context, payload.property_id)

    item = ComplianceItem(organization_id=context.organization_id, **payload.model_dump())
    db.add(item)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="compliance.created",
        entity_type="compliance_item",
        entity_id=item.id,
        actor=context.user,
        summary=(
            f"Recorded {item.name}"
            + (f", expires {item.expires_on:%d %b %Y}" if item.expires_on else " with no expiry date")
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def update_compliance_item(
    db: AsyncSession,
    context: OrgContext,
    item_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> ComplianceItem:
    item = assert_in_org(await db.get(ComplianceItem, item_id), context, label="compliance item")
    fields = payload.model_dump(exclude_unset=True)

    renewed = "expires_on" in fields and fields["expires_on"] != item.expires_on
    for field, value in fields.items():
        setattr(item, field, value)
    if renewed:
        # A renewed certificate starts the reminder ladder again from the top.
        item.last_reminder_days = None

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="compliance.updated",
        entity_type="compliance_item",
        entity_id=item.id,
        actor=context.user,
        summary=(
            f"{item.name} renewed to {item.expires_on:%d %b %Y}"
            if renewed and item.expires_on
            else f"Updated {item.name}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(item)
    return item


async def list_compliance_items(
    db: AsyncSession,
    context: OrgContext,
    *,
    property_id: uuid.UUID | None = None,
    item_status: ComplianceStatus | None = None,
) -> list[ComplianceItem]:
    query = select(ComplianceItem).where(
        ComplianceItem.organization_id == context.organization_id,
        ComplianceItem.is_archived.is_(False),
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(ComplianceItem.property_id.in_(allowed))
    if property_id:
        query = query.where(ComplianceItem.property_id == property_id)

    # Nulls last so a certificate with no expiry does not masquerade as the most
    # urgent thing on the list.
    rows = list(await db.scalars(query.order_by(ComplianceItem.expires_on.asc().nulls_last())))
    return [row for row in rows if item_status is None or row.status == item_status]


async def compliance_dashboard(db: AsyncSession, context: OrgContext) -> dict:
    """The traffic light, per property (US-078)."""
    items = await list_compliance_items(db, context)

    by_property: dict[uuid.UUID, dict] = {}
    counts = {state.value: 0 for state in ComplianceStatus}

    for item in items:
        counts[item.status.value] += 1
        bucket = by_property.setdefault(
            item.property_id,
            {"property_id": str(item.property_id), "property_name": "", "items": [], "worst": "valid"},
        )
        bucket["items"].append(
            {
                "id": str(item.id),
                "name": item.name,
                "type": item.compliance_type.value,
                "expires_on": item.expires_on.isoformat() if item.expires_on else None,
                "days_until_expiry": item.days_until_expiry,
                "status": item.status.value,
            }
        )

    severity = {"valid": 0, "expiring_soon": 1, "missing": 2, "expired": 3}
    for property_id, bucket in by_property.items():
        record = await db.get(Property, property_id)
        bucket["property_name"] = record.name if record else ""
        bucket["worst"] = max((row["status"] for row in bucket["items"]), key=lambda value: severity[value])

    return {
        "total_items": len(items),
        "counts": counts,
        "needs_attention": counts["expired"] + counts["expiring_soon"] + counts["missing"],
        "properties": sorted(by_property.values(), key=lambda row: row["property_name"]),
    }


async def sweep_compliance_expiry(db: AsyncSession) -> int:
    """Walk the reminder ladder — 90, 60, 30, 7 days — and again on the day it
    expires. Each rung fires once (US-078)."""
    today = date.today()
    horizon = today + timedelta(days=max(REMINDER_DAYS))

    rows = list(
        await db.scalars(
            select(ComplianceItem).where(
                ComplianceItem.is_archived.is_(False),
                ComplianceItem.expires_on.is_not(None),
                ComplianceItem.expires_on <= horizon,
            )
        )
    )

    sent = 0
    for item in rows:
        days = (item.expires_on - today).days if item.expires_on else None
        if days is None:
            continue

        # Which rung applies: the smallest threshold this item has passed.
        rung = next((threshold for threshold in REMINDER_DAYS if days <= threshold), None)
        if days < 0:
            rung = 0
        if rung is None:
            continue
        if item.last_reminder_days is not None and item.last_reminder_days <= rung:
            continue

        property_record = await db.get(Property, item.property_id)
        managers = await db.scalars(
            select(User).where(
                User.organization_id == item.organization_id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
                User.is_active.is_(True),
            )
        )
        overdue = days < 0
        for manager in managers:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_user(manager),
                notification_type=NotificationType.COMPLIANCE_EXPIRY,
                title=("Compliance certificate has EXPIRED" if overdue else "Compliance renewal due"),
                body=(
                    f"{item.name} for "
                    f"{property_record.name if property_record else 'a property'} "
                    + (
                        f"expired {abs(days)} day(s) ago on {item.expires_on:%d %b %Y}. "
                        "Renew it before the next inspection or claim."
                        if overdue
                        else f"expires in {days} day(s), on {item.expires_on:%d %b %Y}."
                    )
                    + (f" Responsible: {item.responsible_party}." if item.responsible_party else "")
                ),
                channels=[
                    NotificationChannel.WHATSAPP,
                    NotificationChannel.IN_APP,
                    NotificationChannel.PUSH,
                ],
                link_path=f"/compliance?property_id={item.property_id}",
                entity_type="compliance_item",
                entity_id=item.id,
                organization_id=item.organization_id,
            )
        item.last_reminder_days = rung
        sent += 1

    if sent:
        await db.commit()
    return sent


# --------------------------------------------------------------------- parking


async def create_bay(
    db: AsyncSession, context: OrgContext, payload, request: Request | None = None
) -> ParkingBay:
    await _property_in_scope(db, context, payload.property_id)

    taken = await db.scalar(
        select(ParkingBay.id).where(
            ParkingBay.property_id == payload.property_id,
            ParkingBay.bay_number == payload.bay_number,
        )
    )
    if taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bay {payload.bay_number} already exists at this property",
        )

    bay = ParkingBay(organization_id=context.organization_id, **payload.model_dump())
    db.add(bay)
    await db.commit()
    await db.refresh(bay)
    return bay


async def current_allocation(db: AsyncSession, bay_id: uuid.UUID) -> ParkingAllocation | None:
    today = date.today()
    return await db.scalar(
        select(ParkingAllocation).where(
            ParkingAllocation.bay_id == bay_id,
            ParkingAllocation.released_at.is_(None),
            ParkingAllocation.start_date <= today,
            or_(ParkingAllocation.end_date.is_(None), ParkingAllocation.end_date >= today),
        )
    )


async def allocate_bay(
    db: AsyncSession, context: OrgContext, bay_id: uuid.UUID, payload, request: Request | None = None
) -> ParkingAllocation:
    """Give a bay to a tenancy or a visitor. One bay, one holder (US-079)."""
    bay = assert_in_org(await db.get(ParkingBay, bay_id), context, label="bay")
    if not bay.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This bay is out of service")

    existing = await current_allocation(db, bay.id)
    if existing is not None:
        holder = existing.guest_name or "another tenant"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bay {bay.bay_number} is already allocated to {holder}",
        )

    if payload.tenancy_id is not None:
        assert_in_org(await db.get(Tenancy, payload.tenancy_id), context, label="tenancy")

    allocation = ParkingAllocation(
        organization_id=context.organization_id,
        bay_id=bay.id,
        monthly_fee=payload.monthly_fee if payload.monthly_fee is not None else bay.monthly_fee,
        **payload.model_dump(exclude={"monthly_fee"}),
    )
    db.add(allocation)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="parking.allocated",
        entity_type="parking_bay",
        entity_id=bay.id,
        actor=context.user,
        summary=(
            f"Bay {bay.bay_number} allocated to "
            f"{payload.guest_name or 'a tenancy'} from {payload.start_date:%d %b %Y}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(allocation)
    return allocation


async def release_bay(db: AsyncSession, context: OrgContext, allocation_id: uuid.UUID) -> ParkingAllocation:
    allocation = assert_in_org(await db.get(ParkingAllocation, allocation_id), context, label="allocation")
    if allocation.released_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This allocation is already released"
        )

    allocation.released_at = datetime.now(UTC)
    bay = await db.get(ParkingBay, allocation.bay_id)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="parking.released",
        entity_type="parking_bay",
        entity_id=allocation.bay_id,
        actor=context.user,
        summary=f"Bay {bay.bay_number if bay else ''} released",
    )
    await db.commit()
    await db.refresh(allocation)
    return allocation


async def parking_overview(db: AsyncSession, context: OrgContext, property_id: uuid.UUID) -> dict:
    await _property_in_scope(db, context, property_id)

    bays = list(
        await db.scalars(
            select(ParkingBay).where(ParkingBay.property_id == property_id).order_by(ParkingBay.bay_number)
        )
    )

    rows = []
    allocated = 0
    monthly_income = ZERO
    for bay in bays:
        allocation = await current_allocation(db, bay.id)
        holder = None
        if allocation is not None:
            allocated += 1
            if allocation.bill_monthly:
                monthly_income += Decimal(allocation.monthly_fee)
            if allocation.tenancy_id:
                tenancy = await db.get(Tenancy, allocation.tenancy_id)
                tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
                holder = tenant.full_name if tenant else None
            else:
                holder = allocation.guest_name

        rows.append(
            {
                "bay_id": str(bay.id),
                "bay_number": bay.bay_number,
                "bay_type": bay.bay_type.value,
                "level": bay.level,
                "monthly_fee": float(bay.monthly_fee),
                "is_active": bay.is_active,
                "allocation_id": str(allocation.id) if allocation else None,
                "holder": holder,
                "vehicle_registration": allocation.vehicle_registration if allocation else None,
                "allocated_until": (
                    allocation.end_date.isoformat() if allocation and allocation.end_date else None
                ),
            }
        )

    return {
        "total_bays": len(bays),
        "allocated": allocated,
        "available": len([bay for bay in bays if bay.is_active]) - allocated,
        "monthly_parking_income": float(monthly_income),
        "bays": rows,
    }


async def parking_charges_for_tenancy(db: AsyncSession, tenancy_id: uuid.UUID) -> list[tuple[str, Decimal]]:
    """Billable bays for one tenancy, as (bay number, fee) pairs."""
    today = date.today()
    rows = await db.execute(
        select(ParkingAllocation, ParkingBay)
        .join(ParkingBay, ParkingBay.id == ParkingAllocation.bay_id)
        .where(
            ParkingAllocation.tenancy_id == tenancy_id,
            ParkingAllocation.bill_monthly.is_(True),
            ParkingAllocation.released_at.is_(None),
            ParkingAllocation.start_date <= today,
            or_(ParkingAllocation.end_date.is_(None), ParkingAllocation.end_date >= today),
        )
    )
    return [
        (bay.bay_number, Decimal(allocation.monthly_fee))
        for allocation, bay in rows.all()
        if Decimal(allocation.monthly_fee) > ZERO
    ]


# -------------------------------------------------------------------- amenities


async def create_amenity(
    db: AsyncSession, context: OrgContext, payload, request: Request | None = None
) -> Amenity:
    await _property_in_scope(db, context, payload.property_id)

    amenity = Amenity(organization_id=context.organization_id, **payload.model_dump())
    db.add(amenity)
    await db.commit()
    await db.refresh(amenity)
    return amenity


async def _overlapping_booking(
    db: AsyncSession, amenity_id: uuid.UUID, starts_at: datetime, ends_at: datetime
) -> AmenityBooking | None:
    """Two windows overlap unless one ends before the other starts."""
    return await db.scalar(
        select(AmenityBooking).where(
            AmenityBooking.amenity_id == amenity_id,
            AmenityBooking.status != BookingStatus.CANCELLED,
            AmenityBooking.starts_at < ends_at,
            AmenityBooking.ends_at > starts_at,
        )
    )


async def book_amenity(
    db: AsyncSession,
    context: OrgContext,
    amenity_id: uuid.UUID,
    *,
    starts_at: datetime,
    ends_at: datetime,
    tenancy_id: uuid.UUID | None,
    purpose: str | None = None,
    guests: int = 0,
    status_override: BookingStatus = BookingStatus.CONFIRMED,
) -> AmenityBooking:
    """Reserve a window, refusing anything that breaks the amenity's rules (US-080)."""
    amenity = assert_in_org(await db.get(Amenity, amenity_id), context, label="amenity")

    is_block = status_override == BookingStatus.BLOCKED
    if not amenity.is_bookable and not is_block:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"{amenity.name} is not open for booking"
        )
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The booking ends before it starts"
        )

    # The rules apply to tenants, not to a manager taking the room out of service.
    if not is_block:
        hours = (ends_at - starts_at).total_seconds() / 3600
        if hours > amenity.max_hours_per_booking:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{amenity.name} can be booked for at most "
                    f"{amenity.max_hours_per_booking} hour(s) at a time"
                ),
            )
        notice = (starts_at - datetime.now(UTC)).total_seconds() / 3600
        if notice < amenity.min_notice_hours:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{amenity.name} needs {amenity.min_notice_hours} hour(s) notice",
            )
        if not (
            amenity.opens_at_hour <= starts_at.hour
            and ends_at.hour <= amenity.closes_at_hour
            and (ends_at.hour > amenity.opens_at_hour or ends_at.minute == 0)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{amenity.name} is open from {amenity.opens_at_hour}:00 "
                    f"to {amenity.closes_at_hour}:00"
                ),
            )

        if tenancy_id is not None:
            week_start = starts_at - timedelta(days=starts_at.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            in_week = int(
                await db.scalar(
                    select(func.count(AmenityBooking.id)).where(
                        AmenityBooking.amenity_id == amenity.id,
                        AmenityBooking.tenancy_id == tenancy_id,
                        AmenityBooking.status == BookingStatus.CONFIRMED,
                        AmenityBooking.starts_at >= week_start,
                        AmenityBooking.starts_at < week_start + timedelta(days=7),
                    )
                )
                or 0
            )
            if in_week >= amenity.max_bookings_per_week:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"You have already booked {amenity.name} "
                        f"{in_week} time(s) this week, which is the limit"
                    ),
                )

    clash = await _overlapping_booking(db, amenity.id, starts_at, ends_at)
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{amenity.name} is already taken from "
                f"{clash.starts_at:%H:%M} to {clash.ends_at:%H:%M} that day"
            ),
        )

    tenant_id = None
    if tenancy_id is not None:
        tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
        tenant_id = tenancy.tenant_id

    booking = AmenityBooking(
        organization_id=context.organization_id,
        amenity_id=amenity.id,
        tenancy_id=tenancy_id,
        tenant_id=tenant_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status_override,
        purpose=purpose,
        guests=guests,
        created_by_user_id=context.user.id if context.user else None,
    )
    db.add(booking)
    await db.flush()

    if tenant_id is not None:
        tenant = await db.get(Tenant, tenant_id)
        if tenant is not None:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_tenant(tenant),
                notification_type=NotificationType.AMENITY_BOOKING,
                title=f"{amenity.name} booked",
                body=(
                    f"Your booking for {amenity.name} on {starts_at:%A %d %B} from "
                    f"{starts_at:%H:%M} to {ends_at:%H:%M} is confirmed."
                    + (f" ({purpose})" if purpose else "")
                ),
                channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
                entity_type="amenity_booking",
                entity_id=booking.id,
                organization_id=context.organization_id,
            )

    await db.commit()
    await db.refresh(booking)
    return booking


async def cancel_booking(
    db: AsyncSession, context: OrgContext, booking_id: uuid.UUID, reason: str | None = None
) -> AmenityBooking:
    booking = assert_in_org(await db.get(AmenityBooking, booking_id), context, label="booking")
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This booking is already cancelled")

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_reason = reason
    await db.commit()
    await db.refresh(booking)
    return booking


async def amenity_calendar(
    db: AsyncSession,
    context: OrgContext,
    amenity_id: uuid.UUID,
    *,
    day_from: date,
    day_to: date,
) -> list[AmenityBooking]:
    assert_in_org(await db.get(Amenity, amenity_id), context, label="amenity")
    rows = await db.scalars(
        select(AmenityBooking)
        .where(
            AmenityBooking.amenity_id == amenity_id,
            AmenityBooking.status != BookingStatus.CANCELLED,
            func.date(AmenityBooking.starts_at) >= day_from,
            func.date(AmenityBooking.starts_at) <= day_to,
        )
        .order_by(AmenityBooking.starts_at)
    )
    return list(rows)


async def amenity_usage(
    db: AsyncSession, context: OrgContext, property_id: uuid.UUID, *, months: int = 1
) -> list[dict]:
    """How much each amenity actually gets used (US-080)."""
    await _property_in_scope(db, context, property_id)
    since = date.today() - timedelta(days=30 * months)

    amenities = list(await db.scalars(select(Amenity).where(Amenity.property_id == property_id)))
    usage = []
    for amenity in amenities:
        rows = list(
            await db.scalars(
                select(AmenityBooking).where(
                    AmenityBooking.amenity_id == amenity.id,
                    AmenityBooking.status == BookingStatus.CONFIRMED,
                    func.date(AmenityBooking.starts_at) >= since,
                )
            )
        )
        hours = sum((booking.ends_at - booking.starts_at).total_seconds() / 3600 for booking in rows)
        usage.append(
            {
                "amenity_id": str(amenity.id),
                "name": amenity.name,
                "kind": amenity.kind.value,
                "bookings": len(rows),
                "hours_booked": round(hours, 1),
                "distinct_tenants": len({booking.tenancy_id for booking in rows if booking.tenancy_id}),
            }
        )
    return sorted(usage, key=lambda row: row["bookings"], reverse=True)


# ------------------------------------------------------------ utility accounts


async def upsert_utility_account(
    db: AsyncSession, context: OrgContext, payload, request: Request | None = None
) -> UtilityAccount:
    await _property_in_scope(db, context, payload.property_id)

    account = await db.scalar(
        select(UtilityAccount).where(
            UtilityAccount.organization_id == context.organization_id,
            UtilityAccount.property_id == payload.property_id,
            UtilityAccount.account_type == payload.account_type,
            UtilityAccount.account_number == payload.account_number,
        )
    )
    if account is None:
        account = UtilityAccount(organization_id=context.organization_id, **payload.model_dump())
        db.add(account)
    else:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(account, field, value)

    await db.commit()
    await db.refresh(account)
    return account


async def update_utility_status(
    db: AsyncSession,
    context: OrgContext,
    account_id: uuid.UUID,
    *,
    payment_status: UtilityPaymentStatus,
    last_paid_on: date | None = None,
    last_amount: Decimal | None = None,
    next_due_on: date | None = None,
    request: Request | None = None,
) -> UtilityAccount:
    account = assert_in_org(await db.get(UtilityAccount, account_id), context, label="account")

    account.payment_status = payment_status
    account.status_updated_at = datetime.now(UTC)
    account.status_updated_by_id = context.user.id
    if last_paid_on is not None:
        account.last_paid_on = last_paid_on
    if last_amount is not None:
        account.last_amount = last_amount
    if next_due_on is not None:
        account.next_due_on = next_due_on

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="utility.status_updated",
        entity_type="utility_account",
        entity_id=account.id,
        actor=context.user,
        summary=(
            f"{account.account_type.value.upper()} account {account.account_number} "
            f"marked {payment_status.value}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(account)
    return account


async def list_utility_accounts(
    db: AsyncSession, context: OrgContext, *, property_id: uuid.UUID | None = None
) -> list[UtilityAccount]:
    query = select(UtilityAccount).where(UtilityAccount.organization_id == context.organization_id)
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(UtilityAccount.property_id.in_(allowed))
    if property_id:
        query = query.where(UtilityAccount.property_id == property_id)

    return list(await db.scalars(query.order_by(UtilityAccount.account_type)))


async def sweep_overdue_utilities(db: AsyncSession) -> int:
    """Tell the owner when the building's own bills have gone past due (US-081)."""
    today = date.today()
    rows = list(
        await db.scalars(
            select(UtilityAccount).where(
                UtilityAccount.payment_status != UtilityPaymentStatus.PAID,
                UtilityAccount.next_due_on.is_not(None),
                UtilityAccount.next_due_on < today,
            )
        )
    )

    alerted = 0
    for account in rows:
        property_record = await db.get(Property, account.property_id)
        managers = await db.scalars(
            select(User).where(
                User.organization_id == account.organization_id,
                User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN, UserRole.PROPERTY_MANAGER]),
                User.is_active.is_(True),
            )
        )
        for manager in managers:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_user(manager),
                notification_type=NotificationType.UTILITY_OVERDUE,
                title="A building utility bill is overdue",
                body=(
                    f"The {account.account_type.value.upper()} account "
                    f"{account.account_number} for "
                    f"{property_record.name if property_record else 'a property'} "
                    f"was due on {account.next_due_on:%d %b %Y} and is not marked paid. "
                    "A disconnection affects every tenant in the block."
                ),
                channels=[NotificationChannel.IN_APP, NotificationChannel.PUSH, NotificationChannel.WHATSAPP],
                link_path=f"/properties/{account.property_id}/utilities",
                entity_type="utility_account",
                entity_id=account.id,
                organization_id=account.organization_id,
            )
        # Push the reminder out a week so this becomes a weekly nag, not a daily one.
        account.next_due_on = today + timedelta(days=7)
        alerted += 1

    if alerted:
        await db.commit()
    return alerted
