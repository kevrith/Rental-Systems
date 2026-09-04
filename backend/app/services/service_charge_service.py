"""Service charge billing and reconciliation (US-070).

The three numbers this module keeps apart are what was budgeted, what was
charged and what was actually spent. Any service charge scheme that cannot show
all three is one a tenant is right to dispute, so the annual statement is built
from real expense rows rather than from the charge itself.

Apportionment is computed at billing time from the building as it stands that
month — a unit that fell vacant does not keep paying, and under
`BY_OCCUPIED_UNIT` its share moves to the landlord rather than to the neighbours.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org, assert_property_access
from app.models.billing import Invoice, InvoiceLineItem, LineItemKind
from app.models.property import Property, Unit
from app.models.service_charge import (
    Apportionment,
    ServiceChargeBudget,
    ServiceChargeCategory,
    ServiceChargeExpense,
    ServiceChargeScheme,
    SinkingFundEntry,
    SinkingFundMovement,
)
from app.models.tenant import Tenancy, TenancyStatus
from app.services import audit_service

ZERO = Decimal("0.00")
PENNY = Decimal("0.01")

LIVE_TENANCY_STATUSES = [
    TenancyStatus.ACTIVE,
    TenancyStatus.EXPIRING_SOON,
    TenancyStatus.NOTICE_GIVEN,
]


async def get_scheme(
    db: AsyncSession, organization_id: uuid.UUID, property_id: uuid.UUID
) -> ServiceChargeScheme | None:
    return await db.scalar(
        select(ServiceChargeScheme).where(
            ServiceChargeScheme.organization_id == organization_id,
            ServiceChargeScheme.property_id == property_id,
        )
    )


async def upsert_scheme(
    db: AsyncSession,
    context: OrgContext,
    property_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> ServiceChargeScheme:
    """One scheme per property, created on first save and edited thereafter."""
    property_record = assert_in_org(await db.get(Property, property_id), context, label="property")
    await assert_property_access(db, context, property_record.id)

    scheme = await get_scheme(db, context.organization_id, property_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"budgets"})

    if scheme is None:
        scheme = ServiceChargeScheme(
            organization_id=context.organization_id, property_id=property_id, **fields
        )
        db.add(scheme)
        action, verb = "service_charge.scheme_created", "set up"
    else:
        for field, value in fields.items():
            setattr(scheme, field, value)
        action, verb = "service_charge.scheme_updated", "updated"
    await db.flush()

    if payload.budgets is not None:
        await _replace_budgets(db, context.organization_id, scheme, payload.budgets)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action=action,
        entity_type="service_charge_scheme",
        entity_id=scheme.id,
        actor=context.user,
        summary=(
            f"{context.user.full_name} {verb} the service charge for {property_record.name} "
            f"({scheme.apportionment.value.replace('_', ' ')})"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(scheme)
    return scheme


async def _replace_budgets(
    db: AsyncSession, organization_id: uuid.UUID, scheme: ServiceChargeScheme, budgets: list
) -> None:
    existing = {
        budget.category: budget
        for budget in await db.scalars(
            select(ServiceChargeBudget).where(ServiceChargeBudget.scheme_id == scheme.id)
        )
    }
    seen: set[ServiceChargeCategory] = set()

    for line in budgets:
        seen.add(line.category)
        row = existing.get(line.category)
        if row is None:
            db.add(
                ServiceChargeBudget(
                    organization_id=organization_id,
                    scheme_id=scheme.id,
                    category=line.category,
                    monthly_budget=line.monthly_budget,
                    notes=line.notes,
                )
            )
        else:
            row.monthly_budget = line.monthly_budget
            row.notes = line.notes

    # Categories dropped from the submitted list are removed, so the budget always
    # matches what the operator last saw.
    for category, row in existing.items():
        if category not in seen:
            await db.delete(row)
    await db.flush()


# ---------------------------------------------------------------- apportionment


async def _billable_units(db: AsyncSession, property_id: uuid.UUID) -> list[Unit]:
    rows = await db.scalars(select(Unit).where(Unit.property_id == property_id, Unit.is_archived.is_(False)))
    return list(rows)


async def _occupied_unit_ids(db: AsyncSession, property_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(Tenancy.unit_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .where(Unit.property_id == property_id, Tenancy.status.in_(LIVE_TENANCY_STATUSES))
    )
    return set(rows)


async def apportion(db: AsyncSession, scheme: ServiceChargeScheme) -> dict[uuid.UUID, Decimal]:
    """What each unit owes this month, by unit id.

    Rounding is settled by giving the remainder to the largest share rather than
    letting it vanish — over twelve months a lost cent per unit is a real gap
    between what was charged and what the pool needed.
    """
    units = await _billable_units(db, scheme.property_id)
    if not units:
        return {}

    if scheme.apportionment == Apportionment.FIXED_PER_UNIT:
        amount = Decimal(scheme.fixed_amount).quantize(PENNY)
        return {unit.id: amount for unit in units}

    pool = Decimal(scheme.monthly_pool)
    if pool <= ZERO:
        return {unit.id: ZERO for unit in units}

    if scheme.apportionment == Apportionment.BY_OCCUPIED_UNIT:
        occupied = await _occupied_unit_ids(db, scheme.property_id)
        shares = {unit.id: Decimal("1") for unit in units if unit.id in occupied}
    else:  # BY_FLOOR_AREA
        shares = {unit.id: Decimal(str(unit.size_sqm or 0)) for unit in units if (unit.size_sqm or 0) > 0}

    total_share = sum(shares.values(), ZERO)
    if total_share <= ZERO:
        return {unit.id: ZERO for unit in units}

    allocations: dict[uuid.UUID, Decimal] = {}
    for unit_id, share in shares.items():
        allocations[unit_id] = (pool * share / total_share).quantize(PENNY)

    drift = pool.quantize(PENNY) - sum(allocations.values(), ZERO)
    if drift and allocations:
        largest = max(allocations, key=lambda key: allocations[key])
        allocations[largest] += drift

    # Units that carry no share this month still appear, at zero, so the caller
    # can tell "not charged" from "not in this building".
    for unit in units:
        allocations.setdefault(unit.id, ZERO)
    return allocations


async def charge_for_unit(
    db: AsyncSession, organization_id: uuid.UUID, unit: Unit
) -> tuple[Decimal, ServiceChargeScheme | None]:
    """This unit's service charge for the month, or zero if the property has none."""
    scheme = await get_scheme(db, organization_id, unit.property_id)
    if scheme is None or not scheme.is_active or not scheme.bill_with_rent:
        return ZERO, scheme
    allocations = await apportion(db, scheme)
    return allocations.get(unit.id, ZERO), scheme


