"""Caretaker performance metrics — Phase 2 (US-058).

The point of this is to replace "I think Mwangi is slacking" with a number that
can be shown to Mwangi. Every metric is derived from work he either did or did
not do, over a window, on the properties he is actually assigned to — so a
caretaker is never marked down for a unit nobody gave him.

Four things are measured, weighted by how much they matter to a landlord:

  * meter reading compliance — the recurring duty most often skipped;
  * inspection completion — the evidence that protects deposits;
  * maintenance response time — what a tenant actually experiences;
  * cash discipline — whether recorded cash gets banked rather than held.

A caretaker with nothing to do scores nothing rather than 100: a metric with no
denominator is reported as "no data" and dropped from the weighting, so the score
reflects the work that existed.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.billing import Payment, PaymentMethod, PaymentStatus
from app.models.inspection import InspectionReport, InspectionStatus
from app.models.operations import MaintenanceRequest, MaintenanceStatus, MeterReading
from app.models.property import CaretakerAssignment, Property, Unit
from app.models.user import User, UserRole

ZERO = Decimal("0.00")

# How the four metrics roll into one 0–100 score. Meter readings weigh heaviest
# because they are the recurring duty and the one most visibly skipped.
WEIGHTS = {
    "meter_compliance": 0.35,
    "inspection_completion": 0.25,
    "maintenance_response": 0.25,
    "cash_discipline": 0.15,
}

# A first response slower than this scores zero on responsiveness.
RESPONSE_TARGET_HOURS = 24
RESPONSE_ZERO_HOURS = 96

DEFAULT_WINDOW_DAYS = 30


def _band(score: float | None) -> str:
    """Green above 80, amber to 60, red below — matching the dashboard chips."""
    if score is None:
        return "no_data"
    if score >= 80:
        return "good"
    if score >= 60:
        return "watch"
    return "poor"


def _response_score(average_hours: float | None) -> float | None:
    """24h or better is full marks; 96h or worse is zero; linear between."""
    if average_hours is None:
        return None
    if average_hours <= RESPONSE_TARGET_HOURS:
        return 100.0
    if average_hours >= RESPONSE_ZERO_HOURS:
        return 0.0
    span = RESPONSE_ZERO_HOURS - RESPONSE_TARGET_HOURS
    return round((1 - (average_hours - RESPONSE_TARGET_HOURS) / span) * 100, 1)


def weighted_score(metrics: dict[str, float | None]) -> float | None:
    """Combine the metrics that have data, re-normalised over their weights."""
    available = {key: value for key, value in metrics.items() if value is not None}
    if not available:
        return None
    total_weight = sum(WEIGHTS[key] for key in available)
    if total_weight == 0:
        return None
    return round(sum(value * WEIGHTS[key] for key, value in available.items()) / total_weight, 1)


async def _assigned_units(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """The properties this caretaker holds, and every unit in them."""
    property_ids = list(
        await db.scalars(
            select(CaretakerAssignment.property_id).where(
                CaretakerAssignment.organization_id == organization_id,
                CaretakerAssignment.user_id == user_id,
                CaretakerAssignment.is_active.is_(True),
                CaretakerAssignment.revoked_at.is_(None),
            )
        )
    )
    if not property_ids:
        return [], []

    unit_ids = list(
        await db.scalars(
            select(Unit.id).where(Unit.property_id.in_(property_ids), Unit.is_archived.is_(False))
        )
    )
    return property_ids, unit_ids


async def metrics_for(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    as_at: datetime | None = None,
) -> dict:
    """One caretaker's numbers over the trailing `window_days`."""
    as_at = as_at or datetime.now(UTC)
    since = as_at - timedelta(days=window_days)
    property_ids, unit_ids = await _assigned_units(db, organization_id, user.id)

    # --- meter reading compliance ---
    # The duty is one reading per metered unit per month. Anything below that is
    # a unit whose consumption nobody captured.
    metered_units = 0
    if property_ids:
        rate_rows = await db.execute(
            select(Property.id, Property.water_rate_per_unit, Property.electricity_rate_per_unit).where(
                Property.id.in_(property_ids)
            )
        )
        metered_property_ids = [
            property_id
            for property_id, water, electricity in rate_rows
            if water is not None or electricity is not None
        ]
        if metered_property_ids:
            metered_units = int(
                await db.scalar(
                    select(func.count(Unit.id)).where(
                        Unit.property_id.in_(metered_property_ids),
                        Unit.is_archived.is_(False),
                    )
                )
                or 0
            )

    months = max(1, round(window_days / 30))
    readings_due = metered_units * months
    readings_taken = 0
    if unit_ids:
        readings_taken = int(
            await db.scalar(
                select(func.count(MeterReading.id)).where(
                    MeterReading.organization_id == organization_id,
                    MeterReading.recorded_by_id == user.id,
                    MeterReading.reading_date >= since.date(),
                )
            )
            or 0
        )
    meter_compliance = round(min(100.0, readings_taken / readings_due * 100), 1) if readings_due else None

    # --- inspection completion ---
    inspections_started = int(
        await db.scalar(
            select(func.count(InspectionReport.id)).where(
                InspectionReport.organization_id == organization_id,
                InspectionReport.inspector_id == user.id,
                InspectionReport.created_at >= since,
            )
        )
        or 0
    )
    inspections_submitted = int(
        await db.scalar(
            select(func.count(InspectionReport.id)).where(
                InspectionReport.organization_id == organization_id,
                InspectionReport.inspector_id == user.id,
                InspectionReport.created_at >= since,
                InspectionReport.status == InspectionStatus.SUBMITTED,
            )
        )
        or 0
    )
    # A draft left unsubmitted is the failure mode here — it looks like work but
    # produces no evidence.
    inspection_completion = (
        round(inspections_submitted / inspections_started * 100, 1) if inspections_started else None
    )

    # --- maintenance response time ---
    average_response_hours: float | None = None
    handled = 0
    if unit_ids:
        rows = list(
            await db.execute(
                select(MaintenanceRequest.created_at, MaintenanceRequest.acknowledged_at).where(
                    MaintenanceRequest.organization_id == organization_id,
                    MaintenanceRequest.unit_id.in_(unit_ids),
                    MaintenanceRequest.created_at >= since,
                )
            )
        )
        gaps = []
        for created_at, acknowledged_at in rows:
            # An unacknowledged request is not excused by being open — it counts
            # against the caretaker at its current age.
            end = acknowledged_at or as_at
            gaps.append((end - created_at).total_seconds() / 3600)
        handled = len(gaps)
        if gaps:
            average_response_hours = round(sum(gaps) / len(gaps), 1)
    maintenance_response = _response_score(average_response_hours)

    # --- cash discipline ---
    # Cash a caretaker records is money they are physically holding. The metric is
    # the share of their collections that came in through M-Pesa instead, which is
    # traceable end to end.
    cash_total = ZERO
    traceable_total = ZERO
    payment_rows = list(
        await db.execute(
            select(Payment.method, func.coalesce(func.sum(Payment.amount), 0))
            .where(
                Payment.organization_id == organization_id,
                Payment.recorded_by_id == user.id,
                Payment.status == PaymentStatus.CONFIRMED,
                Payment.payment_date >= since.date(),
            )
            .group_by(Payment.method)
        )
    )
    for method, total in payment_rows:
        if method == PaymentMethod.CASH:
            cash_total += Decimal(total)
        else:
            traceable_total += Decimal(total)
    collected = cash_total + traceable_total
    cash_discipline = round(float(traceable_total / collected * 100), 1) if collected > ZERO else None

    metrics = {
        "meter_compliance": meter_compliance,
        "inspection_completion": inspection_completion,
        "maintenance_response": maintenance_response,
        "cash_discipline": cash_discipline,
    }
    score = weighted_score(metrics)

    return {
        "user_id": str(user.id),
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "property_count": len(property_ids),
        "unit_count": len(unit_ids),
        "window_days": window_days,
        "score": score,
        "band": _band(score),
        "metrics": metrics,
        "detail": {
            "readings_due": readings_due,
            "readings_taken": readings_taken,
            "inspections_started": inspections_started,
            "inspections_submitted": inspections_submitted,
            "maintenance_requests": handled,
            "average_response_hours": average_response_hours,
            "cash_collected": float(cash_total),
            "traceable_collected": float(traceable_total),
        },
    }


