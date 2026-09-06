"""Public API key lifecycle and usage accounting (US-086).

Usage counters live in Redis rather than Postgres: an API key can be called far
more often than any other write path in the system, and per-request rows would
have no accounting or audit value once counted. Only identity and lifecycle —
name, scopes, expiry, revocation — are durable.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.core.api_errors import ExternalApiError
from app.core.redis import redis_client
from app.core.security import generate_api_key, hash_token
from app.models.developer import ApiKey
from app.schemas.developer import ApiKeyCreate
from app.services import audit_service

_USAGE_DAY_TTL_SECONDS = 8 * 24 * 3600
_USAGE_HOUR_TTL_SECONDS = 3600


def _day_key(api_key_id: uuid.UUID, day: str) -> str:
    return f"apikey:usage:{api_key_id}:{day}"


def _hour_key(api_key_id: uuid.UUID, hour: str) -> str:
    return f"apikey:rate:{api_key_id}:{hour}"


def _endpoints_key(api_key_id: uuid.UUID) -> str:
    return f"apikey:endpoints:{api_key_id}"


async def create_api_key(
    db: AsyncSession, context: OrgContext, payload: ApiKeyCreate, request: Request
) -> tuple[ApiKey, str]:
    full_key, prefix, key_hash = generate_api_key()
    row = ApiKey(
        organization_id=context.organization_id,
        name=payload.name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=[scope.value for scope in payload.scopes],
        created_by_id=context.user.id,
        expires_at=payload.expires_at,
    )
    db.add(row)
    await db.flush()
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="api_key.created",
        entity_type="api_key",
        entity_id=row.id,
        actor=context.user,
        summary=f"Created API key '{row.name}'",
        request=request,
    )
    await db.commit()
    await db.refresh(row)
    return row, full_key


async def list_api_keys(db: AsyncSession, context: OrgContext) -> list[ApiKey]:
    rows = await db.scalars(
        select(ApiKey)
        .where(ApiKey.organization_id == context.organization_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(rows)


async def get_api_key(db: AsyncSession, context: OrgContext, api_key_id: uuid.UUID) -> ApiKey:
    row = await db.get(ApiKey, api_key_id)
    return assert_in_org(row, context, label="API key")


async def revoke_api_key(
    db: AsyncSession, context: OrgContext, api_key_id: uuid.UUID, request: Request
) -> ApiKey:
    row = await get_api_key(db, context, api_key_id)
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        audit_service.record(
            db,
            organization_id=context.organization_id,
            action="api_key.revoked",
            entity_type="api_key",
            entity_id=row.id,
            actor=context.user,
            summary=f"Revoked API key '{row.name}'",
            request=request,
        )
        await db.commit()
        await db.refresh(row)
    return row


async def usage_stats(api_key_id: uuid.UUID) -> dict[str, object]:
    today = datetime.now(UTC).date()
    requests_today = int(await redis_client.get(_day_key(api_key_id, today.isoformat())) or 0)
    last_7_days = 0
    for offset in range(7):
        day = (today - timedelta(days=offset)).isoformat()
        last_7_days += int(await redis_client.get(_day_key(api_key_id, day)) or 0)
    endpoints_hit = {
        field: int(value) for field, value in (await redis_client.hgetall(_endpoints_key(api_key_id))).items()
    }
    return {
        "requests_today": requests_today,
        "requests_last_7_days": last_7_days,
        "endpoints_hit": endpoints_hit,
    }


async def authenticate(db: AsyncSession, raw_key: str) -> ApiKey:
    """Resolve a raw `X-API-Key` header value to an active row, or raise 401.

    A key looks like `rf_live_<8 hex>_<secret>`. The secret comes from
    `secrets.token_urlsafe`, which can itself contain underscores, so the
    prefix must be taken as the first three `_`-separated segments — a
    `rsplit` on the last underscore would cut the wrong side whenever the
    secret happened to contain one.
    """
    parts = raw_key.split("_", 3)
    prefix = "_".join(parts[:3]) if len(parts) == 4 else raw_key
    candidate = await db.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))
    if candidate is None or candidate.key_hash != hash_token(raw_key):
        raise ExternalApiError(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if not candidate.is_usable(datetime.now(UTC)):
        raise ExternalApiError(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="This API key is revoked or expired"
        )
    return candidate


async def enforce_rate_limit(api_key: ApiKey, limit_per_hour: int) -> None:
    hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
    key = _hour_key(api_key.id, hour)
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, _USAGE_HOUR_TTL_SECONDS)
    if count > limit_per_hour:
        raise ExternalApiError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit_per_hour} requests/hour",
        )


async def record_usage(db: AsyncSession, api_key: ApiKey, endpoint: str) -> None:
    today = datetime.now(UTC).date().isoformat()
    day_key = _day_key(api_key.id, today)
    await redis_client.incr(day_key)
    await redis_client.expire(day_key, _USAGE_DAY_TTL_SECONDS)
    await redis_client.hincrby(_endpoints_key(api_key.id), endpoint, 1)

    api_key.last_used_at = datetime.now(UTC)
    await db.commit()
