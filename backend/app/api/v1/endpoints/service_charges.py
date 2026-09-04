"""Service charge configuration, expenses and reconciliation (US-070)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.property import Property
from app.models.service_charge import (
    ServiceChargeBudget,
    ServiceChargeScheme,
    SinkingFundEntry,
)
from app.schemas.service_charge import (
    BudgetLine,
    ExpenseCreate,
    ExpenseRead,
    SchemeDetail,
    SchemeRead,
    SchemeUpsert,
    SinkingFundEntryCreate,
    SinkingFundEntryRead,
    UnitCharge,
)
from app.services import service_charge_service

router = APIRouter()


async def _detail(db: AsyncSession, context: OrgContext, scheme: ServiceChargeScheme) -> SchemeDetail:
    property_record = await db.get(Property, scheme.property_id)
    overview = await service_charge_service.scheme_overview(db, context, scheme)
    budgets = await db.scalars(select(ServiceChargeBudget).where(ServiceChargeBudget.scheme_id == scheme.id))

    return SchemeDetail(
        **SchemeRead.model_validate(scheme).model_dump(),
        property_name=property_record.name if property_record else None,
        budgets=[
            BudgetLine(category=b.category, monthly_budget=b.monthly_budget, notes=b.notes) for b in budgets
        ],
        monthly_total=overview["monthly_total"],
        sinking_fund_balance=overview["sinking_fund_balance"],
        units=[UnitCharge(**row) for row in overview["units"]],
    )


@router.get("/property/{property_id}", response_model=SchemeDetail | None)
async def get_scheme(
    property_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.PROPERTY_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> SchemeDetail | None:
    """The property's scheme, or null if it does not charge one."""
    scheme = await service_charge_service.get_scheme(db, context.organization_id, property_id)
    return await _detail(db, context, scheme) if scheme else None


@router.put("/property/{property_id}", response_model=SchemeDetail)
async def upsert_scheme(
    property_id: uuid.UUID,
    payload: SchemeUpsert,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SchemeDetail:
    scheme = await service_charge_service.upsert_scheme(db, context, property_id, payload, request)
    return await _detail(db, context, scheme)


@router.get("/{scheme_id}/reconciliation")
async def reconciliation(
    scheme_id: uuid.UUID,
    period_start: date = Query(...),
    period_end: date = Query(...),
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Budgeted vs charged vs spent, and the surplus or deficit (US-070)."""
    if period_end < period_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The period ends before it starts"
        )
    return await service_charge_service.reconcile(
        db, context, scheme_id, period_start=period_start, period_end=period_end
    )


@router.get("/{scheme_id}/expenses", response_model=list[ExpenseRead])
async def list_expenses(
    scheme_id: uuid.UUID,
    since: date | None = None,
    until: date | None = None,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseRead]:
    rows = await service_charge_service.list_expenses(db, context, scheme_id, since=since, until=until)
    return [ExpenseRead.model_validate(row) for row in rows]


@router.post("/{scheme_id}/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def record_expense(
    scheme_id: uuid.UUID,
    payload: ExpenseCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseRead:
    expense = await service_charge_service.record_expense(db, context, scheme_id, payload, request)
    return ExpenseRead.model_validate(expense)


@router.get("/{scheme_id}/sinking-fund", response_model=list[SinkingFundEntryRead])
async def sinking_fund(
    scheme_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[SinkingFundEntryRead]:
    assert_in_org(await db.get(ServiceChargeScheme, scheme_id), context, label="scheme")
    rows = await db.scalars(
        select(SinkingFundEntry)
        .where(SinkingFundEntry.scheme_id == scheme_id)
        .order_by(SinkingFundEntry.entry_date.desc())
        .limit(200)
    )
    return [SinkingFundEntryRead.model_validate(row) for row in rows]


@router.post(
    "/{scheme_id}/sinking-fund",
    response_model=SinkingFundEntryRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_sinking_fund_movement(
    scheme_id: uuid.UUID,
    payload: SinkingFundEntryCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.PROPERTY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SinkingFundEntryRead:
    entry = await service_charge_service.record_sinking_fund_movement(
        db,
        context,
        scheme_id,
        movement=payload.movement,
        amount=payload.amount,
        entry_date=payload.entry_date,
        description=payload.description,
        request=request,
    )
    return SinkingFundEntryRead.model_validate(entry)
