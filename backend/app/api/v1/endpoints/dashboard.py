import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.audit import AuditLog
from app.schemas.billing import AgingBuckets
from app.schemas.operations import ActivityEntry, CaretakerActivitySummary
from app.services import dashboard_service, operations_service

router = APIRouter()
activity_router = APIRouter()


class MonthPointRead(BaseModel):
    month: str
    expected: Decimal
    collected: Decimal


class DefaulterRead(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenancy_id: uuid.UUID
    unit_number: str
    property_name: str
    amount_owed: Decimal
    days_overdue: int


class RecentPaymentRead(BaseModel):
    id: uuid.UUID
    reference_code: str
    amount: Decimal
    method: str
    paid_at: datetime | None
    tenant_name: str
    unit_number: str
    property_name: str


class AttentionCounts(BaseModel):
    vacant: int
    under_maintenance: int
    vacating: int
    leases_expiring: int


class FinancialDashboard(BaseModel):
    expected_rent: Decimal
    collected: Decimal
    collection_rate: float
    total_arrears: Decimal
    tenants_in_arrears: int
    occupancy_rate: float
    total_units: int
    occupied_units: int
    vacant_units: int
    total_properties: int
    monthly_chart: list[MonthPointRead]
    top_defaulters: list[DefaulterRead]
    recent_payments: list[RecentPaymentRead]
    aging: AgingBuckets
    attention: AttentionCounts


@router.get("/financial", response_model=FinancialDashboard)
async def financial_dashboard(
    months_back: int = Query(default=6, ge=1, le=24),
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> FinancialDashboard:
    """Real-time KPI cards, six-month income chart, defaulters and recent payments."""
    data = await dashboard_service.build(db, context, months_back)
    attention = await dashboard_service.units_needing_attention(db, context)

    return FinancialDashboard(
        expected_rent=data["expected_rent"],
        collected=data["collected"],
        collection_rate=data["collection_rate"],
        total_arrears=data["total_arrears"],
        tenants_in_arrears=data["tenants_in_arrears"],
        occupancy_rate=data["occupancy_rate"],
        total_units=data["total_units"],
        occupied_units=data["occupied_units"],
        vacant_units=data["vacant_units"],
        total_properties=data["total_properties"],
        monthly_chart=[
            MonthPointRead(month=p.month, expected=p.expected, collected=p.collected)
            for p in data["monthly_chart"]
        ],
        top_defaulters=[
            DefaulterRead(
                tenant_id=row.tenant_id,
                tenant_name=row.tenant_name,
                tenancy_id=row.tenancy_id,
                unit_number=row.unit_number,
                property_name=row.property_name,
                amount_owed=row.amount_owed,
                days_overdue=row.days_overdue,
            )
            for row in data["top_defaulters"]
        ],
        recent_payments=[RecentPaymentRead(**row) for row in data["recent_payments"]],
        aging=AgingBuckets(**data["aging"]),
        attention=AttentionCounts(**attention),
    )


# ---------------------------------------------------------------- activity / audit


@activity_router.get("", response_model=list[ActivityEntry])
async def list_activity(
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    context: OrgContext = Depends(require(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ActivityEntry]:
    """The audit trail — also the caretaker activity log (US-028)."""
    query = select(AuditLog).where(AuditLog.organization_id == context.organization_id)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)

    rows = await db.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit))
    return [
        ActivityEntry(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            summary=entry.summary,
            actor_name=entry.actor_name,
            user_id=entry.user_id,
            created_at=entry.created_at,
            gps_latitude=entry.gps_latitude,
            gps_longitude=entry.gps_longitude,
        )
        for entry in rows
    ]


@activity_router.get("/caretakers", response_model=list[CaretakerActivitySummary])
async def caretaker_activity(
    days: int = Query(default=30, ge=1, le=365),
    context: OrgContext = Depends(require(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[CaretakerActivitySummary]:
    """Per-caretaker activity counts over a window (US-028)."""
    from datetime import UTC, timedelta

    from app.models.user import User, UserRole

    since = datetime.now(UTC) - timedelta(days=days)
    caretakers = await db.scalars(
        select(User).where(
            User.organization_id == context.organization_id,
            User.role == UserRole.CARETAKER,
            User.deleted_at.is_(None),
        )
    )

    summaries = []
    for caretaker in caretakers:
        counts = await operations_service.caretaker_activity_counts(
            db, context.organization_id, caretaker.id, since
        )
        days_since = (datetime.now(UTC) - caretaker.last_login_at).days if caretaker.last_login_at else None
        summaries.append(
            CaretakerActivitySummary(
                user_id=caretaker.id,
                full_name=caretaker.full_name,
                last_login_at=caretaker.last_login_at,
                days_since_login=days_since,
                **counts,
            )
        )
    return summaries
