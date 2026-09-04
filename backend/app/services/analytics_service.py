"""Advanced analytics service — Phase 2 (US-054).

Financial intelligence, property performance, and predictive forecasting.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Invoice, Payment, PaymentStatus
from app.models.operations import BILLABLE_STATUSES, MaintenanceRequest
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus

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
