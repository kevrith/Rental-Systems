"""Email suppression and Resend's delivery-event webhook (Sprint 26A)."""

import base64
import hashlib
import hmac
import json
import uuid

from httpx import AsyncClient

from app.core.config import settings
from app.models.notification import (
    DeliveryStatus,
    EmailSuppression,
    EmailSuppressionReason,
    Notification,
    NotificationChannel,
    NotificationType,
)
from app.models.user import User
from app.services import email_service
from tests.conftest import Actor

WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"a-test-signing-key-32-bytes-long").decode()


def _sign(payload: bytes, *, svix_id: str = "msg_test", svix_timestamp: str = "1700000000") -> dict[str, str]:
    key = base64.b64decode(WEBHOOK_SECRET.split("_", 1)[1])
    signed_content = f"{svix_id}.{svix_timestamp}.{payload.decode()}".encode()
    signature = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": svix_timestamp, "svix-signature": f"v1,{signature}"}


async def test_is_suppressed_and_suppress_are_case_and_whitespace_insensitive(db) -> None:
    assert await email_service.is_suppressed(db, "Someone@Example.com") is False

    await email_service.suppress(db, "  Someone@Example.com  ", EmailSuppressionReason.BOUNCED)
    await db.commit()

    assert await email_service.is_suppressed(db, "someone@example.com") is True


async def test_suppress_is_idempotent(db) -> None:
    await email_service.suppress(db, "dup@example.com", EmailSuppressionReason.BOUNCED)
    await email_service.suppress(db, "dup@example.com", EmailSuppressionReason.COMPLAINED)
    await db.commit()

    from sqlalchemy import select

    rows = list(await db.scalars(select(EmailSuppression).where(EmailSuppression.email == "dup@example.com")))
    assert len(rows) == 1
    assert rows[0].reason == EmailSuppressionReason.BOUNCED  # first write wins


def test_verify_webhook_signature_accepts_a_correctly_signed_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    payload = json.dumps({"type": "email.bounced"}).encode()
    headers = _sign(payload)
    assert email_service.verify_webhook_signature(payload, headers) is True


def test_verify_webhook_signature_rejects_a_tampered_payload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    payload = json.dumps({"type": "email.bounced"}).encode()
    headers = _sign(payload)
    tampered = json.dumps({"type": "email.delivered"}).encode()
    assert email_service.verify_webhook_signature(tampered, headers) is False


def test_verify_webhook_signature_rejects_when_secret_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", None)
    payload = json.dumps({"type": "email.bounced"}).encode()
    headers = _sign(payload)
    assert email_service.verify_webhook_signature(payload, headers) is False


async def test_handle_event_marks_the_notification_and_suppresses_the_address(owner: Actor, db) -> None:
    notification = Notification(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        channel=NotificationChannel.EMAIL,
        notification_type=NotificationType.WELCOME,
        recipient="bounced@example.com",
        title="Welcome",
        body="Hi",
        status=DeliveryStatus.SENT,
        provider_message_id="resend-msg-1",
    )
    db.add(notification)
    await db.commit()

    event = {
        "type": "email.bounced",
        "data": {"email_id": "resend-msg-1", "to": ["bounced@example.com"]},
    }
    await email_service.handle_event(db, event)

    await db.refresh(notification)
    assert notification.status == DeliveryStatus.BOUNCED
    assert await email_service.is_suppressed(db, "bounced@example.com") is True


async def test_handle_event_ignores_event_types_it_does_not_act_on(db) -> None:
    await email_service.handle_event(db, {"type": "email.delivered", "data": {}})
    assert await email_service.is_suppressed(db, "irrelevant@example.com") is False


async def test_resend_webhook_endpoint_rejects_an_unsigned_request(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    response = await client.post("/api/v1/webhooks/resend", content=b'{"type": "email.bounced"}')
    assert response.status_code == 401


async def test_resend_webhook_endpoint_accepts_a_signed_complaint(
    client: AsyncClient, monkeypatch, owner: Actor, db
) -> None:
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    notification = Notification(
        organization_id=user.organization_id,
        channel=NotificationChannel.EMAIL,
        notification_type=NotificationType.WELCOME,
        user_id=user.id,
        recipient=user.email,
        title="Welcome",
        body="Hi",
        status=DeliveryStatus.SENT,
        provider_message_id="resend-msg-2",
    )
    db.add(notification)
    await db.commit()

    payload = json.dumps(
        {"type": "email.complained", "data": {"email_id": "resend-msg-2", "to": [user.email]}}
    ).encode()
    headers = _sign(payload)

    response = await client.post("/api/v1/webhooks/resend", content=payload, headers=headers)
    assert response.status_code == 200, response.text

    assert await email_service.is_suppressed(db, user.email) is True


async def test_send_skips_a_suppressed_email_address(owner: Actor, db) -> None:
    from app.services import notification_service

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    await email_service.suppress(db, user.email, EmailSuppressionReason.BOUNCED)
    await db.commit()

    written = await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_user(user),
        notification_type=NotificationType.WELCOME,
        title="Welcome back",
        body="Hi",
        channels=[NotificationChannel.EMAIL],
    )
    await db.commit()

    assert len(written) == 1
    assert written[0].status == DeliveryStatus.SKIPPED
    assert "suppress" in (written[0].error or "").lower()
