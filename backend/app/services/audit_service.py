"""Append-only audit trail.

`record` never commits — it adds to the caller's session so the log entry lands in
the same transaction as the change it describes. An audit row can therefore not
survive a rolled-back write, and vice versa.
"""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _gps(request: Request | None) -> tuple[float | None, float | None]:
    """Mobile clients pass coordinates in `X-Geo-Position: <lat>,<lng>`."""
    if request is None:
        return None, None
    header = request.headers.get("x-geo-position")
    if not header or "," not in header:
        return None, None
    lat_raw, _, lng_raw = header.partition(",")
    try:
        return float(lat_raw), float(lng_raw)
    except ValueError:
        return None, None


def record(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    actor: User | None = None,
    summary: str | None = None,
    changes: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    latitude, longitude = _gps(request)
    entry = AuditLog(
        organization_id=organization_id,
        user_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        changes=changes,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
        gps_latitude=latitude,
        gps_longitude=longitude,
    )
    db.add(entry)
    return entry


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Only the fields that actually changed, as `{field: {from, to}}`."""
    changed: dict[str, Any] = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value != new_value:
            changed[key] = {"from": _plain(old_value), "to": _plain(new_value)}
    return changed


def _plain(value: Any) -> Any:
    """JSONB cannot hold UUIDs, dates or Decimals — stringify anything exotic."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


async def list_for_entity(
    db: AsyncSession, organization_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID, limit: int = 50
) -> list[AuditLog]:
    result = await db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == organization_id,
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result)
