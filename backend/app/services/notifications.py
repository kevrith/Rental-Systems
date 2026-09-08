"""Outbound message providers: SMS, WhatsApp and Web Push.

Each provider has a console implementation used whenever its credentials are
absent, so every notification path is exercisable in development — messages land
in the application log instead of a phone. `notification_service` picks the
provider; nothing else should talk to these classes directly.
"""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.crypto import mask
from app.core.logging import sanitize_for_log

logger = logging.getLogger("rentflow.notifications")


@dataclass(slots=True)
class DeliveryResult:
    success: bool
    provider_message_id: str | None = None
    error: str | None = None


def normalize_phone(phone_number: str) -> str:
    """Coerce Kenyan numbers to E.164 (+2547XXXXXXXX).

    Accepts 07…, 7…, 254… and +254… — the four forms landlords actually type.
    """
    digits = "".join(ch for ch in phone_number if ch.isdigit())
    if digits.startswith("254"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+254{digits[1:]}"
    if len(digits) == 9 and digits[0] in "17":
        return f"+254{digits}"
    return phone_number if phone_number.startswith("+") else f"+{digits}"


# --------------------------------------------------------------------------- SMS


class SmsNotifier(Protocol):
    # lgtm[py/ineffectual-statement]
    async def send(self, phone_number: str, message: str) -> DeliveryResult: ...


class ConsoleSmsNotifier:
    """Local-dev stand-in that logs instead of sending a real SMS.

    `message` is never logged in full — it routinely carries a login or phone
    verification OTP (see auth_service), and a code sitting in clear text in a
    log line defeats the second factor for anyone who can read logs.
    """

    async def send(self, phone_number: str, message: str) -> DeliveryResult:
        logger.info("SMS to %s (%d chars)", mask(normalize_phone(phone_number)), len(message))
        return DeliveryResult(success=True, provider_message_id="console")


class AfricasTalkingSmsNotifier:
    """Africa's Talking REST API. Used whenever credentials are configured."""

    @property
    def base_url(self) -> str:
        if (settings.AFRICAS_TALKING_USERNAME or "").lower() == "sandbox":
            return "https://api.sandbox.africastalking.com/version1/messaging"
        return "https://api.africastalking.com/version1/messaging"

    async def send(self, phone_number: str, message: str) -> DeliveryResult:
        payload: dict[str, str] = {
            "username": settings.AFRICAS_TALKING_USERNAME or "",
            "to": normalize_phone(phone_number),
            "message": message,
        }
        if settings.AFRICAS_TALKING_SENDER_ID:
            payload["from"] = settings.AFRICAS_TALKING_SENDER_ID

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    self.base_url,
                    data=payload,
                    headers={
                        "apiKey": settings.AFRICAS_TALKING_API_KEY or "",
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                response.raise_for_status()
                recipients = response.json().get("SMSMessageData", {}).get("Recipients", [])
                if recipients and recipients[0].get("status") == "Success":
                    logger.info("AT SMS sent to %s: messageId=%s", mask(normalize_phone(phone_number)), recipients[0].get("messageId"))
                    return DeliveryResult(success=True, provider_message_id=recipients[0].get("messageId"))
                reason = recipients[0].get("status") if recipients else "No recipients accepted"
                logger.warning("AT SMS rejected for %s: %s", mask(normalize_phone(phone_number)), reason)
                return DeliveryResult(success=False, error=str(reason))
        except httpx.HTTPError as exc:
            logger.warning("Africa's Talking SMS failed for %s: %s", mask(normalize_phone(phone_number)), exc)
            return DeliveryResult(success=False, error=str(exc)[:500])


@lru_cache
def get_sms_notifier() -> SmsNotifier:
    if settings.AFRICAS_TALKING_USERNAME and settings.AFRICAS_TALKING_API_KEY:
        logger.info("SMS notifier: AfricasTalking (username=%s)", settings.AFRICAS_TALKING_USERNAME)
        return AfricasTalkingSmsNotifier()
    logger.info("SMS notifier: Console (AT credentials not set)")
    return ConsoleSmsNotifier()


# ---------------------------------------------------------------------- WhatsApp


class WhatsAppNotifier(Protocol):
    # lgtm[py/ineffectual-statement]
    async def send_text(self, phone_number: str, message: str) -> DeliveryResult: ...

    # lgtm[py/ineffectual-statement]
    async def send_document(
        self, phone_number: str, document_url: str, filename: str, caption: str | None = None
    ) -> DeliveryResult: ...


class ConsoleWhatsAppNotifier:
    """Local-dev stand-in — see ConsoleSmsNotifier for why `message`/`document_url`
    (a signed, directly-usable link) are never logged in full."""

    async def send_text(self, phone_number: str, message: str) -> DeliveryResult:
        logger.info("WhatsApp to %s (%d chars)", mask(normalize_phone(phone_number)), len(message))
        return DeliveryResult(success=True, provider_message_id="console")

    async def send_document(
        self, phone_number: str, document_url: str, filename: str, caption: str | None = None
    ) -> DeliveryResult:
        logger.info(
            "WhatsApp document to %s: %s (caption: %s)",
            mask(normalize_phone(phone_number)),
            filename,
            "yes" if caption else "no",
        )
        return DeliveryResult(success=True, provider_message_id="console")


class CloudApiWhatsAppNotifier:
    """WhatsApp Business Cloud API (Meta Graph)."""

    async def _post(self, payload: dict[str, Any]) -> DeliveryResult:
        url = f"{settings.WHATSAPP_API_BASE_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                messages = response.json().get("messages", [])
                return DeliveryResult(
                    success=True, provider_message_id=messages[0].get("id") if messages else None
                )
        except httpx.HTTPError as exc:
            logger.warning("WhatsApp send failed: %s", exc)
            return DeliveryResult(success=False, error=str(exc)[:500])

    async def send_text(self, phone_number: str, message: str) -> DeliveryResult:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": normalize_phone(phone_number).lstrip("+"),
                "type": "text",
                "text": {"preview_url": False, "body": message},
            }
        )

    async def send_document(
        self, phone_number: str, document_url: str, filename: str, caption: str | None = None
    ) -> DeliveryResult:
        document: dict[str, str] = {"link": document_url, "filename": filename}
        if caption:
            document["caption"] = caption
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": normalize_phone(phone_number).lstrip("+"),
                "type": "document",
                "document": document,
            }
        )


