"""Outbound webhooks: subscription management and event fan-out (US-087).

`dispatch` is called from the same place each event's WhatsApp/SMS notification
already goes out (payment confirmation, tenant creation, lease signing,
inspection completion, maintenance status change, invoice generation) — see
each service's call site. It only ever writes `WebhookDelivery` rows inside the
caller's transaction; the actual HTTP delivery happens out of band in
`app.tasks.webhooks.deliver_webhook`, so a slow or unreachable customer
endpoint can never slow down the request that triggered the event.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.core import crypto
from app.core.config import settings
from app.core.security import generate_webhook_secret
from app.models.developer import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint, WebhookEvent
from app.schemas.developer import WebhookEndpointCreate, WebhookEndpointUpdate
from app.services import audit_service


async def create_endpoint(
    db: AsyncSession, context: OrgContext, payload: WebhookEndpointCreate, request: Request
) -> tuple[WebhookEndpoint, str]:
    active_count = await db.scalar(
        select(func.count(WebhookEndpoint.id)).where(
            WebhookEndpoint.organization_id == context.organization_id,
            WebhookEndpoint.is_archived.is_(False),
        )
    )
    if (active_count or 0) >= settings.WEBHOOK_MAX_PER_ORG:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An organization may have at most {settings.WEBHOOK_MAX_PER_ORG} webhook endpoints",
        )

    secret = generate_webhook_secret()
    row = WebhookEndpoint(
        organization_id=context.organization_id,
        url=payload.url,
        description=payload.description,
        secret_encrypted=await crypto.encrypt_for_org(db, context.organization_id, secret),
        event_types=[event.value for event in payload.event_types],
        created_by_id=context.user.id,
    )
    db.add(row)
    await db.flush()
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="webhook_endpoint.created",
        entity_type="webhook_endpoint",
        entity_id=row.id,
        actor=context.user,
        summary=f"Registered webhook endpoint {row.url}",
        request=request,
    )
    await db.commit()
    await db.refresh(row)
    return row, secret


async def list_endpoints(db: AsyncSession, context: OrgContext) -> list[WebhookEndpoint]:
    rows = await db.scalars(
        select(WebhookEndpoint)
        .where(
            WebhookEndpoint.organization_id == context.organization_id,
            WebhookEndpoint.is_archived.is_(False),
        )
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return list(rows)


async def get_endpoint(db: AsyncSession, context: OrgContext, endpoint_id: uuid.UUID) -> WebhookEndpoint:
    row = await db.get(WebhookEndpoint, endpoint_id)
    return assert_in_org(row, context, label="webhook endpoint")


async def reveal_secret(db: AsyncSession, context: OrgContext, endpoint_id: uuid.UUID) -> str:
    row = await get_endpoint(db, context, endpoint_id)
    secret = await crypto.decrypt_for_org(db, row.organization_id, row.secret_encrypted)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This endpoint's secret can no longer be decrypted — regenerate it",
        )
    return secret


async def update_endpoint(
    db: AsyncSession,
    context: OrgContext,
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    request: Request,
) -> WebhookEndpoint:
    row = await get_endpoint(db, context, endpoint_id)
    if payload.url is not None:
        row.url = payload.url
    if payload.description is not None:
        row.description = payload.description
    if payload.event_types is not None:
        row.event_types = [event.value for event in payload.event_types]
    if payload.is_active is not None:
        row.is_active = payload.is_active
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="webhook_endpoint.updated",
        entity_type="webhook_endpoint",
        entity_id=row.id,
        actor=context.user,
        request=request,
    )
    await db.commit()
    await db.refresh(row)
    return row


async def archive_endpoint(
    db: AsyncSession, context: OrgContext, endpoint_id: uuid.UUID, request: Request
) -> WebhookEndpoint:
    row = await get_endpoint(db, context, endpoint_id)
    row.is_archived = True
    row.archived_at = datetime.now(UTC)
    row.is_active = False
    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="webhook_endpoint.archived",
        entity_type="webhook_endpoint",
        entity_id=row.id,
        actor=context.user,
        request=request,
    )
    await db.commit()
    await db.refresh(row)
    return row


async def list_deliveries(
    db: AsyncSession, context: OrgContext, endpoint_id: uuid.UUID, *, limit: int = 100
) -> list[WebhookDelivery]:
    await get_endpoint(db, context, endpoint_id)  # 403/404 before leaking any delivery rows
    rows = await db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def dispatch(db: AsyncSession, organization_id: uuid.UUID, event: WebhookEvent, payload: dict) -> None:
    """Queue `event` for every active endpoint subscribed to it.

    Deliberately not `async def dispatch(..., context: OrgContext, ...)` —
    callers like the M-Pesa webhook run with no authenticated user, only an
    organization id, so the signature matches what every call site actually has.
    """
    endpoints = await db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == organization_id,
            WebhookEndpoint.is_active.is_(True),
            WebhookEndpoint.is_archived.is_(False),
        )
    )
    delivery_ids: list[uuid.UUID] = []
    for endpoint in endpoints:
        if event.value not in endpoint.event_types:
            continue
        delivery = WebhookDelivery(
            organization_id=organization_id,
            webhook_endpoint_id=endpoint.id,
            event_type=event.value,
            payload=payload,
            status=WebhookDeliveryStatus.PENDING,
        )
        db.add(delivery)
        await db.flush()
        delivery_ids.append(delivery.id)

    if not delivery_ids:
        return

    await db.commit()

    # Imported lazily: `app.tasks.webhooks` imports Celery's app, which is a
    # heavier import than any request path touching `dispatch` should pay for.
    from app.tasks.webhooks import deliver_webhook

    for delivery_id in delivery_ids:
        deliver_webhook.delay(str(delivery_id))
