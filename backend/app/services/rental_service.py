"""Vehicle and equipment hire (US-082, US-083).

Three rules run through this module:

  * an asset cannot be in two places at once, so every booking checks the
    calendar for an overlap rather than trusting the status field;
  * an asset with lapsed insurance does not go out, full stop;
  * what is charged at check-in is derived from the two condition snapshots, so
    the hirer can be shown the arithmetic rather than a number.
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.asset import (
    AGREEMENT_TRANSITIONS,
    BLOCKING_STATUSES,
    AgreementStatus,
    AssetKind,
    AssetStatus,
    FuelPolicy,
    RateBasis,
    RentalAgreement,
    RentalAsset,
)
from app.models.tenant import Tenant
from app.services import audit_service, reference_service, tenant_pii

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
PENNY = Decimal("0.01")

# A tank is recorded in eighths, because that is what a fuel gauge shows.
FUEL_EIGHTHS = 8
# What a missing eighth costs when the hirer brings it back emptier than they
# took it. Configurable per organisation would be over-engineering until someone
# asks: a litre of petrol is a litre of petrol.
DEFAULT_FUEL_CHARGE_PER_EIGHTH = Decimal("900.00")


def assert_transition(current: AgreementStatus, target: AgreementStatus) -> None:
    """A hire only moves forward.

    Unlike the maintenance state machine, re-entering the same state is refused
    rather than treated as a no-op: checking an asset out twice would overwrite
    the check-out snapshot, which is the evidence a deposit dispute turns on.
    """
    if target not in AGREEMENT_TRANSITIONS.get(current, ()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"A hire that is {current.value} cannot become {target.value}."),
        )


# ---------------------------------------------------------------------- assets


async def create_asset(
    db: AsyncSession, context: OrgContext, payload, request: Request | None = None
) -> RentalAsset:
    prefix = "VEH" if payload.kind == AssetKind.VEHICLE else "EQP"
    code = await reference_service.generate_reference(db, RentalAsset, context.organization_id, prefix)

    if payload.kind == AssetKind.VEHICLE and payload.registration_number:
        taken = await db.scalar(
            select(RentalAsset.id).where(
                RentalAsset.organization_id == context.organization_id,
                RentalAsset.registration_number == payload.registration_number,
                RentalAsset.is_archived.is_(False),
            )
        )
        if taken:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{payload.registration_number} is already in your fleet",
            )

    asset = RentalAsset(
        organization_id=context.organization_id,
        reference_code=code,
        status=AssetStatus.AVAILABLE,
        **payload.model_dump(exclude={"photo_file_ids"}),
        photo_file_ids=[str(f) for f in payload.photo_file_ids],
    )
    db.add(asset)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="asset.created",
        entity_type="rental_asset",
        entity_id=asset.id,
        actor=context.user,
        summary=f"Added {asset.kind.value} {asset.name} ({code})",
        request=request,
    )
    await db.commit()
    await db.refresh(asset)
    return asset


async def update_asset(
    db: AsyncSession,
    context: OrgContext,
    asset_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> RentalAsset:
    asset = assert_in_org(await db.get(RentalAsset, asset_id), context, label="asset")
    fields = payload.model_dump(exclude_unset=True)

    if "status" in fields and fields["status"] == AssetStatus.AVAILABLE:
        live = await _live_agreement(db, asset.id)
        if live is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{asset.name} is still out on hire {live.reference_code}",
            )

    for field, value in fields.items():
        setattr(asset, field, value)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="asset.updated",
        entity_type="rental_asset",
        entity_id=asset.id,
        actor=context.user,
        summary=f"{asset.reference_code}: updated {', '.join(sorted(fields)) or 'nothing'}",
        request=request,
    )
    await db.commit()
    await db.refresh(asset)
    return asset


async def list_assets(
    db: AsyncSession,
    context: OrgContext,
    *,
    kind: AssetKind | None = None,
    asset_status: AssetStatus | None = None,
    search: str | None = None,
    available_between: tuple[date, date] | None = None,
    limit: int = 200,
) -> list[RentalAsset]:
    query = select(RentalAsset).where(
        RentalAsset.organization_id == context.organization_id,
        RentalAsset.is_archived.is_(False),
    )
    if kind:
        query = query.where(RentalAsset.kind == kind)
    if asset_status:
        query = query.where(RentalAsset.status == asset_status)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                RentalAsset.name.ilike(term),
                RentalAsset.registration_number.ilike(term),
                RentalAsset.serial_number.ilike(term),
                RentalAsset.reference_code.ilike(term),
            )
        )

    rows = list(await db.scalars(query.order_by(RentalAsset.name).limit(limit)))

    if available_between is not None:
        start, end = available_between
        free = []
        for asset in rows:
            if await _overlapping_agreement(db, asset.id, start, end) is None:
                free.append(asset)
        return free
    return rows


async def _live_agreement(db: AsyncSession, asset_id: uuid.UUID) -> RentalAgreement | None:
    return await db.scalar(
        select(RentalAgreement).where(
            RentalAgreement.asset_id == asset_id,
            RentalAgreement.status == AgreementStatus.OUT,
        )
    )


async def _overlapping_agreement(
    db: AsyncSession,
    asset_id: uuid.UUID,
    start: date,
    end: date,
    *,
    exclude: uuid.UUID | None = None,
) -> RentalAgreement | None:
    """Two hires overlap unless one ends before the other starts."""
    query = select(RentalAgreement).where(
        RentalAgreement.asset_id == asset_id,
        RentalAgreement.status.in_(BLOCKING_STATUSES),
        RentalAgreement.start_date <= end,
        RentalAgreement.end_date >= start,
    )
    if exclude:
        query = query.where(RentalAgreement.id != exclude)
    return await db.scalar(query)


async def availability(
    db: AsyncSession, context: OrgContext, asset_id: uuid.UUID, *, day_from: date, day_to: date
) -> list[dict]:
    """The asset's calendar: what is booked, so a clerk can see the gaps."""
    assert_in_org(await db.get(RentalAsset, asset_id), context, label="asset")

    rows = await db.scalars(
        select(RentalAgreement)
        .where(
            RentalAgreement.asset_id == asset_id,
            RentalAgreement.status.in_(BLOCKING_STATUSES),
            RentalAgreement.start_date <= day_to,
            RentalAgreement.end_date >= day_from,
        )
        .order_by(RentalAgreement.start_date)
    )

    booked = []
    for agreement in rows:
        tenant = await db.get(Tenant, agreement.tenant_id)
        booked.append(
            {
                "agreement_id": str(agreement.id),
                "reference_code": agreement.reference_code,
                "start_date": agreement.start_date.isoformat(),
                "end_date": agreement.end_date.isoformat(),
                "status": agreement.status.value,
                "hirer": tenant.full_name if tenant else None,
            }
        )
    return booked


