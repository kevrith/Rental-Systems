"""Advanced analytics service — Phase 2 (US-054).

Financial intelligence, property performance, and predictive forecasting.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.operations import BILLABLE_STATUSES, MaintenanceRequest, MeterReading, MeterType
from app.models.property import Property, Unit, UnitStatus
from app.models.renewal import LeaseRenewal, RenewalStatus
from app.models.tenant import Tenancy, TenancyStatus, Tenant

ZERO = Decimal("0.00")


def _month_bounds(anchor: date, offset: int) -> tuple[date, date]:
    """First and last day of the month `offset` months before `anchor`."""
    total = anchor.year * 12 + (anchor.month - 1) - offset
    year, month = divmod(total, 12)
    first = date(year, month + 1, 1)
    last = (date(year + 1, 1, 1) if month == 11 else date(year, month + 2, 1)) - timedelta(days=1)
    return first, last


async def revenue_analytics(
    db: AsyncSession,
    organization_id: uuid.UUID,
    months: int = 6,
) -> list[dict]:
    """Monthly collected against billed for the last N months.

    Two grouped queries rather than two per month: this is the dashboard's first
    call, and a per-month loop turned a 6-month chart into 12 round trips.
    """
    months = max(1, min(months, 36))
    today = date.today()
    window_start, _ = _month_bounds(today, months - 1)

    collected_rows = await db.execute(
        select(
            func.date_trunc("month", func.cast(Payment.payment_date, Date)).label("bucket"),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.payment_date >= window_start,
        )
        .group_by("bucket")
    )
    collected_by_month = {row[0].date(): Decimal(row[1]) for row in collected_rows}

    expected_rows = await db.execute(
        select(
            func.date_trunc("month", func.cast(Invoice.period_start, Date)).label("bucket"),
            func.coalesce(func.sum(Invoice.total), 0),
        )
        .where(
            Invoice.organization_id == organization_id,
            Invoice.period_start >= window_start,
        )
        .group_by("bucket")
    )
    expected_by_month = {row[0].date(): Decimal(row[1]) for row in expected_rows}

    result = []
    for offset in range(months - 1, -1, -1):
        first, _ = _month_bounds(today, offset)
        collected = collected_by_month.get(first, ZERO)
        expected = expected_by_month.get(first, ZERO)
        result.append(
            {
                "month": first.strftime("%b %Y"),
                "month_start": first.isoformat(),
                "collected": float(collected),
                "expected": float(expected),
                "collection_rate": (round(float(collected) / float(expected) * 100, 1) if expected else 0.0),
            }
        )
    return result


async def property_performance(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> list[dict]:
    """Per-property collection rate, occupancy and maintenance spend this month.

    Five grouped queries regardless of portfolio size. The previous shape ran
    four queries per property, so a 60-property agency paid 240 round trips to
    open one screen.
    """
    today = date.today()
    month_start = today.replace(day=1)

    properties = list(
        await db.scalars(
            select(Property).where(
                Property.organization_id == organization_id,
                Property.is_archived.is_(False),
            )
        )
    )
    if not properties:
        return []

    property_ids = [p.id for p in properties]

    # unit -> property, and the occupancy tally, in one pass.
    unit_rows = list(
        await db.execute(
            select(Unit.id, Unit.property_id, Unit.status).where(
                Unit.organization_id == organization_id,
                Unit.property_id.in_(property_ids),
                Unit.is_archived.is_(False),
            )
        )
    )
    property_of_unit = {unit_id: property_id for unit_id, property_id, _ in unit_rows}
    unit_counts: dict[uuid.UUID, int] = {}
    occupied_counts: dict[uuid.UUID, int] = {}
    for _, property_id, unit_status in unit_rows:
        unit_counts[property_id] = unit_counts.get(property_id, 0) + 1
        if unit_status == UnitStatus.OCCUPIED:
            occupied_counts[property_id] = occupied_counts.get(property_id, 0) + 1

    unit_ids = list(property_of_unit)
    collected: dict[uuid.UUID, Decimal] = {}
    expected: dict[uuid.UUID, Decimal] = {}
    maintenance: dict[uuid.UUID, Decimal] = {}

    if unit_ids:
        payment_rows = await db.execute(
            select(Tenancy.unit_id, func.coalesce(func.sum(Payment.amount), 0))
            .join(Tenancy, Tenancy.id == Payment.tenancy_id)
            .where(
                Payment.organization_id == organization_id,
                Payment.status == PaymentStatus.CONFIRMED,
                Tenancy.unit_id.in_(unit_ids),
                Payment.payment_date >= month_start,
            )
            .group_by(Tenancy.unit_id)
        )
        for unit_id, total in payment_rows:
            property_id = property_of_unit[unit_id]
            collected[property_id] = collected.get(property_id, ZERO) + Decimal(total)

        invoice_rows = await db.execute(
            select(Tenancy.unit_id, func.coalesce(func.sum(Invoice.total), 0))
            .join(Tenancy, Tenancy.id == Invoice.tenancy_id)
            .where(
                Invoice.organization_id == organization_id,
                Tenancy.unit_id.in_(unit_ids),
                Invoice.period_start >= month_start,
            )
            .group_by(Tenancy.unit_id)
        )
        for unit_id, total in invoice_rows:
            property_id = property_of_unit[unit_id]
            expected[property_id] = expected.get(property_id, ZERO) + Decimal(total)

        maintenance_rows = await db.execute(
            select(
                MaintenanceRequest.unit_id,
                func.coalesce(func.sum(MaintenanceRequest.cost), 0),
            )
            .where(
                MaintenanceRequest.organization_id == organization_id,
                MaintenanceRequest.unit_id.in_(unit_ids),
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.cost.is_not(None),
            )
            .group_by(MaintenanceRequest.unit_id)
        )
        for unit_id, total in maintenance_rows:
            property_id = property_of_unit[unit_id]
            maintenance[property_id] = maintenance.get(property_id, ZERO) + Decimal(total)

    result: list[dict[str, Any]] = []
    for prop in properties:
        units = unit_counts.get(prop.id, 0)
        occupied = occupied_counts.get(prop.id, 0)
        billed = expected.get(prop.id, ZERO)
        paid = collected.get(prop.id, ZERO)
        result.append(
            {
                "property_id": str(prop.id),
                "property_name": prop.name,
                "total_units": units,
                "occupied_units": occupied,
                "occupancy_rate": round(occupied / units * 100, 1) if units else 0.0,
                "collected_this_month": float(paid),
                "expected_this_month": float(billed),
                "collection_rate": round(float(paid) / float(billed) * 100, 1) if billed else 0.0,
                "total_maintenance_cost": float(maintenance.get(prop.id, ZERO)),
            }
        )

    result.sort(key=lambda row: float(row["collection_rate"]), reverse=True)
    return result


async def cash_flow_forecast(
    db: AsyncSession,
    organization_id: uuid.UUID,
    months_ahead: int = 3,
) -> list[dict]:
    """Project income for the next N months based on active tenancies."""
    today = date.today()

    active_rent = (
        await db.scalar(
            select(func.coalesce(func.sum(Tenancy.monthly_rent), 0)).where(
                Tenancy.organization_id == organization_id,
                Tenancy.status.in_([TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON]),
            )
        )
        or ZERO
    )

    three_months_ago = date(
        today.year if today.month > 3 else today.year - 1,
        (today.month - 3) % 12 or 12,
        1,
    )
    collected_3m = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == organization_id,
                Payment.status == PaymentStatus.CONFIRMED,
                Payment.payment_date >= three_months_ago,
            )
        )
        or ZERO
    )
    expected_3m = (
        await db.scalar(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.organization_id == organization_id,
                Invoice.period_start >= three_months_ago,
            )
        )
        or ZERO
    )
    collection_rate = float(collected_3m) / float(expected_3m) if expected_3m else 0.85

    result = []
    for i in range(1, months_ahead + 1):
        month = today.month + i
        year = today.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        first = date(year, month, 1)
        result.append(
            {
                "month": first.strftime("%b %Y"),
                "projected_income": round(float(active_rent) * collection_rate, 2),
                "collection_rate_assumption": round(collection_rate * 100, 1),
                "active_rent_roll": float(active_rent),
            }
        )
    return result


async def expiring_leases_forecast(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> dict:
    """Leases expiring in 30, 60, 90 days."""
    today = date.today()
    result = {}
    for days in [30, 60, 90]:
        target = today + timedelta(days=days)
        count = (
            await db.scalar(
                select(func.count(Tenancy.id)).where(
                    Tenancy.organization_id == organization_id,
                    Tenancy.end_date <= target,
                    Tenancy.end_date >= today,
                    Tenancy.status.in_([TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON]),
                )
            )
            or 0
        )
        result[f"expiring_in_{days}_days"] = count
    return result


async def maintenance_analytics(
    db: AsyncSession,
    organization_id: uuid.UUID,
) -> dict:
    """Maintenance cost breakdown and spike detection."""
    today = date.today()
    month_start = today.replace(day=1)
    three_months_ago = date(
        today.year if today.month > 3 else today.year - 1,
        (today.month - 3) % 12 or 12,
        1,
    )

    this_month_cost = (
        await db.scalar(
            select(func.coalesce(func.sum(MaintenanceRequest.cost), 0)).where(
                MaintenanceRequest.organization_id == organization_id,
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.cost.is_not(None),
                MaintenanceRequest.completed_at >= month_start,
            )
        )
        or ZERO
    )

    three_month_total = (
        await db.scalar(
            select(func.coalesce(func.sum(MaintenanceRequest.cost), 0)).where(
                MaintenanceRequest.organization_id == organization_id,
                MaintenanceRequest.status.in_(BILLABLE_STATUSES),
                MaintenanceRequest.cost.is_not(None),
                MaintenanceRequest.completed_at >= three_months_ago,
            )
        )
        or ZERO
    )
    avg_monthly = Decimal(str(three_month_total)) / 3

    spike_alert = Decimal(str(this_month_cost)) > avg_monthly * Decimal("1.5") if avg_monthly > 0 else False

    return {
        "this_month_cost": float(this_month_cost),
        "avg_monthly_cost_3m": float(avg_monthly),
        "spike_alert": spike_alert,
    }


async def vacancy_risk_forecast(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    days_ahead: int = 90,
) -> list[dict]:
    """Tenancies expiring soon with no sign the tenant is staying (US-095).

    `expiring_leases_forecast` above counts every lease ending in the window —
    this is narrower: it drops anything already OFFERED or ACCEPTED a renewal
    (Sprint 12's `LeaseRenewal`), so what is left is expiry with no renewal
    intention on record, not just expiry.
    """
    today = date.today()
    horizon = today + timedelta(days=days_ahead)

    candidates = (
        await db.execute(
            select(Tenancy, Tenant, Unit, Property)
            .join(Tenant, Tenant.id == Tenancy.tenant_id)
            .join(Unit, Unit.id == Tenancy.unit_id)
            .join(Property, Property.id == Unit.property_id)
            .where(
                Tenancy.organization_id == organization_id,
                Tenancy.status.in_([TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON]),
                Tenancy.end_date.is_not(None),
                Tenancy.end_date >= today,
                Tenancy.end_date <= horizon,
            )
        )
    ).all()
    if not candidates:
        return []

    tenancy_ids = [tenancy.id for tenancy, *_ in candidates]
    renewal_rows = await db.execute(
        select(LeaseRenewal.tenancy_id, LeaseRenewal.status).where(
            LeaseRenewal.organization_id == organization_id,
            LeaseRenewal.tenancy_id.in_(tenancy_ids),
        )
    )
    statuses_by_tenancy: dict[uuid.UUID, set[RenewalStatus]] = {}
    for tenancy_id, renewal_status in renewal_rows:
        statuses_by_tenancy.setdefault(tenancy_id, set()).add(renewal_status)

    result = []
    for tenancy, tenant, unit, prop in candidates:
        statuses = statuses_by_tenancy.get(tenancy.id, set())
        if statuses & {RenewalStatus.OFFERED, RenewalStatus.ACCEPTED}:
            continue
        renewal_state = (
            "declined"
            if RenewalStatus.DECLINED in statuses
            else ("lapsed" if RenewalStatus.LAPSED in statuses else "none")
        )
        result.append(
            {
                "tenancy_id": str(tenancy.id),
                "tenant_name": tenant.full_name,
                "property_name": prop.name,
                "unit_number": unit.unit_number,
                "end_date": tenancy.end_date.isoformat(),
                "days_until_expiry": (tenancy.end_date - today).days,
                "monthly_rent": float(tenancy.monthly_rent),
                "renewal_state": renewal_state,
            }
        )

    result.sort(key=lambda row: row["days_until_expiry"])
    return result


async def rent_review_suggestions(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    min_months: int = 12,
) -> list[dict]:
    """Units whose rent hasn't moved in `min_months`+ (US-095).

    "Market average" here is a portfolio-internal proxy — the average rent
    this organisation charges on other active units with the same bedroom
    count — not external market data. Callers should present it as an
    estimate from the owner's own portfolio, not a market survey.
    """
    today = date.today()

    candidates = (
        await db.execute(
            select(Tenancy, Tenant, Unit, Property)
            .join(Tenant, Tenant.id == Tenancy.tenant_id)
            .join(Unit, Unit.id == Tenancy.unit_id)
            .join(Property, Property.id == Unit.property_id)
            .where(
                Tenancy.organization_id == organization_id,
                Tenancy.status.in_([TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON]),
            )
        )
    ).all()
    if not candidates:
        return []

    tenancy_ids = [tenancy.id for tenancy, *_ in candidates]
    renewal_rows = await db.execute(
        select(LeaseRenewal.tenancy_id, func.max(LeaseRenewal.new_start_date))
        .where(
            LeaseRenewal.organization_id == organization_id,
            LeaseRenewal.tenancy_id.in_(tenancy_ids),
            LeaseRenewal.status == RenewalStatus.ACCEPTED,
        )
        .group_by(LeaseRenewal.tenancy_id)
    )
    latest_accepted: dict[uuid.UUID, date] = {
        tenancy_id: new_start_date for tenancy_id, new_start_date in renewal_rows
    }

    rent_by_bedrooms: dict[int | None, list[Decimal]] = {}
    for tenancy, _tenant, unit, _prop in candidates:
        rent_by_bedrooms.setdefault(unit.bedrooms, []).append(Decimal(tenancy.monthly_rent))
    avg_by_bedrooms = {
        bedrooms: sum(rents, ZERO) / len(rents) for bedrooms, rents in rent_by_bedrooms.items()
    }

    result = []
    for tenancy, tenant, unit, prop in candidates:
        last_change = latest_accepted.get(tenancy.id) or tenancy.start_date
        months_since = (today.year - last_change.year) * 12 + (today.month - last_change.month)
        if months_since < min_months:
            continue

        rent = Decimal(tenancy.monthly_rent)
        avg_rent = avg_by_bedrooms.get(unit.bedrooms, rent)
        percent_vs_average = round(float((rent - avg_rent) / avg_rent * 100), 1) if avg_rent > 0 else 0.0

        result.append(
            {
                "tenancy_id": str(tenancy.id),
                "tenant_name": tenant.full_name,
                "property_name": prop.name,
                "unit_number": unit.unit_number,
                "monthly_rent": float(rent),
                "months_since_last_change": months_since,
                "last_change_date": last_change.isoformat(),
                "portfolio_avg_rent_same_type": float(avg_rent),
                "percent_vs_portfolio_average": percent_vs_average,
            }
        )

    result.sort(key=lambda row: row["months_since_last_change"], reverse=True)
    return result


async def utility_analytics(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    months: int = 6,
    above_average_multiplier: float = 1.5,
) -> dict:
    """Consumption trends, heavy-consumption units and billing efficiency (US-054).

    Consumption is already computed and frozen on each `MeterReading` at capture
    time (`operations_service.record_meter_reading`), so this never recomputes
    it from a rate that may since have changed — it only aggregates what was
    actually read and what was actually billed.

    "Billing efficiency" is the gap between the two: a reading with no
    `billed_invoice_id` is money measured and never charged, which is the
    single most common way utility revenue leaks out of a manual process.
    """
    months = max(1, min(months, 36))
    today = date.today()
    window_start, _ = _month_bounds(today, months - 1)

    readings = (
        await db.execute(
            select(MeterReading, Unit, Property)
            .join(Unit, Unit.id == MeterReading.unit_id)
            .join(Property, Property.id == Unit.property_id)
            .where(
                MeterReading.organization_id == organization_id,
                MeterReading.reading_date >= window_start,
            )
        )
    ).all()

    # month -> meter type -> (consumption, amount)
    trend: dict[date, dict[MeterType, list[Decimal]]] = {}
    readings_taken = 0
    readings_billed = 0
    amount_read = ZERO
    amount_billed = ZERO
    # (property id, meter type) -> consumptions, for the peer average below.
    peers: dict[tuple[uuid.UUID, MeterType], list[Decimal]] = {}
    org_peers: dict[MeterType, list[Decimal]] = {}
    # (unit id, meter type) -> the most recent reading for that meter.
    latest: dict[tuple[uuid.UUID, MeterType], tuple[MeterReading, Unit, Property]] = {}

    for reading, unit, prop in readings:
        bucket = reading.reading_date.replace(day=1)
        totals = trend.setdefault(bucket, {}).setdefault(reading.meter_type, [ZERO, ZERO])
        consumption = Decimal(reading.consumption)
        amount = Decimal(reading.amount)
        totals[0] += consumption
        totals[1] += amount

        readings_taken += 1
        amount_read += amount
        if reading.billed_invoice_id is not None:
            readings_billed += 1
            amount_billed += amount

        peers.setdefault((prop.id, reading.meter_type), []).append(consumption)
        org_peers.setdefault(reading.meter_type, []).append(consumption)

        key = (unit.id, reading.meter_type)
        current = latest.get(key)
        if current is None or reading.reading_date > current[0].reading_date:
            latest[key] = (reading, unit, prop)

    trend_rows = []
    for offset in range(months - 1, -1, -1):
        first, _ = _month_bounds(today, offset)
        by_type = trend.get(first, {})
        water = by_type.get(MeterType.WATER, [ZERO, ZERO])
        electricity = by_type.get(MeterType.ELECTRICITY, [ZERO, ZERO])
        trend_rows.append(
            {
                "month": first.strftime("%b %Y"),
                "month_start": first.isoformat(),
                "water_consumption": float(water[0]),
                "water_amount": float(water[1]),
                "electricity_consumption": float(electricity[0]),
                "electricity_amount": float(electricity[1]),
            }
        )

    # A property with only one or two metered units has no meaningful internal
    # average, so those fall back to the organisation-wide one.
    MIN_PEERS = 3
    flagged: list[dict[str, Any]] = []
    for (unit_id, meter_type), (reading, unit, prop) in latest.items():
        sample = peers.get((prop.id, meter_type), [])
        scope = "property"
        if len(sample) < MIN_PEERS:
            sample = org_peers.get(meter_type, [])
            scope = "portfolio"
        if len(sample) < MIN_PEERS:
            continue

        average = sum(sample, ZERO) / len(sample)
        consumption = Decimal(reading.consumption)
        if average <= 0 or consumption <= average * Decimal(str(above_average_multiplier)):
            continue

        flagged.append(
            {
                "unit_id": str(unit_id),
                "unit_number": unit.unit_number,
                "property_name": prop.name,
                "meter_type": meter_type.value,
                "reading_date": reading.reading_date.isoformat(),
                "consumption": float(consumption),
                "peer_average": round(float(average), 2),
                "peer_scope": scope,
                "percent_above_average": round(float((consumption - average) / average * 100), 1),
                "amount": float(reading.amount),
            }
        )

    flagged.sort(key=lambda row: float(row["percent_above_average"]), reverse=True)

    return {
        "months": months,
        "trend": trend_rows,
        "billing_efficiency": {
            "readings_taken": readings_taken,
            "readings_billed": readings_billed,
            "billed_percent": (round(readings_billed / readings_taken * 100, 1) if readings_taken else 0.0),
            "amount_read": float(amount_read),
            "amount_billed": float(amount_billed),
            "amount_unbilled": float(amount_read - amount_billed),
        },
        "high_consumption_units": flagged,
        "above_average_multiplier": above_average_multiplier,
    }


# Segment thresholds. Named rather than inlined because the boundary between
# "occasionally late" and "chronic" is a judgement call a landlord may want to
# argue with, and it should be visible in one place when they do.
CHRONIC_LATE_RATIO = 0.5
NON_PAYING_OVERDUE_INVOICES = 2


def _settlement_dates(invoices: list[Invoice], payments: list[Payment]) -> dict[uuid.UUID, date | None]:
    """Replay oldest-invoice-first allocation to date each invoice's settlement.

    `payment_service._allocate` applies money to the oldest open invoice first,
    and `Invoice.amount_paid` records the outcome but not the day it happened.
    Replaying the same policy over the tenancy's whole history recovers the
    missing date: the payment that tipped an invoice's cumulative allocation to
    its full total is the day it was settled.

    Invoices never fully covered map to None — they are outstanding, not late.
    """
    outstanding = {invoice.id: Decimal(invoice.total) for invoice in invoices}
    # A zero-total invoice needs no payment to be settled, and is dated to its
    # own due date. Without this it would fall through the loop below with no
    # settlement date and be reported as unpaid, which is how a tenant who owes
    # nothing ends up in the non-paying segment.
    settled: dict[uuid.UUID, date | None] = {
        invoice.id: (invoice.due_date if Decimal(invoice.total) <= ZERO else None) for invoice in invoices
    }
    order = sorted(invoices, key=lambda inv: (inv.due_date, inv.period_start))

    for payment in payments:
        remaining = Decimal(payment.amount)
        paid_on = payment.payment_date or (payment.paid_at.date() if payment.paid_at else None)
        for invoice in order:
            if remaining <= 0:
                break
            owed = outstanding[invoice.id]
            if owed <= 0:
                continue
            applied = min(owed, remaining)
            outstanding[invoice.id] = owed - applied
            remaining -= applied
            if outstanding[invoice.id] <= 0:
                settled[invoice.id] = paid_on

    return settled


async def payment_behaviour_segments(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    months: int = 6,
) -> dict:
    """Group tenancies by how reliably they actually pay (US-054).

    The arrears report answers "who owes money today". This answers the
    different question of "who is a problem" — a tenant who clears every
    invoice three weeks late is never in the top-defaulters list yet costs the
    landlord the same cash-flow pain every single month.

    Only invoices already past their due date are assessed; an invoice issued
    this week cannot make anyone late.
    """
    months = max(1, min(months, 36))
    today = date.today()
    window_start, _ = _month_bounds(today, months - 1)

    rows = (
        await db.execute(
            select(Tenancy, Tenant, Unit, Property)
            .join(Tenant, Tenant.id == Tenancy.tenant_id)
            .join(Unit, Unit.id == Tenancy.unit_id)
            .join(Property, Property.id == Unit.property_id)
            .where(
                Tenancy.organization_id == organization_id,
                Tenancy.status.in_(
                    [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]
                ),
            )
        )
    ).all()
    if not rows:
        return {"months": months, "segments": {}, "tenancies": []}

    tenancy_ids = [tenancy.id for tenancy, *_ in rows]

    # The whole history, not just the window: allocation is oldest-first, so a
    # payment made this month may be settling last year's invoice, and dating
    # the window's invoices correctly requires seeing what came before them.
    invoices_by_tenancy: dict[uuid.UUID, list[Invoice]] = {}
    for invoice in await db.scalars(
        select(Invoice).where(
            Invoice.organization_id == organization_id,
            Invoice.tenancy_id.in_(tenancy_ids),
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    ):
        invoices_by_tenancy.setdefault(invoice.tenancy_id, []).append(invoice)

    payments_by_tenancy: dict[uuid.UUID, list[Payment]] = {}
    for payment in await db.scalars(
        select(Payment)
        .where(
            Payment.organization_id == organization_id,
            Payment.tenancy_id.in_(tenancy_ids),
            Payment.status == PaymentStatus.CONFIRMED,
        )
        .order_by(Payment.payment_date, Payment.created_at)
    ):
        payments_by_tenancy.setdefault(payment.tenancy_id, []).append(payment)

    segments = {
        "on_time": 0,
        "occasionally_late": 0,
        "chronically_late": 0,
        "non_paying": 0,
        "no_history": 0,
    }
    result: list[dict[str, Any]] = []

    for tenancy, tenant, unit, prop in rows:
        invoices = invoices_by_tenancy.get(tenancy.id, [])
        settled = _settlement_dates(invoices, payments_by_tenancy.get(tenancy.id, []))

        assessed = [
            invoice
            for invoice in invoices
            if invoice.period_start >= window_start and invoice.due_date <= today
        ]
        on_time = 0
        late_days: list[int] = []
        overdue_unpaid = 0
        for invoice in assessed:
            settled_on = settled.get(invoice.id)
            if settled_on is None:
                overdue_unpaid += 1
            elif settled_on <= invoice.due_date:
                on_time += 1
            else:
                late_days.append((settled_on - invoice.due_date).days)

        outstanding = sum(
            (Decimal(invoice.total) - Decimal(invoice.amount_paid) for invoice in invoices),
            ZERO,
        )
        outstanding = max(outstanding, ZERO)
        rent = Decimal(tenancy.monthly_rent)

        if not assessed:
            segment = "no_history"
        elif overdue_unpaid >= NON_PAYING_OVERDUE_INVOICES or (rent > 0 and outstanding >= rent * 2):
            segment = "non_paying"
        elif len(late_days) / len(assessed) >= CHRONIC_LATE_RATIO:
            segment = "chronically_late"
        elif late_days:
            segment = "occasionally_late"
        else:
            segment = "on_time"

        segments[segment] += 1
        result.append(
            {
                "tenancy_id": str(tenancy.id),
                "tenant_name": tenant.full_name,
                "property_name": prop.name,
                "unit_number": unit.unit_number,
                "segment": segment,
                "invoices_assessed": len(assessed),
                "paid_on_time": on_time,
                "paid_late": len(late_days),
                "still_unpaid": overdue_unpaid,
                "average_days_late": round(sum(late_days) / len(late_days), 1) if late_days else 0.0,
                "worst_days_late": max(late_days) if late_days else 0,
                "outstanding_balance": float(outstanding),
                "monthly_rent": float(rent),
            }
        )

    severity = {"non_paying": 0, "chronically_late": 1, "occasionally_late": 2, "on_time": 3, "no_history": 4}
    result.sort(key=lambda row: (severity[str(row["segment"])], -float(row["outstanding_balance"])))
    return {"months": months, "segments": segments, "tenancies": result}


ENDED_STATUSES: tuple[TenancyStatus, ...] = (TenancyStatus.VACATED, TenancyStatus.EXPIRED)
LIVE_STATUSES: tuple[TenancyStatus, ...] = (
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
)


def _ended_on(tenancy: Tenancy) -> date | None:
    """The day a tenancy actually finished, from whichever field recorded it.

    `vacated_at` is set when someone confirms the move-out, `move_out_date` when
    a notice is served, `end_date` is the lease term. They are checked in that
    order — the most specific record of what happened wins.
    """
    if tenancy.vacated_at is not None:
        return tenancy.vacated_at.date()
    return tenancy.move_out_date or tenancy.end_date


def _months_between(start: date, end: date) -> float:
    return max((end - start).days, 0) / 30.44


async def tenant_turnover(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    months: int = 12,
) -> dict:
    """How often tenants leave, and how long they stay (Module 12).

    Turnover rate is expressed against the tenancies actually held during the
    window — the live ones plus the ones that ended in it — rather than against
    unit count. A landlord with empty units should not look like they have low
    turnover simply because there was nobody there to leave.

    Average tenancy length is reported two ways on purpose: over the tenancies
    that ended in the window (what churn costs right now) and over every
    tenancy ever ended (the long-run number, which a young portfolio will not
    have enough history to trust).
    """
    months = max(1, min(months, 60))
    today = date.today()
    window_start, _ = _month_bounds(today, months - 1)

    rows = (
        await db.execute(
            select(Tenancy, Unit.property_id, Property.name)
            .join(Unit, Unit.id == Tenancy.unit_id)
            .join(Property, Property.id == Unit.property_id)
            .where(Tenancy.organization_id == organization_id)
        )
    ).all()

    live_by_property: dict[uuid.UUID, int] = {}
    ended_by_property: dict[uuid.UUID, list[float]] = {}
    property_names: dict[uuid.UUID, str] = {}
    window_durations: list[float] = []
    all_time_durations: list[float] = []
    moved_out = 0

    for tenancy, property_id, property_name in rows:
        property_names[property_id] = property_name

        if tenancy.status in LIVE_STATUSES:
            live_by_property[property_id] = live_by_property.get(property_id, 0) + 1
            continue
        if tenancy.status not in ENDED_STATUSES:
            continue

        finished = _ended_on(tenancy)
        if finished is None:
            continue
        duration = _months_between(tenancy.start_date, finished)
        all_time_durations.append(duration)
        if finished >= window_start:
            moved_out += 1
            window_durations.append(duration)
            ended_by_property.setdefault(property_id, []).append(duration)

    live_total = sum(live_by_property.values())
    held = live_total + moved_out

    properties: list[dict[str, Any]] = []
    for property_id, name in sorted(property_names.items(), key=lambda item: item[1]):
        live = live_by_property.get(property_id, 0)
        ended = ended_by_property.get(property_id, [])
        property_held = live + len(ended)
        properties.append(
            {
                "property_id": str(property_id),
                "property_name": name,
                "active_tenancies": live,
                "moved_out": len(ended),
                "turnover_rate_percent": (
                    round(len(ended) / property_held * 100, 1) if property_held else 0.0
                ),
                "average_tenancy_months": (round(sum(ended) / len(ended), 1) if ended else None),
            }
        )

    properties.sort(key=lambda row: float(row["turnover_rate_percent"]), reverse=True)

    return {
        "window_months": months,
        "active_tenancies": live_total,
        "moved_out": moved_out,
        "tenancies_held": held,
        "turnover_rate_percent": round(moved_out / held * 100, 1) if held else 0.0,
        "average_tenancy_months": (
            round(sum(window_durations) / len(window_durations), 1) if window_durations else None
        ),
        "average_tenancy_months_all_time": (
            round(sum(all_time_durations) / len(all_time_durations), 1) if all_time_durations else None
        ),
        "tenancies_ever_ended": len(all_time_durations),
        "properties": properties,
    }