@lru_cache
def get_whatsapp_notifier() -> WhatsAppNotifier:
    if settings.WHATSAPP_API_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID:
        return CloudApiWhatsAppNotifier()
    return ConsoleWhatsAppNotifier()


# -------------------------------------------------------------------------- Push


class PushNotifier(Protocol):
    # lgtm[py/ineffectual-statement]
    async def send(self, subscription_info: dict[str, Any], payload: dict[str, Any]) -> DeliveryResult: ...


class ConsolePushNotifier:
    async def send(self, subscription_info: dict[str, Any], payload: dict[str, Any]) -> DeliveryResult:
        logger.info("Push to %s: %s", subscription_info.get("endpoint", "?")[:60], payload.get("title"))
        return DeliveryResult(success=True, provider_message_id="console")


class WebPushNotifier:
    """VAPID Web Push. Raises `PushExpired` upward as a failed result so the caller
    can prune dead subscriptions."""

    async def send(self, subscription_info: dict[str, Any], payload: dict[str, Any]) -> DeliveryResult:
        import anyio
        from pywebpush import WebPushException, webpush

        def _send() -> None:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
            )

        try:
            await anyio.to_thread.run_sync(_send)
            return DeliveryResult(success=True)
        except WebPushException as exc:
            gone = exc.response is not None and exc.response.status_code in (404, 410)
            return DeliveryResult(success=False, error=("expired" if gone else str(exc)[:500]))


@lru_cache
def get_push_notifier() -> PushNotifier:
    if settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY:
        return WebPushNotifier()
    return ConsolePushNotifier()


# ------------------------------------------------------------------------- Email


class EmailNotifier(Protocol):
    # lgtm[py/ineffectual-statement]
    async def send(self, to: str, subject: str, html: str) -> DeliveryResult: ...


class ConsoleEmailNotifier:
    async def send(self, to: str, subject: str, html: str) -> DeliveryResult:
        logger.info("Email to %s | %s", sanitize_for_log(to), sanitize_for_log(subject))
        return DeliveryResult(success=True, provider_message_id="console")


class ResendEmailNotifier:
    async def send(self, to: str, subject: str, html: str) -> DeliveryResult:
        import anyio
        import resend

        resend.api_key = settings.RESEND_API_KEY

        def _send() -> resend.Email:
            return resend.Emails.send(
                {
                    "from": settings.EMAIL_FROM,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                }
            )

        try:
            result = await anyio.to_thread.run_sync(_send)
            return DeliveryResult(success=True, provider_message_id=result.get("id"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Resend email failed for %s: %s", to, exc)
            return DeliveryResult(success=False, error=str(exc)[:500])


@lru_cache
def get_email_notifier() -> EmailNotifier:
    if settings.RESEND_API_KEY:
        return ResendEmailNotifier()
    return ConsoleEmailNotifier()