# ------------------------------------------------------------------ agreements


def quote(asset: RentalAsset, basis: RateBasis, days: int) -> Decimal:
    """What the hire costs before any check-in extras.

    A weekly or monthly rate is charged per started period — a nine-day hire on a
    weekly rate is two weeks, which is how the counter quotes it.
    """
    if basis == RateBasis.DAILY:
        return (Decimal(asset.daily_rate) * days).quantize(PENNY)
    if basis == RateBasis.WEEKLY:
        rate = Decimal(asset.weekly_rate or asset.daily_rate * 7)
        weeks = -(-days // 7)
        return (rate * weeks).quantize(PENNY)
    rate = Decimal(asset.monthly_rate or asset.daily_rate * 30)
    months = -(-days // 30)
    return (rate * months).quantize(PENNY)


async def book(
    db: AsyncSession, context: OrgContext, payload, request: Request | None = None
) -> RentalAgreement:
    asset = assert_in_org(await db.get(RentalAsset, payload.asset_id), context, label="asset")
    assert_in_org(await db.get(Tenant, payload.tenant_id), context, label="hirer")

    if asset.status == AssetStatus.RETIRED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{asset.name} has been retired")
    if asset.status == AssetStatus.MAINTENANCE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"{asset.name} is off the road for service"
        )

    clash = await _overlapping_agreement(db, asset.id, payload.start_date, payload.end_date)
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{asset.name} is already booked from {clash.start_date:%d %b} "
                f"to {clash.end_date:%d %b} ({clash.reference_code})"
            ),
        )

    code = await reference_service.generate_reference(db, RentalAgreement, context.organization_id, "HIR")
    days = (payload.end_date - payload.start_date).days + 1
    rate = payload.rate if payload.rate is not None else _rate_for(asset, payload.rate_basis)

    agreement = RentalAgreement(
        organization_id=context.organization_id,
        reference_code=code,
        asset_id=asset.id,
        tenant_id=payload.tenant_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        rate_basis=payload.rate_basis,
        rate=rate,
        deposit_amount=(
            payload.deposit_amount if payload.deposit_amount is not None else Decimal(asset.deposit_amount)
        ),
        status=AgreementStatus.BOOKED,
        notes=payload.notes,
    )
    agreement.hire_charge = quote(asset, payload.rate_basis, days)
    agreement.total_charge = agreement.hire_charge
    db.add(agreement)
    await db.flush()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="hire.booked",
        entity_type="rental_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=(
            f"{code}: {asset.name} booked {payload.start_date:%d %b} to "
            f"{payload.end_date:%d %b} at KES {agreement.hire_charge:,.2f}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


