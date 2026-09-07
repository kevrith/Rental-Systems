"""Unified notification dispatch.

One call fans a single event out across WhatsApp, SMS, push and the in-app inbox,
writing a `Notification` row per channel so delivery is auditable per-channel
(US-031). Opt-outs are honoured per user, per type, per channel.

Delivery failures never propagate: a receipt that cannot reach WhatsApp must not
roll back the payment that produced it. Failures are recorded and surfaced in the
notification history instead.
"""

import html
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    DeliveryStatus,
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationType,
    PushSubscription,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.services import communication_template_service, email_service
from app.services.notifications import (
    get_email_notifier,
    get_push_notifier,
    get_sms_notifier,
    get_whatsapp_notifier,
)

logger = logging.getLogger("rentflow.notifications")

# Channels a user can never switch off — they are security or money events.
MANDATORY_TYPES = {
    NotificationType.PAYMENT_CONFIRMED,
    NotificationType.RECEIPT_ISSUED,
    NotificationType.SUSPICIOUS_LOGIN,
    NotificationType.ACCOUNT,
}


@dataclass(slots=True)
class Recipient:
    """Who to reach. Either a platform user or a tenant (who may have no login)."""

    phone_number: str | None = None
    user: User | None = None
    tenant: Tenant | None = None
    organization_id: uuid.UUID | None = None

    @classmethod
    def for_user(cls, user: User) -> "Recipient":
        return cls(phone_number=user.phone_number, user=user, organization_id=user.organization_id)

    @classmethod
    def for_tenant(cls, tenant: Tenant) -> "Recipient":
        return cls(phone_number=tenant.phone_number, tenant=tenant, organization_id=tenant.organization_id)


@dataclass(slots=True)
class Attachment:
    url: str
    filename: str


async def _channel_enabled(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    notification_type: NotificationType,
    channel: NotificationChannel,
) -> bool:
    if notification_type in MANDATORY_TYPES or user_id is None:
        return True
    preference = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type,
            NotificationPreference.channel == channel,
        )
    )
    # No stored preference means the default — on.
    return preference.enabled if preference else True


async def _deliver_push(db: AsyncSession, user_id: uuid.UUID, notification: Notification) -> None:
    subscriptions = list(
        await db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id, PushSubscription.revoked_at.is_(None)
            )
        )
    )
    if not subscriptions:
        notification.status = DeliveryStatus.SKIPPED
        notification.error = "No push subscriptions registered"
        return

    notifier = get_push_notifier()
    payload = {
        "title": notification.title,
        "body": notification.body,
        "url": notification.link_path or "/",
        "type": notification.notification_type.value,
    }
    delivered = False
    for subscription in subscriptions:
        result = await notifier.send(
            {
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
            },
            payload,
        )
        if result.success:
            delivered = True
        elif result.error == "expired":
            # The browser dropped it — stop trying rather than failing forever.
            subscription.revoked_at = datetime.now(UTC)

    notification.status = DeliveryStatus.SENT if delivered else DeliveryStatus.FAILED
    if delivered:
        notification.sent_at = datetime.now(UTC)


def to_email_html(body: str) -> str:
    """Wrap a plain-text notification body for an HTML email.

    Escaped, not interpolated raw. Every caller writes prose, and since Sprint 26
    an organisation can supply its own wording (Module 21) — so a stray `<` or
    `&` in a landlord's template would otherwise either break the markup or
    inject it into an email sent to their tenants.
    """
    return f"<p>{html.escape(body).replace(chr(10), '<br>')}</p>"


