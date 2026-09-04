"""Owner financial dashboard (US-032).

'Expected' is the contracted rent on occupied units for the current month, not
the sum of every invoice raised — an owner asking "am I collecting what I should
be?" means the former. 'Collected' counts confirmed payments in the month
regardless of which invoice they settled, because that is what actually reached
the bank.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.property import Property, Unit, UnitStatus
from app.models.tenant import Tenancy, TenancyStatus
from app.services import arrears_service, property_service

ZERO = Decimal("0.00")
LIVE = [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]


@dataclass
class MonthPoint:
    month: str
    expected: Decimal
    collected: Decimal


def month_range(anchor: date, months_back: int) -> list[tuple[date, date]]:
    """`months_back` complete months ending with the month containing `anchor`."""
    spans: list[tuple[date, date]] = []
    year, month = anchor.year, anchor.month
    for _ in range(months_back):
        last_day = calendar.monthrange(year, month)[1]
        spans.append((date(year, month, 1), date(year, month, last_day)))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(spans))


async def _tenancy_scope(db: AsyncSession, context: OrgContext):
    """Subquery of tenancy ids this user may see, or None for the whole org."""
    allowed = await accessible_property_ids(db, context)
    if allowed is None:
        return None
    return select(Tenancy.id).join(Unit, Unit.id == Tenancy.unit_id).where(Unit.property_id.in_(allowed))


async def collected_between(db: AsyncSession, context: OrgContext, start: date, end: date) -> Decimal:
    query = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.organization_id == context.organization_id,
        Payment.status == PaymentStatus.CONFIRMED,
        Payment.payment_date >= start,
        Payment.payment_date <= end,
    )
    scope = await _tenancy_scope(db, context)
    if scope is not None:
        query = query.where(Payment.tenancy_id.in_(scope))
    return Decimal(await db.scalar(query) or 0)


async def invoiced_between(db: AsyncSession, context: OrgContext, start: date, end: date) -> Decimal:
    query = select(func.coalesce(func.sum(Invoice.total), 0)).where(
        Invoice.organization_id == context.organization_id,
        Invoice.status != InvoiceStatus.CANCELLED,
        Invoice.issue_date >= start,
        Invoice.issue_date <= end,
    )
    scope = await _tenancy_scope(db, context)
    if scope is not None:
        query = query.where(Invoice.tenancy_id.in_(scope))
    return Decimal(await db.scalar(query) or 0)


async def expected_this_month(db: AsyncSession, context: OrgContext) -> Decimal:
    """Contracted rent across live tenancies."""
    query = select(func.coalesce(func.sum(Tenancy.monthly_rent), 0)).where(
        Tenancy.organization_id == context.organization_id, Tenancy.status.in_(LIVE)
    )
    scope = await _tenancy_scope(db, context)
    if scope is not None:
        query = query.where(Tenancy.id.in_(scope))
    return Decimal(await db.scalar(query) or 0)


async def recent_payments(db: AsyncSession, context: OrgContext, limit: int = 10) -> list[dict]:
    query = (
        select(Payment, Tenancy, Unit, Property)
        .join(Tenancy, Tenancy.id == Payment.tenancy_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .where(
            Payment.organization_id == context.organization_id,
            Payment.status == PaymentStatus.CONFIRMED,
        )
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Unit.property_id.in_(allowed))

    rows = (await db.execute(query.order_by(Payment.paid_at.desc()).limit(limit))).all()

    from app.models.tenant import Tenant

    result = []
    for payment, tenancy, unit, property_record in rows:
        tenant = await db.get(Tenant, tenancy.tenant_id)
        result.append(
            {
                "id": payment.id,
                "reference_code": payment.reference_code,
                "amount": Decimal(payment.amount),
                "method": payment.method.value,
                "paid_at": payment.paid_at,
                "tenant_name": tenant.full_name if tenant else "",
                "unit_number": unit.unit_number,
                "property_name": property_record.name,
            }
        )
    return result


async def build(db: AsyncSession, context: OrgContext, months_back: int = 6) -> dict:
    today = date.today()
    month_start = today.replace(day=1)
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    expected = await expected_this_month(db, context)
    collected = await collected_between(db, context, month_start, month_end)
    arrears = await arrears_service.build_report(db, context)
    portfolio, _ = await property_service.portfolio_stats(db, context)

    chart: list[MonthPoint] = []
    for start, end in month_range(today, months_back):
        chart.append(
            MonthPoint(
                month=start.strftime("%b %Y"),
                expected=await invoiced_between(db, context, start, end),
                collected=await collected_between(db, context, start, end),
            )
        )

    collection_rate = float(round(collected / expected * 100, 1)) if expected > 0 else 0.0

    return {
        "expected_rent": expected,
        "collected": collected,
        "collection_rate": collection_rate,
        "total_arrears": arrears.total_arrears,
        "tenants_in_arrears": arrears.tenants_in_arrears,
        "occupancy_rate": portfolio.occupancy_rate,
        "total_units": portfolio.total_units,
        "occupied_units": portfolio.occupied_units,
        "vacant_units": portfolio.vacant_units,
        "total_properties": portfolio.total_properties,
        "monthly_chart": chart,
        "top_defaulters": arrears.rows[:5],
        "recent_payments": await recent_payments(db, context),
        "aging": arrears.aging,
    }


async def units_needing_attention(db: AsyncSession, context: OrgContext) -> dict[str, int]:
    """Counts behind the dashboard's action prompts."""
    base = select(func.count(Unit.id)).where(
        Unit.organization_id == context.organization_id, Unit.is_archived.is_(False)
    )
    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        base = base.where(Unit.property_id.in_(allowed))

    vacant = int(await db.scalar(base.where(Unit.status == UnitStatus.VACANT)) or 0)
    maintenance = int(await db.scalar(base.where(Unit.status == UnitStatus.UNDER_MAINTENANCE)) or 0)
    vacating = int(await db.scalar(base.where(Unit.status == UnitStatus.VACATING)) or 0)

    expiring_query = select(func.count(Tenancy.id)).where(
        Tenancy.organization_id == context.organization_id,
        Tenancy.status == TenancyStatus.EXPIRING_SOON,
    )
    scope = await _tenancy_scope(db, context)
    if scope is not None:
        expiring_query = expiring_query.where(Tenancy.id.in_(scope))
    expiring = int(await db.scalar(expiring_query) or 0)

    return {
        "vacant": vacant,
        "under_maintenance": maintenance,
        "vacating": vacating,
        "leases_expiring": expiring,
    }