def _rate_for(asset: RentalAsset, basis: RateBasis) -> Decimal:
    if basis == RateBasis.WEEKLY:
        return Decimal(asset.weekly_rate or asset.daily_rate * 7)
    if basis == RateBasis.MONTHLY:
        return Decimal(asset.monthly_rate or asset.daily_rate * 30)
    return Decimal(asset.daily_rate)


async def check_out(
    db: AsyncSession,
    context: OrgContext,
    agreement_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> RentalAgreement:
    """Hand the asset over, recording its condition as it leaves (US-082)."""
    agreement = assert_in_org(await db.get(RentalAgreement, agreement_id), context, label="agreement")
    assert_transition(agreement.status, AgreementStatus.OUT)

    asset = await db.get(RentalAsset, agreement.asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    # An asset whose insurance has lapsed does not go out. This is the one check
    # in the module that is worth losing a booking over.
    expired = [
        warning for warning in asset.compliance_warnings if "expired" in warning or "overdue" in warning
    ]
    if expired and not payload.override_compliance:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{asset.name} cannot go out: {'; '.join(expired)}. "
                "Renew it, or override with a written reason if you accept the risk."
            ),
        )

    now = datetime.now(UTC)
    agreement.status = AgreementStatus.OUT
    agreement.checked_out_at = now
    agreement.checked_out_by_id = context.user.id
    agreement.mileage_out = payload.mileage
    agreement.fuel_out_eighths = payload.fuel_eighths
    agreement.condition_out = payload.condition_notes
    agreement.photos_out = [str(f) for f in payload.photo_file_ids]
    if payload.driver_licence_file_id:
        agreement.driver_licence_file_id = payload.driver_licence_file_id

    asset.status = AssetStatus.ON_HIRE
    if payload.mileage is not None:
        asset.mileage = payload.mileage

    document = await _render_agreement(db, agreement, asset)
    if document is not None:
        agreement.agreement_document_id = document.id

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="hire.checked_out",
        entity_type="rental_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=(
            f"{agreement.reference_code}: {asset.name} handed over"
            + (f" at {payload.mileage:,} km" if payload.mileage is not None else "")
            + (
                f" (compliance overridden: {payload.override_reason})"
                if expired and payload.override_compliance
                else ""
            )
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