async def send(
    db: AsyncSession,
    *,
    recipient: Recipient,
    notification_type: NotificationType,
    title: str,
    body: str,
    channels: list[NotificationChannel] | None = None,
    link_path: str | None = None,
    attachment: Attachment | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    variables: dict[str, object] | None = None,
) -> list[Notification]:
    """Dispatch across `channels` (default WhatsApp + SMS) and return the log rows.

    Rows are added to the caller's session but not committed — the caller decides
    the transaction boundary.

    `title` and `body` are the built-in copy. An organisation that has written
    its own wording for this notification type gets theirs instead, rendered
    from `variables` (Module 21). Callers that pass no variables simply never
    match a template that needs any, and their own copy stands — which is why
    adding this required no change at any existing call site.
    """
    org_id = organization_id or recipient.organization_id
    if org_id is None:
        raise ValueError("A notification needs an organization to be scoped to")

    channels = channels or [NotificationChannel.WHATSAPP, NotificationChannel.SMS]
    user_id = recipient.user.id if recipient.user else None
    tenant_id = recipient.tenant.id if recipient.tenant else None
    phone = recipient.phone_number

    written: list[Notification] = []
    for channel in channels:
        # Per channel, not once per send: an organisation may write a short SMS
        # and a fuller email for the same event.
        channel_title, channel_body = await communication_template_service.apply(
            db,
            organization_id=org_id,
            notification_type=notification_type,
            channel=channel,
            title=title,
            body=body,
            variables=variables,
        )
        notification = Notification(
            organization_id=org_id,
            channel=channel,
            notification_type=notification_type,
            user_id=user_id,
            tenant_id=tenant_id,
            recipient=phone,
            title=channel_title,
            body=channel_body,
            link_path=link_path,
            entity_type=entity_type,
            entity_id=entity_id,
            status=DeliveryStatus.QUEUED,
        )
        db.add(notification)
        written.append(notification)

        if not await _channel_enabled(db, user_id, notification_type, channel):
            notification.status = DeliveryStatus.SKIPPED
            notification.error = "Muted by user preference"
            continue

        try:
            if channel == NotificationChannel.IN_APP:
                notification.status = DeliveryStatus.DELIVERED
                notification.sent_at = datetime.now(UTC)

            elif channel == NotificationChannel.PUSH:
                if user_id is None:
                    notification.status = DeliveryStatus.SKIPPED
                    notification.error = "Push requires a platform user"
                else:
                    await _deliver_push(db, user_id, notification)

            elif channel == NotificationChannel.WHATSAPP:
                if not phone:
                    notification.status = DeliveryStatus.SKIPPED
                    notification.error = "No phone number on file"
                else:
                    notifier = get_whatsapp_notifier()
                    if attachment:
                        result = await notifier.send_document(
                            phone, attachment.url, attachment.filename, caption=notification.body
                        )
                    else:
                        result = await notifier.send_text(
                            phone, f"{notification.title}\n\n{notification.body}"
                        )
                    _apply(notification, result)

            elif channel == NotificationChannel.SMS:
                if not phone:
                    notification.status = DeliveryStatus.SKIPPED
                    notification.error = "No phone number on file"
                else:
                    result = await get_sms_notifier().send(phone, notification.body)
                    _apply(notification, result)

            else:  # EMAIL
                if not recipient.user or not recipient.user.email:
                    notification.status = DeliveryStatus.SKIPPED
                    notification.error = "No email address on file"
                elif await email_service.is_suppressed(db, recipient.user.email):
                    notification.status = DeliveryStatus.SKIPPED
                    notification.error = "Address is suppressed (bounced or complained previously)"
                else:
                    result = await get_email_notifier().send(
                        recipient.user.email,
                        notification.title,
                        to_email_html(notification.body),
                    )
                    _apply(notification, result)

        except Exception as exc:  # noqa: BLE001 — a bad provider must not break the caller
            logger.exception("Notification dispatch failed on %s", channel.value)
            notification.status = DeliveryStatus.FAILED
            notification.error = str(exc)[:500]

    return written


def _apply(notification: Notification, result) -> None:  # noqa: ANN001 — DeliveryResult
    if result.success:
        notification.status = DeliveryStatus.SENT
        notification.sent_at = datetime.now(UTC)
        notification.provider_message_id = result.provider_message_id
    else:
        notification.status = DeliveryStatus.FAILED
        notification.error = result.error
