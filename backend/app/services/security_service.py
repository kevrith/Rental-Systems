"""Security hardening: IP whitelisting, per-role session policy, the security
audit log export, and fraud alert triage (Sprint 22, US-097/098).
"""

import ipaddress
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.audit import AuditLog
from app.models.organization import Organization
from app.models.security import (
    FraudAlert,
    FraudAlertStatus,
    FraudSuppression,
    SecurityEvent,
    SecurityEventType,
)
from app.models.user import User, UserRole
from app.services import audit_service, export_service, pdf_service


def ip_allowed(whitelist: list[str], client_ip: str | None) -> bool:
    """An empty whitelist means unrestricted — this is what every account starts
    with. Once populated, the caller's IP must match an entry exactly or fall
    inside a CIDR range."""
    if not whitelist:
        return True
    if not client_ip:
        return False
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for entry in whitelist:
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


async def record_event(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_type: SecurityEventType,
    user_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> SecurityEvent:
    from app.services.session_service import client_ip

    event = SecurityEvent(
        organization_id=organization_id,
        event_type=event_type,
        user_id=user_id,
        ip_address=client_ip(request) if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(event)
    return event


async def apply_role_session_timeouts(db: AsyncSession, organization: Organization) -> int:
    """Push the organisation's per-role policy onto every active user of that
    role right now. This is an imposed policy, not a per-user preference — a
    user does not keep a laxer timeout just because they set one before the
    policy existed."""
    if not organization.role_session_timeouts:
        return 0

    updated = 0
    for role_value, minutes in organization.role_session_timeouts.items():
        try:
            role = UserRole(role_value)
        except ValueError:
            continue
        result = await db.scalars(
            select(User).where(User.organization_id == organization.id, User.role == role)
        )
        for user in result:
            user.inactivity_timeout_minutes = minutes
            updated += 1
    return updated


# ------------------------------------------------------------------ fraud alerts


async def list_fraud_alerts(
    db: AsyncSession, context: OrgContext, *, alert_status: FraudAlertStatus | None = None, limit: int = 100
) -> list[FraudAlert]:
    query = select(FraudAlert).where(FraudAlert.organization_id == context.organization_id)
    if alert_status is not None:
        query = query.where(FraudAlert.status == alert_status)
    rows = await db.scalars(query.order_by(FraudAlert.created_at.desc()).limit(limit))
    return list(rows)


async def resolve_fraud_alert(
    db: AsyncSession,
    context: OrgContext,
    alert_id: uuid.UUID,
    *,
    new_status: Literal[FraudAlertStatus.SUPPRESSED, FraudAlertStatus.RESOLVED],
    request: Request | None = None,
) -> FraudAlert:
    alert = assert_in_org(await db.get(FraudAlert, alert_id), context, label="fraud alert")
    if alert.status != FraudAlertStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This alert is already resolved")

    alert.status = new_status
    alert.resolved_by_id = context.user.id
    alert.resolved_at = datetime.now(UTC)

    if new_status == FraudAlertStatus.SUPPRESSED:
        existing = await db.scalar(
            select(FraudSuppression).where(
                FraudSuppression.organization_id == context.organization_id,
                FraudSuppression.pattern_key == alert.pattern_key,
            )
        )
        if existing is None:
            db.add(
                FraudSuppression(
                    organization_id=context.organization_id,
                    pattern_key=alert.pattern_key,
                    created_by_id=context.user.id,
                )
            )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action=f"fraud_alert.{new_status.value}",
        entity_type="fraud_alert",
        entity_id=alert.id,
        actor=context.user,
        summary=f"Marked fraud alert '{alert.summary}' as {new_status.value}",
        request=request,
    )
    await db.commit()
    await db.refresh(alert)
    return alert


# --------------------------------------------------------------- audit log export


async def export_audit_log(
    db: AsyncSession,
    context: OrgContext,
    *,
    export_format: Literal["csv", "pdf"],
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[bytes, str]:
    query = select(AuditLog).where(AuditLog.organization_id == context.organization_id)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)

    rows = list(await db.scalars(query.order_by(AuditLog.created_at.desc()).limit(5000)))
    shaped = [
        {
            "Date": entry.created_at,
            "Actor": entry.actor_name or "System",
            "Action": entry.action,
            "Entity type": entry.entity_type,
            "Entity ID": entry.entity_id,
            "Summary": entry.summary,
            "IP address": entry.ip_address,
        }
        for entry in rows
    ]
    stamp = date.today().isoformat()

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="security.audit_log_exported",
        entity_type="audit_log",
        actor=context.user,
        summary=f"Exported {len(shaped)} audit log row(s) as {export_format}",
    )
    await db.commit()

    if export_format == "csv":
        return export_service.to_csv(shaped), f"rentflow-audit-log-{stamp}.csv"

    columns = (
        list(shaped[0].keys())
        if shaped
        else list(["Date", "Actor", "Action", "Entity type", "Entity ID", "Summary", "IP address"])
    )
    pdf_bytes = pdf_service.render_pdf(
        "custom_report.html",
        {
            "title": "Security Audit Log",
            "organization": context.organization,
            "generated_at": date.today(),
            "rows": shaped,
            "columns": columns,
        },
    )
    return pdf_bytes, f"rentflow-audit-log-{stamp}.pdf"