async def _render_agreement(db: AsyncSession, agreement: RentalAgreement, asset: RentalAsset):
    """The signed hire agreement, filed against the hirer.

    Rendered at hand-over rather than at booking, so it carries the condition
    the asset was actually in when it left.
    """
    from app.models.file import FileCategory
    from app.models.organization import Organization
    from app.services import file_service, pdf_service

    hirer = await db.get(Tenant, agreement.tenant_id)
    organization = await db.get(Organization, agreement.organization_id)
    if not (hirer and organization):
        return None

    hirer.national_id = await tenant_pii.decrypt_national_id(db, hirer)

    try:
        pdf_bytes = pdf_service.render_pdf(
            "rental_agreement.html",
            {
                "organization": organization,
                "logo_url": None,
                "agreement": agreement,
                "asset": asset,
                "hirer": hirer,
                "generated_at": date.today(),
            },
        )
    except Exception:  # noqa: BLE001 — the hire stands without the paperwork
        logger.exception("Hire agreement rendering failed for %s", agreement.reference_code)
        return None

    return await file_service.register_generated(
        db,
        agreement.organization_id,
        data=pdf_bytes,
        filename=f"Hire-{agreement.reference_code}.pdf",
        category=FileCategory.LEASE,
        entity_type="tenant",
        entity_id=hirer.id,
    )


async def check_in(
    db: AsyncSession,
    context: OrgContext,
    agreement_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> RentalAgreement:
    """Take the asset back, compare the two snapshots and price the difference."""
    agreement = assert_in_org(await db.get(RentalAgreement, agreement_id), context, label="agreement")
    assert_transition(agreement.status, AgreementStatus.RETURNED)

    asset = await db.get(RentalAsset, agreement.asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    if payload.mileage is not None and agreement.mileage_out is not None:
        if payload.mileage < agreement.mileage_out:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"The odometer reads less than at check-out "
                    f"({payload.mileage:,} < {agreement.mileage_out:,} km)"
                ),
            )

    now = datetime.now(UTC)
    agreement.status = AgreementStatus.RETURNED
    agreement.checked_in_at = now
    agreement.checked_in_by_id = context.user.id
    agreement.mileage_in = payload.mileage
    agreement.fuel_in_eighths = payload.fuel_eighths
    agreement.condition_in = payload.condition_notes
    agreement.photos_in = [str(f) for f in payload.photo_file_ids]
    agreement.damage_charge = payload.damage_charge or ZERO

    charges = _price_return(asset, agreement, returned_on=payload.returned_on or date.today())
    agreement.excess_mileage_charge = charges["excess_mileage"]
    agreement.fuel_charge = charges["fuel"]
    agreement.late_charge = charges["late"]
    agreement.total_charge = (
        Decimal(agreement.hire_charge)
        + agreement.excess_mileage_charge
        + agreement.fuel_charge
        + agreement.late_charge
        + Decimal(agreement.damage_charge)
    ).quantize(PENNY)

    # What the hirer gets back, floored at zero: a deposit covers the extras, it
    # does not go negative.
    extras = agreement.total_charge - Decimal(agreement.hire_charge)
    agreement.deposit_refunded = max(Decimal(agreement.deposit_amount) - extras, ZERO)

    asset.status = AssetStatus.AVAILABLE
    if payload.mileage is not None:
        asset.mileage = payload.mileage

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="hire.checked_in",
        entity_type="rental_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=(
            f"{agreement.reference_code}: {asset.name} returned, "
            f"total KES {agreement.total_charge:,.2f}, "
            f"deposit refund KES {agreement.deposit_refunded:,.2f}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


