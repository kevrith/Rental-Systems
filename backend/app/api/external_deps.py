"""Authentication and rate limiting for the public API (Sprint 19, US-085/086).

Kept separate from `app.api.deps`: the public API's identity is an API key
belonging to an organization, not a logged-in user, so the whole dependency
chain (`ApiKeyContext`, scope checks, rate limiting) has no user, role or
session to reason about — reusing `OrgContext` here would mean carrying a lot
of `None`s through code that never needed them.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_errors import ExternalApiError
from app.core.config import settings
from app.core.database import get_db
from app.models.developer import ApiKey, ApiKeyScope
from app.models.organization import Organization
from app.services import api_key_service

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(slots=True)
class ApiKeyContext:
    organization_id: uuid.UUID
    api_key: ApiKey


async def get_api_key_context(
    request: Request,
    raw_key: str | None = Depends(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyContext:
    if not raw_key:
        raise ExternalApiError(status_code=401, detail="Missing X-API-Key header")

    api_key = await api_key_service.authenticate(db, raw_key)

    organization = await db.get(Organization, api_key.organization_id)
    if organization is None or not organization.is_active:
        raise ExternalApiError(status_code=403, detail="Organization is suspended or missing")

    limit = organization.api_rate_limit_per_hour or settings.API_KEY_DEFAULT_RATE_LIMIT_PER_HOUR
    await api_key_service.enforce_rate_limit(api_key, limit)
    await api_key_service.record_usage(db, api_key, endpoint=request.url.path)

    return ApiKeyContext(organization_id=api_key.organization_id, api_key=api_key)


def require_scope(*scopes: ApiKeyScope):
    """Dependency factory: the key must hold every listed scope."""

    def dependency(context: ApiKeyContext = Depends(get_api_key_context)) -> ApiKeyContext:
        held = set(context.api_key.scopes)
        missing = [scope.value for scope in scopes if scope.value not in held]
        if missing:
            raise ExternalApiError(
                status_code=403, detail=f"This API key lacks scope(s): {', '.join(missing)}"
            )
        return context

    return dependency
