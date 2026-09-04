"""Portfolio: properties, units, statuses and the dashboard roll-up (Sprint 2).

Every query in here is filtered by organization *and*, for caretakers, by their
property assignments — the two together are what make cross-tenant and
cross-property leakage structurally impossible rather than merely unlikely.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids, assert_in_org
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import Property, PropertyType, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus
from app.models.user import User, UserRole
from app.schemas.property import (
    PortfolioStats,
    PropertyCreate,
    PropertyUpdate,
    UnitBulkCreate,
    UnitCreate,
    UnitStatusUpdate,
    UnitUpdate,
)
from app.services import audit_service, file_service, notification_service, reference_service

OCCUPYING_STATUSES = {UnitStatus.OCCUPIED, UnitStatus.VACATING}


async def _scope_properties(db: AsyncSession, context: OrgContext, query: Select) -> Select:
    query = query.where(Property.organization_id == context.organization_id)
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Property.id.in_(allowed))
    return query


async def _scope_units(db: AsyncSession, context: OrgContext, query: Select) -> Select:
    query = query.where(Unit.organization_id == context.organization_id)
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Unit.property_id.in_(allowed))
    return query


# ---------------------------------------------------------------------- property


async def _assert_owner_profile(
    db: AsyncSession, context: OrgContext, owner_profile_id: uuid.UUID | None
) -> None:
    """A property may only be attributed to an owner profile in the same org.

    Without this check an agency could point a property at another agency's owner
    profile, which would leak that property's rent into the other agency's
    disbursement calculation.
    """
    if owner_profile_id is None:
        return
    from app.models.agency import OwnerProfile

    profile = await db.get(OwnerProfile, owner_profile_id)
    if profile is None or profile.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner profile not found")


async def create_property(
    db: AsyncSession, context: OrgContext, payload: PropertyCreate, request: Request | None = None
) -> Property:
    await _assert_owner_profile(db, context, payload.owner_profile_id)
    reference = await reference_service.generate_reference(db, Property, context.organization_id, "PRP")
    record = Property(
        organization_id=context.organization_id,
        reference_code=reference,
        **payload.model_dump(exclude={"photo_file_ids"}),
    )
    db.add(record)
    await db.flush()

    if payload.photo_file_ids:
        await file_service.attach(db, context, payload.photo_file_ids, "property", record.id)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="property.created",
        entity_type="property",
        entity_id=record.id,
        actor=context.user,
        summary=f"Added property {record.name} ({reference})",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def list_properties(
    db: AsyncSession, context: OrgContext, include_archived: bool = False, search: str | None = None
) -> list[Property]:
    query = select(Property)
    query = await _scope_properties(db, context, query)
    if not include_archived:
        query = query.where(Property.is_archived.is_(False))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            Property.name.ilike(pattern)
            | Property.address.ilike(pattern)
            | Property.reference_code.ilike(pattern)
        )
    rows = await db.scalars(query.order_by(Property.created_at.desc()))
    return list(rows)


async def get_property(db: AsyncSession, context: OrgContext, property_id: uuid.UUID) -> Property:
    record = assert_in_org(await db.get(Property, property_id), context, label="property")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None and record.id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )
    return record


async def update_property(
    db: AsyncSession,
    context: OrgContext,
    property_id: uuid.UUID,
    payload: PropertyUpdate,
    request: Request | None = None,
) -> Property:
    record = await get_property(db, context, property_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"photo_file_ids"})
    if "owner_profile_id" in fields:
        await _assert_owner_profile(db, context, fields["owner_profile_id"])

    before = {field: getattr(record, field) for field in fields}
    for field, value in fields.items():
        setattr(record, field, value)
    after = {field: getattr(record, field) for field in fields}

    if payload.photo_file_ids is not None:
        await file_service.attach(db, context, payload.photo_file_ids, "property", record.id, replace=True)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="property.updated",
        entity_type="property",
        entity_id=record.id,
        actor=context.user,
        summary=f"Updated {record.name}",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def archive_property(
    db: AsyncSession, context: OrgContext, property_id: uuid.UUID, request: Request | None = None
) -> Property:
    record = await get_property(db, context, property_id)

    active = await db.scalar(
        select(func.count())
        .select_from(Tenancy)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .where(
            Unit.property_id == record.id,
            Tenancy.status.in_(
                [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]
            ),
        )
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{record.name} still has {active} active tenanc{'y' if active == 1 else 'ies'}. "
                "End them before archiving the property."
            ),
        )

    record.is_archived = True
    record.archived_at = datetime.now(UTC)
    for unit in record.units:
        unit.is_archived = True
        unit.archived_at = record.archived_at

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="property.archived",
        entity_type="property",
        entity_id=record.id,
        actor=context.user,
        summary=f"Archived {record.name}",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def restore_property(
    db: AsyncSession, context: OrgContext, property_id: uuid.UUID, request: Request | None = None
) -> Property:
    record = await get_property(db, context, property_id)
    record.is_archived = False
    record.archived_at = None
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="property.restored",
        entity_type="property",
        entity_id=record.id,
        actor=context.user,
        summary=f"Restored {record.name}",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


# -------------------------------------------------------------------------- unit


async def create_unit(
    db: AsyncSession, context: OrgContext, payload: UnitCreate, request: Request | None = None
) -> Unit:
    await get_property(db, context, payload.property_id)  # scope + existence check

    await _assert_unit_number_free(db, payload.property_id, payload.unit_number)

    reference = await reference_service.generate_reference(db, Unit, context.organization_id, "UNT")
    record = Unit(
        organization_id=context.organization_id,
        reference_code=reference,
        **payload.model_dump(exclude={"photo_file_ids"}),
    )
    db.add(record)
    await db.flush()

    if payload.photo_file_ids:
        await file_service.attach(db, context, payload.photo_file_ids, "unit", record.id)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="unit.created",
        entity_type="unit",
        entity_id=record.id,
        actor=context.user,
        summary=f"Added unit {record.unit_number} ({reference})",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _assert_unit_number_free(
    db: AsyncSession, property_id: uuid.UUID, unit_number: str, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(Unit.id).where(Unit.property_id == property_id, Unit.unit_number == unit_number)
    if exclude_id:
        query = query.where(Unit.id != exclude_id)
    if await db.scalar(query):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unit '{unit_number}' already exists in this property",
        )


async def bulk_create_units(
    db: AsyncSession, context: OrgContext, payload: UnitBulkCreate, request: Request | None = None
) -> list[Unit]:
    """Create N identically-specced units with sequential names (US-008)."""
    await get_property(db, context, payload.property_id)

    numbers = payload.unit_numbers()
    taken = set(
        await db.scalars(
            select(Unit.unit_number).where(
                Unit.property_id == payload.property_id, Unit.unit_number.in_(numbers)
            )
        )
    )
    if taken:
        preview = ", ".join(sorted(taken)[:5])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"These unit numbers already exist: {preview}" + (" …" if len(taken) > 5 else ""),
        )

    shared = payload.model_dump(
        exclude={"property_id", "count", "name_prefix", "start_number", "number_padding"}
    )
    created: list[Unit] = []
    for unit_number in numbers:
        reference = await reference_service.generate_reference(db, Unit, context.organization_id, "UNT")
        unit = Unit(
            organization_id=context.organization_id,
            property_id=payload.property_id,
            reference_code=reference,
            unit_number=unit_number,
            **shared,
        )
        db.add(unit)
        created.append(unit)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="unit.bulk_created",
        entity_type="property",
        entity_id=payload.property_id,
        actor=context.user,
        summary=f"Bulk-created {len(created)} units ({numbers[0]}–{numbers[-1]})",
        request=request,
    )
    await db.commit()
    for unit in created:
        await db.refresh(unit)
    return created


async def list_units(
    db: AsyncSession,
    context: OrgContext,
    *,
    property_id: uuid.UUID | None = None,
    unit_status: UnitStatus | None = None,
    include_archived: bool = False,
    search: str | None = None,
) -> list[Unit]:
    query = select(Unit)
    query = await _scope_units(db, context, query)
    if property_id:
        query = query.where(Unit.property_id == property_id)
    if unit_status:
        query = query.where(Unit.status == unit_status)
    if not include_archived:
        query = query.where(Unit.is_archived.is_(False))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(Unit.unit_number.ilike(pattern) | Unit.reference_code.ilike(pattern))
    rows = await db.scalars(query.order_by(Unit.unit_number))
    return list(rows)


async def get_unit(db: AsyncSession, context: OrgContext, unit_id: uuid.UUID) -> Unit:
    record = assert_in_org(await db.get(Unit, unit_id), context, label="unit")
    allowed = await accessible_property_ids(db, context)
    if allowed is not None and record.property_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this property"
        )
    return record


async def update_unit(
    db: AsyncSession,
    context: OrgContext,
    unit_id: uuid.UUID,
    payload: UnitUpdate,
    request: Request | None = None,
) -> Unit:
    record = await get_unit(db, context, unit_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"photo_file_ids"})

    if "unit_number" in fields and fields["unit_number"] != record.unit_number:
        await _assert_unit_number_free(db, record.property_id, fields["unit_number"], record.id)

    before = {field: getattr(record, field) for field in fields}
    for field, value in fields.items():
        setattr(record, field, value)
    after = {field: getattr(record, field) for field in fields}

    if payload.photo_file_ids is not None:
        await file_service.attach(db, context, payload.photo_file_ids, "unit", record.id, replace=True)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="unit.updated",
        entity_type="unit",
        entity_id=record.id,
        actor=context.user,
        summary=f"Updated unit {record.unit_number}",
        changes=audit_service.diff(before, after),
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def update_unit_status(
    db: AsyncSession,
    context: OrgContext,
    unit_id: uuid.UUID,
    payload: UnitStatusUpdate,
    request: Request | None = None,
) -> Unit:
    """Change a unit's status, logging it and alerting the owner when a caretaker
    is the one making the change (US-010)."""
    record = await get_unit(db, context, unit_id)
    previous = record.status
    if previous == payload.status:
        return record

    if payload.status in OCCUPYING_STATUSES and previous == UnitStatus.VACANT:
        active_tenancy = await db.scalar(
            select(Tenancy.id).where(
                Tenancy.unit_id == record.id,
                Tenancy.status.in_(
                    [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]
                ),
            )
        )
        if not active_tenancy:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Create a tenancy to mark this unit occupied — status follows the tenancy.",
            )

    record.status = payload.status
    if payload.status == UnitStatus.VACANT:
        record.vacancy_date = date.today()
        record.expected_vacancy_date = None
    elif payload.status == UnitStatus.VACATING:
        record.expected_vacancy_date = payload.expected_vacancy_date

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="unit.status_changed",
        entity_type="unit",
        entity_id=record.id,
        actor=context.user,
        summary=f"Unit {record.unit_number}: {previous.value} → {payload.status.value}",
        changes={
            "status": {"from": previous.value, "to": payload.status.value},
            "note": payload.note,
        },
        request=request,
    )

    if context.role == UserRole.CARETAKER:
        await _notify_owners_of_status_change(db, context, record, previous)

    await db.commit()
    await db.refresh(record)
    return record


async def _notify_owners_of_status_change(
    db: AsyncSession, context: OrgContext, unit: Unit, previous: UnitStatus
) -> None:
    prop = await db.get(Property, unit.property_id)
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
            notification_type=NotificationType.UNIT_STATUS_CHANGED,
            title="Unit status updated",
            body=(
                f"{context.user.full_name} changed unit {unit.unit_number} at "
                f"{prop.name if prop else 'your property'} from {previous.value.replace('_', ' ')} "
                f"to {unit.status.value.replace('_', ' ')}."
            ),
            channels=[NotificationChannel.PUSH, NotificationChannel.IN_APP],
            link_path=f"/units/{unit.id}",
            entity_type="unit",
            entity_id=unit.id,
        )


async def archive_unit(
    db: AsyncSession, context: OrgContext, unit_id: uuid.UUID, request: Request | None = None
) -> Unit:
    record = await get_unit(db, context, unit_id)

    active = await db.scalar(
        select(Tenancy.id).where(
            Tenancy.unit_id == record.id,
            Tenancy.status.in_(
                [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]
            ),
        )
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This unit has an active tenancy. End it before archiving the unit.",
        )

    record.is_archived = True
    record.archived_at = datetime.now(UTC)
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="unit.archived",
        entity_type="unit",
        entity_id=record.id,
        actor=context.user,
        summary=f"Archived unit {record.unit_number}",
        request=request,
    )
    await db.commit()
    await db.refresh(record)
    return record


# --------------------------------------------------------------------- dashboard


async def portfolio_stats(
    db: AsyncSession, context: OrgContext
) -> tuple[PortfolioStats, dict[uuid.UUID, dict]]:
    """One grouped query for the whole portfolio, plus per-property breakdowns."""
    query = select(
        Unit.property_id,
        Unit.status,
        func.count(Unit.id),
        func.coalesce(func.sum(Unit.monthly_rent), 0),
    ).where(Unit.is_archived.is_(False))
    query = await _scope_units(db, context, query)
    rows = (await db.execute(query.group_by(Unit.property_id, Unit.status))).all()

    per_property: dict[uuid.UUID, dict] = {}
    # Counts and money are tracked separately; one mixed dict types as `object`
    # and loses every arithmetic guarantee.
    counts: dict[str, int] = {
        "total_units": 0,
        "occupied_units": 0,
        "vacant_units": 0,
        "maintenance_units": 0,
        "reserved_units": 0,
        "vacating_units": 0,
    }
    rent_potential = Decimal("0.00")
    rent_contracted = Decimal("0.00")

    status_key = {
        UnitStatus.OCCUPIED: "occupied_units",
        UnitStatus.VACANT: "vacant_units",
        UnitStatus.UNDER_MAINTENANCE: "maintenance_units",
        UnitStatus.RESERVED: "reserved_units",
        UnitStatus.VACATING: "vacating_units",
    }

    for property_id, unit_status, count, rent_sum in rows:
        bucket = per_property.setdefault(
            property_id,
            {
                "total_units": 0,
                "occupied_units": 0,
                "vacant_units": 0,
                "maintenance_units": 0,
                "reserved_units": 0,
                "vacating_units": 0,
                "monthly_rent_potential": Decimal("0.00"),
            },
        )
        key = status_key[unit_status]
        bucket[key] += count
        bucket["total_units"] += count
        bucket["monthly_rent_potential"] += Decimal(rent_sum)

        counts[key] += count
        counts["total_units"] += count
        rent_potential += Decimal(rent_sum)
        if unit_status in OCCUPYING_STATUSES:
            rent_contracted += Decimal(rent_sum)

    for bucket in per_property.values():
        occupied = bucket["occupied_units"] + bucket["vacating_units"]
        bucket["occupancy_rate"] = (
            round(occupied / bucket["total_units"] * 100, 1) if bucket["total_units"] else 0.0
        )

    occupied_total = counts["occupied_units"] + counts["vacating_units"]
    stats = PortfolioStats(
        total_properties=await _property_count(db, context),
        total_units=counts["total_units"],
        occupied_units=counts["occupied_units"],
        vacant_units=counts["vacant_units"],
        maintenance_units=counts["maintenance_units"],
        reserved_units=counts["reserved_units"],
        vacating_units=counts["vacating_units"],
        occupancy_rate=(
            round(occupied_total / counts["total_units"] * 100, 1) if counts["total_units"] else 0.0
        ),
        monthly_rent_potential=rent_potential,
        monthly_rent_contracted=rent_contracted,
    )
    return stats, per_property


async def _property_count(db: AsyncSession, context: OrgContext) -> int:
    query = select(func.count(Property.id)).where(Property.is_archived.is_(False))
    query = await _scope_properties(db, context, query)
    return int(await db.scalar(query) or 0)


PROPERTY_TYPES = [t.value for t in PropertyType]