def line_item_for(amount: Decimal, period_start: date, scheme: ServiceChargeScheme) -> InvoiceLineItem:
    return InvoiceLineItem(
        kind=LineItemKind.SERVICE_CHARGE,
        description=f"{scheme.name} — {period_start.strftime('%B %Y')}",
        quantity=Decimal("1"),
        unit_amount=amount,
        amount=amount,
    )


async def record_sinking_fund_contribution(
    db: AsyncSession, scheme: ServiceChargeScheme, charged: Decimal, period_start: date
) -> SinkingFundEntry | None:
    """Move this month's reserve slice out of the charge as it is billed.

    Done at billing time rather than at collection: the reserve is a share of
    what the building charged, and treating it as a share of what was collected
    would let one late tenant quietly shrink the roof fund.
    """
    percent = Decimal(scheme.sinking_fund_percent or 0)
    if percent <= ZERO or charged <= ZERO:
        return None

    amount = (charged * percent / 100).quantize(PENNY)
    if amount <= ZERO:
        return None

    existing = await db.scalar(
        select(SinkingFundEntry).where(
            SinkingFundEntry.scheme_id == scheme.id,
            SinkingFundEntry.billing_period == period_start,
            SinkingFundEntry.movement == SinkingFundMovement.CONTRIBUTION,
        )
    )
    if existing is not None:
        # A second invoice in the same month tops up the same entry rather than
        # opening a duplicate one.
        existing.amount = Decimal(existing.amount) + amount
        return existing

    entry = SinkingFundEntry(
        organization_id=scheme.organization_id,
        scheme_id=scheme.id,
        movement=SinkingFundMovement.CONTRIBUTION,
        amount=amount,
        entry_date=period_start,
        description=f"{percent}% of {period_start.strftime('%B %Y')} service charges",
        billing_period=period_start,
    )
    db.add(entry)
    return entry