async def trend_for(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    *,
    months: int = 6,
) -> list[dict]:
    """The same score over past windows, so improvement is visible (US-058).

    Each point is a 30-day window ending that many months ago, computed with the
    same function — the trend and the headline can never disagree.
    """
    points = []
    now = datetime.now(UTC)
    for offset in range(months - 1, -1, -1):
        as_at = now - timedelta(days=30 * offset)
        snapshot = await metrics_for(db, organization_id, user, window_days=30, as_at=as_at)
        points.append(
            {
                "month": as_at.strftime("%b %Y"),
                "score": snapshot["score"],
                "meter_compliance": snapshot["metrics"]["meter_compliance"],
                "maintenance_response": snapshot["metrics"]["maintenance_response"],
            }
        )
    return points


async def list_caretakers(
    db: AsyncSession, context: OrgContext, *, window_days: int = DEFAULT_WINDOW_DAYS
) -> list[dict]:
    """Every caretaker in the organisation, worst score first."""
    caretakers = list(
        await db.scalars(
            select(User).where(
                User.organization_id == context.organization_id,
                User.role == UserRole.CARETAKER,
                User.is_active.is_(True),
            )
        )
    )
    rows = [
        await metrics_for(db, context.organization_id, user, window_days=window_days) for user in caretakers
    ]
    # Whoever needs attention first, with "no data" last rather than at the top.
    rows.sort(key=lambda row: (row["score"] is None, row["score"] if row["score"] is not None else 0))
    return rows


