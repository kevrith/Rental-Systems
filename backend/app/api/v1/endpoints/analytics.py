"""Analytics API endpoints — Phase 2 (US-054)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.core.permissions import Permission
from app.services import analytics_service

router = APIRouter()


@router.get("/revenue")
async def revenue_analytics(
    months: int = 6,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.revenue_analytics(db, context.organization_id, months)


@router.get("/property-performance")
async def property_performance(
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.property_performance(db, context.organization_id)


@router.get("/cash-flow-forecast")
async def cash_flow_forecast(
    months_ahead: int = 3,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.cash_flow_forecast(db, context.organization_id, months_ahead)


@router.get("/expiring-leases")
async def expiring_leases(
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.expiring_leases_forecast(db, context.organization_id)


@router.get("/maintenance")
async def maintenance_analytics(
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.maintenance_analytics(db, context.organization_id)


@router.get("/vacancy-risk")
async def vacancy_risk_forecast(
    days_ahead: int = 90,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.vacancy_risk_forecast(db, context.organization_id, days_ahead=days_ahead)


@router.get("/rent-review")
async def rent_review_suggestions(
    min_months: int = 12,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.rent_review_suggestions(db, context.organization_id, min_months=min_months)


@router.get("/utilities")
async def utility_analytics(
    months: int = 6,
    above_average_multiplier: float = 1.5,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.utility_analytics(
        db,
        context.organization_id,
        months=months,
        above_average_multiplier=above_average_multiplier,
    )


@router.get("/payment-behaviour")
async def payment_behaviour(
    months: int = 6,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.payment_behaviour_segments(db, context.organization_id, months=months)


@router.get("/turnover")
async def tenant_turnover(
    months: int = 12,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.tenant_turnover(db, context.organization_id, months=months)
