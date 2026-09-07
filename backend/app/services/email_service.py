"""Email suppression and Resend's delivery-event webhook (Sprint 26A).

Deliverability has two halves. SPF/DKIM/DMARC (documented in
`docs/procurement/email-deliverability.md`, since they are DNS records on a
real domain this environment cannot configure) prove RentFlow is allowed to
send as itself. This module is the other half — proving RentFlow *behaves*
once it can send: an address that hard-bounces or marks a message as spam
gets suppressed, platform-wide, rather than mailed again next month by a
different landlord's reminder job. Repeated sends to a dead or complaining
address are exactly what makes mailbox providers stop trusting a sending
domain regardless of how correct its DNS is.
"""

import hashlib
import hmac
import logging
from base64 import b64decode, b64encode
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import (
    DeliveryStatus,
    EmailSuppression,
    EmailSuppressionReason,
    Notification,
)

logger = logging.getLogger("rentflow.email")

# Resend's event names for the two that matter here — a full delivery-event
# payload carries several others (sent, delivered, opened, clicked) that this
# module has no reason to act on.
_BOUNCE_EVENT = "email.bounced"
_COMPLAINT_EVENT = "email.complained"


async def is_suppressed(db: AsyncSession, email: str) -> bool:
    normalized = email.strip().lower()
    return (
        await db.scalar(select(EmailSuppression.id).where(EmailSuppression.email == normalized).limit(1))
        is not None
    )


async def suppress(
    db: AsyncSession, email: str, reason: EmailSuppressionReason, detail: str | None = None
) -> None:
    """`ON CONFLICT DO NOTHING` rather than a check-then-insert: `handle_event`
    below can suppress several addresses from one webhook payload before
    anything commits, so two calls for the same address in one still-open
    transaction is an expected case, not just a cross-request race — and a
    plain SELECT-then-INSERT would not see its own prior, unflushed write."""
    normalized = email.strip().lower()
    await db.execute(
        insert(EmailSuppression)
        .values(email=normalized, reason=reason, detail=detail)
        .on_conflict_do_nothing(index_elements=["email"])
    )


def verify_webhook_signature(payload: bytes, headers: dict[str, str]) -> bool:
    """Resend signs webhooks the way Svix does: HMAC-SHA256 over
    `{svix-id}.{svix-timestamp}.{payload}`, keyed by the base64 portion of a
    `whsec_...` secret, compared against one of the space-separated `v1,<sig>`
    values in `svix-signature`. No `svix` package dependency for one function —
    the scheme is simple enough, and this codebase already hand-rolls its own
    HMAC constructions (`app.core.security.sign_payload`) rather than reaching
    for a library per primitive.
    """
    if not settings.RESEND_WEBHOOK_SECRET:
        logger.warning("Rejected a Resend webhook: RESEND_WEBHOOK_SECRET is not configured")
        return False

    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")
    if not (svix_id and svix_timestamp and svix_signature):
        return False

    secret = settings.RESEND_WEBHOOK_SECRET
    key = b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    signed_content = f"{svix_id}.{svix_timestamp}.{payload.decode('utf-8')}".encode()
    expected = b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()

    for candidate in svix_signature.split():
        _, _, sig = candidate.partition(",")
        if sig and hmac.compare_digest(sig, expected):
            return True
    return False


async def handle_event(db: AsyncSession, event: dict[str, Any]) -> None:
    """Apply one already-verified Resend webhook event.

    Looks up the `Notification` row by the provider's message id
    (`_apply` in `notification_service.py` stores it on every successful
    send), so an event for a message this instance never sent (a different
    environment, or one sent outside the notification pipeline) is simply a
    no-op rather than an error — a webhook endpoint has no way to know which
    of those it is, and neither case is actionable here.
    """
    event_type = event.get("type")
    if event_type not in (_BOUNCE_EVENT, _COMPLAINT_EVENT):
        return

    data = event.get("data") or {}
    message_id = data.get("email_id")
    recipients: list[str] = data.get("to") or []
    is_bounce = event_type == _BOUNCE_EVENT

    if message_id:
        notification = await db.scalar(
            select(Notification).where(Notification.provider_message_id == message_id)
        )
        if notification is not None:
            notification.status = DeliveryStatus.BOUNCED if is_bounce else DeliveryStatus.COMPLAINED
            detail = f": {data['bounce']['message']}" if is_bounce and data.get("bounce") else ""
            notification.error = f"Resend {event_type}{detail}"[:500]

    reason = EmailSuppressionReason.BOUNCED if is_bounce else EmailSuppressionReason.COMPLAINED
    for recipient in recipients:
        await suppress(db, recipient, reason, detail=f"Resend {event_type}, message {message_id}")

    await db.commit()