async def caretaker_detail(
    db: AsyncSession,
    context: OrgContext,
    user_id: uuid.UUID,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    from fastapi import HTTPException, status

    user = await db.get(User, user_id)
    if user is None or user.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caretaker not found")

    snapshot = await metrics_for(db, context.organization_id, user, window_days=window_days)
    snapshot["trend"] = await trend_for(db, context.organization_id, user)

    property_ids, _ = await _assigned_units(db, context.organization_id, user.id)
    properties = (
        list(await db.scalars(select(Property).where(Property.id.in_(property_ids)))) if property_ids else []
    )
    snapshot["properties"] = [{"id": str(p.id), "name": p.name} for p in properties]
    return snapshot


async def open_maintenance_ages(db: AsyncSession, context: OrgContext, user_id: uuid.UUID) -> list[dict]:
    """The specific jobs dragging a caretaker's response score down."""
    _, unit_ids = await _assigned_units(db, context.organization_id, user_id)
    if not unit_ids:
        return []

    now = datetime.now(UTC)
    rows = list(
        await db.scalars(
            select(MaintenanceRequest)
            .where(
                MaintenanceRequest.organization_id == context.organization_id,
                MaintenanceRequest.unit_id.in_(unit_ids),
                MaintenanceRequest.status == MaintenanceStatus.SUBMITTED,
            )
            .order_by(MaintenanceRequest.created_at)
        )
    )
    return [
        {
            "id": str(row.id),
            "reference_code": row.reference_code,
            "title": row.title,
            "priority": row.priority.value,
            "created_at": row.created_at.isoformat(),
            "hours_open": round((now - row.created_at).total_seconds() / 3600, 1),
        }
        for row in rows
    ]
