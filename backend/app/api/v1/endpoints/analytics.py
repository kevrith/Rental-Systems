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