async def sinking_fund_balance(db: AsyncSession, scheme_id: uuid.UUID) -> Decimal:
    contributions = await db.scalar(
        select(func.coalesce(func.sum(SinkingFundEntry.amount), 0)).where(
            SinkingFundEntry.scheme_id == scheme_id,
            SinkingFundEntry.movement == SinkingFundMovement.CONTRIBUTION,
        )
    )
    withdrawals = await db.scalar(
        select(func.coalesce(func.sum(SinkingFundEntry.amount), 0)).where(
            SinkingFundEntry.scheme_id == scheme_id,
            SinkingFundEntry.movement == SinkingFundMovement.WITHDRAWAL,
        )
    )
    return Decimal(str(contributions or 0)) - Decimal(str(withdrawals or 0))


async def record_sinking_fund_movement(
    db: AsyncSession,
    context: OrgContext,
    scheme_id: uuid.UUID,
    *,
    movement: SinkingFundMovement,
    amount: Decimal,
    entry_date: date,
    description: str,
    request: Request | None = None,
) -> SinkingFundEntry:
    scheme = assert_in_org(await db.get(ServiceChargeScheme, scheme_id), context, label="scheme")

    if movement == SinkingFundMovement.WITHDRAWAL:
        balance = await sinking_fund_balance(db, scheme.id)
        if amount > balance:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The reserve only holds KES {balance:,.2f}",
            )

    entry = SinkingFundEntry(
        organization_id=context.organization_id,
        scheme_id=scheme.id,
        movement=movement,
        amount=amount,
        entry_date=entry_date,
        description=description,
        recorded_by_id=context.user.id,
    )
    db.add(entry)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action=f"sinking_fund.{movement.value}",
        entity_type="service_charge_scheme",
        entity_id=scheme.id,
        actor=context.user,
        summary=f"KES {amount:,.2f} {movement.value} — {description}",
        request=request,
    )
    await db.commit()
    await db.refresh(entry)
    return entry


# ------------------------------------------------------------------- expenses


async def record_expense(
    db: AsyncSession,
    context: OrgContext,
    scheme_id: uuid.UUID,
    payload,
    request: Request | None = None,
) -> ServiceChargeExpense:
    scheme = assert_in_org(await db.get(ServiceChargeScheme, scheme_id), context, label="scheme")

    expense = ServiceChargeExpense(
        organization_id=context.organization_id,
        scheme_id=scheme.id,
        recorded_by_id=context.user.id,
        **payload.model_dump(),
    )
    db.add(expense)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="service_charge.expense_recorded",
        entity_type="service_charge_scheme",
        entity_id=scheme.id,
        actor=context.user,
        summary=(
            f"KES {payload.amount:,.2f} on {payload.category.value.replace('_', ' ')} "
            f"— {payload.description}"
        ),
        request=request,
    )
    await db.commit()
    await db.refresh(expense)
    return expense


async def list_expenses(
    db: AsyncSession,
    context: OrgContext,
    scheme_id: uuid.UUID,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int = 200,
) -> list[ServiceChargeExpense]:
    query = select(ServiceChargeExpense).where(
        ServiceChargeExpense.organization_id == context.organization_id,
        ServiceChargeExpense.scheme_id == scheme_id,
    )
    if since:
        query = query.where(ServiceChargeExpense.incurred_on >= since)
    if until:
        query = query.where(ServiceChargeExpense.incurred_on <= until)

    rows = await db.scalars(query.order_by(ServiceChargeExpense.incurred_on.desc()).limit(limit))
    return list(rows)


# ------------------------------------------------------------- reconciliation


