"""Developer platform management (Sprint 19): API keys and webhook endpoints,
as seen by an authenticated user in the app itself — not the public API these
credentials unlock (see `app.api.v1.endpoints.external`).
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.developer import ApiKey, WebhookEndpoint
from app.schemas.developer import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    ApiKeyUsage,
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointCreated,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
)
from app.services import api_key_service, webhook_service

router = APIRouter()
webhooks_router = APIRouter()


def _api_key_read(row: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=row.scopes,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def _webhook_read(row: WebhookEndpoint) -> WebhookEndpointRead:
    return WebhookEndpointRead(
        id=row.id,
        url=row.url,
        description=row.description,
        event_types=row.event_types,
        is_active=row.is_active,
        consecutive_failures=row.consecutive_failures,
        last_triggered_at=row.last_triggered_at,
        last_success_at=row.last_success_at,
        created_at=row.created_at,
    )


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.API_KEY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    row, raw_key = await api_key_service.create_api_key(db, context, payload, request)
    return ApiKeyCreated(**_api_key_read(row).model_dump(), api_key=raw_key)


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(
    context: OrgContext = Depends(require(Permission.API_KEY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyRead]:
    rows = await api_key_service.list_api_keys(db, context)
    return [_api_key_read(row) for row in rows]


@router.get("/{api_key_id}/usage", response_model=ApiKeyUsage)
async def get_api_key_usage(
    api_key_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.API_KEY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyUsage:
    await api_key_service.get_api_key(db, context, api_key_id)  # 403/404 before reading Redis
    stats = await api_key_service.usage_stats(api_key_id)
    return ApiKeyUsage.model_validate(stats)


@router.post("/{api_key_id}/revoke", response_model=ApiKeyRead)
async def revoke_api_key(
    api_key_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.API_KEY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyRead:
    row = await api_key_service.revoke_api_key(db, context, api_key_id, request)
    return _api_key_read(row)


@webhooks_router.post("", response_model=WebhookEndpointCreated, status_code=status.HTTP_201_CREATED)
async def create_webhook_endpoint(
    payload: WebhookEndpointCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointCreated:
    row, secret = await webhook_service.create_endpoint(db, context, payload, request)
    return WebhookEndpointCreated(**_webhook_read(row).model_dump(), secret=secret)


@webhooks_router.get("", response_model=list[WebhookEndpointRead])
async def list_webhook_endpoints(
    context: OrgContext = Depends(require(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookEndpointRead]:
    rows = await webhook_service.list_endpoints(db, context)
    return [_webhook_read(row) for row in rows]


@webhooks_router.get("/{endpoint_id}/secret")
async def reveal_webhook_secret(
    endpoint_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return {"secret": await webhook_service.reveal_secret(db, context, endpoint_id)}


@webhooks_router.patch("/{endpoint_id}", response_model=WebhookEndpointRead)
async def update_webhook_endpoint(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointRead:
    row = await webhook_service.update_endpoint(db, context, endpoint_id, payload, request)
    return _webhook_read(row)


@webhooks_router.post("/{endpoint_id}/archive", response_model=WebhookEndpointRead)
async def archive_webhook_endpoint(
    endpoint_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointRead:
    row = await webhook_service.archive_endpoint(db, context, endpoint_id, request)
    return _webhook_read(row)


@webhooks_router.get("/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryRead])
async def list_webhook_deliveries(
    endpoint_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryRead]:
    rows = await webhook_service.list_deliveries(db, context, endpoint_id)
    return [WebhookDeliveryRead.model_validate(row) for row in rows]
