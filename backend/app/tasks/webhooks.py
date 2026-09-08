"""Outbound webhook delivery (US-087) — the HTTP side of `webhook_service.dispatch`.

Delivery is retried up to twice more (three attempts total) with exponential
backoff, matching the acceptance criteria. Each attempt's result — status,
body, timing — is written back onto the `WebhookDelivery` row so the developer
portal's delivery log always reflects reality without polling anything.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.models.developer import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint
from app.tasks.async_utils import run_async
from app.tasks.celery_app import celery_app

logger = logging.getLogger("rentflow.webhooks")

# Countdown before retry 1 and retry 2, in seconds — one minute, then ten.
_RETRY_BACKOFF_SECONDS = [60, 600]


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@celery_app.task(bind=True, name="rentflow.deliver_webhook", max_retries=len(_RETRY_BACKOFF_SECONDS))
def deliver_webhook(self, delivery_id: str) -> dict[str, object]:
    attempt_index = self.request.retries

    async def work(db: AsyncSession) -> bool:
        delivery = await db.get(WebhookDelivery, uuid.UUID(delivery_id))
        if delivery is None or delivery.status == WebhookDeliveryStatus.SUCCESS:
            return True

        endpoint = await db.get(WebhookEndpoint, delivery.webhook_endpoint_id)
        if endpoint is None or not endpoint.is_active:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.response_body = "Endpoint no longer active"
            delivery.next_retry_at = None
            await db.commit()
            return True

        secret = await crypto.decrypt_for_org(db, endpoint.organization_id, endpoint.secret_encrypted)
        body = json.dumps(
            {"event": delivery.event_type, "data": delivery.payload, "delivery_id": str(delivery.id)}
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-RentFlow-Event": delivery.event_type,
            "X-RentFlow-Delivery": str(delivery.id),
        }
        if secret:
            headers["X-RentFlow-Signature"] = f"sha256={_sign(secret, body)}"

        delivery.attempt_count += 1
        endpoint.last_triggered_at = datetime.now(UTC)

        try:
            async with httpx.AsyncClient(timeout=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS) as client:
                response = await client.post(endpoint.url, content=body, headers=headers)
            delivery.response_status_code = response.status_code
            delivery.response_body = response.text[:1000]
            delivered = 200 <= response.status_code < 300
        except httpx.HTTPError as exc:
            delivery.response_status_code = None
            delivery.response_body = str(exc)[:1000]
            delivered = False

        if delivered:
            delivery.status = WebhookDeliveryStatus.SUCCESS
            delivery.delivered_at = datetime.now(UTC)
            delivery.next_retry_at = None
            endpoint.consecutive_failures = 0
            endpoint.last_success_at = datetime.now(UTC)
        else:
            endpoint.consecutive_failures += 1
            if attempt_index < len(_RETRY_BACKOFF_SECONDS):
                delivery.next_retry_at = datetime.now(UTC) + timedelta(
                    seconds=_RETRY_BACKOFF_SECONDS[attempt_index]
                )
            else:
                delivery.status = WebhookDeliveryStatus.FAILED
                delivery.next_retry_at = None

        await db.commit()
        return delivered

    delivered = run_async(work)
    if not delivered and attempt_index < len(_RETRY_BACKOFF_SECONDS):
        raise self.retry(countdown=_RETRY_BACKOFF_SECONDS[attempt_index])

    return {"delivery_id": delivery_id, "delivered": delivered}