async def reconcile(
    db: AsyncSession,
    context: OrgContext,
    scheme_id: uuid.UUID,
    *,
    period_start: date,
    period_end: date,
) -> dict:
    """Budget vs charged vs spent for a period, by category (US-070).

    The surplus or deficit at the bottom is the number the annual statement has
    to justify to tenants, so it is computed from the same rows the detail lists
    rather than from a stored total.
    """
    scheme = assert_in_org(await db.get(ServiceChargeScheme, scheme_id), context, label="scheme")
    property_record = await db.get(Property, scheme.property_id)

    months = max(
        1,
        (period_end.year - period_start.year) * 12 + (period_end.month - period_start.month) + 1,
    )

    budgets = {
        budget.category: Decimal(budget.monthly_budget)
        for budget in await db.scalars(
            select(ServiceChargeBudget).where(ServiceChargeBudget.scheme_id == scheme.id)
        )
    }
    spend_rows = (
        await db.execute(
            select(
                ServiceChargeExpense.category,
                func.coalesce(func.sum(ServiceChargeExpense.amount), 0),
            )
            .where(
                ServiceChargeExpense.scheme_id == scheme.id,
                ServiceChargeExpense.incurred_on >= period_start,
                ServiceChargeExpense.incurred_on <= period_end,
            )
            .group_by(ServiceChargeExpense.category)
        )
    ).all()
    spend = {category: Decimal(str(total or 0)) for category, total in spend_rows}

    # What tenants in this building were actually invoiced over the window.
    charged = Decimal(
        str(
            await db.scalar(
                select(func.coalesce(func.sum(InvoiceLineItem.amount), 0))
                .select_from(InvoiceLineItem)
                .join(Invoice, Invoice.id == InvoiceLineItem.invoice_id)
                .join(Tenancy, Tenancy.id == Invoice.tenancy_id)
                .join(Unit, Unit.id == Tenancy.unit_id)
                .where(
                    InvoiceLineItem.kind == LineItemKind.SERVICE_CHARGE,
                    Unit.property_id == scheme.property_id,
                    Invoice.organization_id == context.organization_id,
                    Invoice.period_start >= period_start,
                    Invoice.period_start <= period_end,
                )
            )
            or 0
        )
    )

    categories = sorted(set(budgets) | set(spend), key=lambda item: item.value)
    lines = []
    for category in categories:
        budgeted = budgets.get(category, ZERO) * months
        actual = spend.get(category, ZERO)
        lines.append(
            {
                "category": category.value,
                "budgeted": float(budgeted),
                "spent": float(actual),
                "variance": float(budgeted - actual),
                "over_budget": bool(actual > budgeted),
            }
        )

    total_budget = sum((Decimal(str(line["budgeted"])) for line in lines), ZERO)
    total_spent = sum((Decimal(str(line["spent"])) for line in lines), ZERO)

    return {
        "scheme_id": str(scheme.id),
        "property_name": property_record.name if property_record else None,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "months": months,
        "total_budgeted": float(total_budget),
        "total_charged": float(charged),
        "total_spent": float(total_spent),
        # Positive means tenants were charged more than the building spent, which
        # is money that belongs back to them or into the reserve.
        "surplus_or_deficit": float(charged - total_spent),
        "sinking_fund_balance": float(await sinking_fund_balance(db, scheme.id)),
        "lines": lines,
    }


async def scheme_overview(db: AsyncSession, context: OrgContext, scheme: ServiceChargeScheme) -> dict:
    """What the configuration screen shows: the split, per unit, as it stands."""
    allocations = await apportion(db, scheme)
    units = {unit.id: unit for unit in await _billable_units(db, scheme.property_id)}
    occupied = await _occupied_unit_ids(db, scheme.property_id)

    breakdown = [
        {
            "unit_id": str(unit_id),
            "unit_number": units[unit_id].unit_number if unit_id in units else "",
            "size_sqm": units[unit_id].size_sqm if unit_id in units else None,
            "occupied": unit_id in occupied,
            "monthly_charge": float(amount),
        }
        for unit_id, amount in sorted(
            allocations.items(),
            key=lambda item: units[item[0]].unit_number if item[0] in units else "",
        )
    ]
    return {
        "monthly_total": float(sum(allocations.values(), ZERO)),
        "units": breakdown,
        "sinking_fund_balance": float(await sinking_fund_balance(db, scheme.id)),
    }