def _price_return(asset: RentalAsset, agreement: RentalAgreement, *, returned_on: date) -> dict[str, Decimal]:
    """Everything owed beyond the agreed hire, itemised so it can be shown."""
    excess_mileage = ZERO
    if asset.daily_mileage_limit and asset.excess_mileage_rate and agreement.mileage_covered is not None:
        allowed = asset.daily_mileage_limit * agreement.hire_days
        over = agreement.mileage_covered - allowed
        if over > 0:
            excess_mileage = (Decimal(over) * Decimal(asset.excess_mileage_rate)).quantize(PENNY)

    fuel = ZERO
    if (
        asset.kind == AssetKind.VEHICLE
        and asset.fuel_policy != FuelPolicy.PREPAID
        and agreement.fuel_out_eighths is not None
        and agreement.fuel_in_eighths is not None
    ):
        expected = (
            FUEL_EIGHTHS if asset.fuel_policy == FuelPolicy.FULL_TO_FULL else agreement.fuel_out_eighths
        )
        missing = expected - agreement.fuel_in_eighths
        if missing > 0:
            fuel = (Decimal(missing) * DEFAULT_FUEL_CHARGE_PER_EIGHTH).quantize(PENNY)

    late = ZERO
    if returned_on > agreement.end_date:
        days_late = (returned_on - agreement.end_date).days
        late = (Decimal(asset.daily_rate) * days_late).quantize(PENNY)

    return {"excess_mileage": excess_mileage, "fuel": fuel, "late": late}


async def cancel(
    db: AsyncSession,
    context: OrgContext,
    agreement_id: uuid.UUID,
    reason: str | None = None,
    request: Request | None = None,
) -> RentalAgreement:
    agreement = assert_in_org(await db.get(RentalAgreement, agreement_id), context, label="agreement")
    assert_transition(agreement.status, AgreementStatus.CANCELLED)

    agreement.status = AgreementStatus.CANCELLED
    agreement.cancelled_reason = reason

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="hire.cancelled",
        entity_type="rental_agreement",
        entity_id=agreement.id,
        actor=context.user,
        summary=f"{agreement.reference_code} cancelled" + (f": {reason}" if reason else ""),
        request=request,
    )
    await db.commit()
    await db.refresh(agreement)
    return agreement


async def list_agreements(
    db: AsyncSession,
    context: OrgContext,
    *,
    asset_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    agreement_status: AgreementStatus | None = None,
    overdue_only: bool = False,
    limit: int = 200,
) -> list[RentalAgreement]:
    query = select(RentalAgreement).where(RentalAgreement.organization_id == context.organization_id)
    if asset_id:
        query = query.where(RentalAgreement.asset_id == asset_id)
    if tenant_id:
        query = query.where(RentalAgreement.tenant_id == tenant_id)
    if agreement_status:
        query = query.where(RentalAgreement.status == agreement_status)
    if overdue_only:
        query = query.where(
            RentalAgreement.status == AgreementStatus.OUT,
            RentalAgreement.end_date < date.today(),
        )

    rows = await db.scalars(query.order_by(RentalAgreement.start_date.desc()).limit(limit))
    return list(rows)


async def fleet_overview(db: AsyncSession, context: OrgContext) -> dict:
    """The counter's morning screen: what is out, what is free, what is illegal."""
    assets = await list_assets(db, context, limit=500)

    out = len([asset for asset in assets if asset.status == AssetStatus.ON_HIRE])
    maintenance = len([asset for asset in assets if asset.status == AssetStatus.MAINTENANCE])
    warnings = [
        {
            "asset_id": str(asset.id),
            "name": asset.name,
            "reference_code": asset.reference_code,
            "kind": asset.kind.value,
            "warnings": asset.compliance_warnings,
        }
        for asset in assets
        if asset.compliance_warnings
    ]

    overdue = await list_agreements(db, context, overdue_only=True)
    revenue = Decimal(
        str(
            await db.scalar(
                select(func.coalesce(func.sum(RentalAgreement.total_charge), 0)).where(
                    RentalAgreement.organization_id == context.organization_id,
                    RentalAgreement.status == AgreementStatus.RETURNED,
                    func.date(RentalAgreement.checked_in_at) >= date.today().replace(day=1),
                )
            )
            or 0
        )
    )

    return {
        "total_assets": len(assets),
        "vehicles": len([a for a in assets if a.kind == AssetKind.VEHICLE]),
        "equipment": len([a for a in assets if a.kind == AssetKind.EQUIPMENT]),
        "on_hire": out,
        "available": len(assets) - out - maintenance,
        "in_maintenance": maintenance,
        "overdue_returns": len(overdue),
        "revenue_this_month": float(revenue),
        "compliance_warnings": warnings,
    }
