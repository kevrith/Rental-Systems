"""Paystack card collections — the card alternative to an M-Pesa STK push.

Paystack's Standard flow is a redirect, not a push: we initialise a transaction,
send the tenant to the `authorization_url` Paystack hands back, and learn the
outcome from a webhook. The confirmation path mirrors `mpesa_service` because
the same hazards apply:

  * every webhook body is HMAC-verified before it is parsed at all;
  * a Redis lock makes concurrent deliveries of the same event a no-op;
  * the transaction reference is unique in the database, so the same charge can
    never be banked twice even if every other guard is bypassed;
  * a verified webhook is still re-checked against Paystack's own API before the
    money is treated as received — the webhook alone is not proof.

With no secret key configured `is_configured()` is False and the card option is
hidden rather than offered and then failing at the last step.
"""

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.redis import redis_client

logger = logging.getLogger("rentflow.paystack")

_WEBHOOK_LOCK_TTL = 300

# Paystack works in the currency's minor unit — kobo for NGN, cents for KES.
_MINOR_UNITS = Decimal("100")


class PaystackError(RuntimeError):
    pass


@dataclass(slots=True)
class InitializeResult:
    reference: str
    authorization_url: str
    access_code: str


@dataclass(slots=True)
class ChargeResult:
    reference: str
    success: bool
    status: str
    amount: Decimal | None = None
    paid_at: datetime | None = None
    channel: str | None = None
    gateway_response: str | None = None


def is_configured() -> bool:
    return bool(settings.PAYSTACK_SECRET_KEY)


def _headers() -> dict[str, str]:
    if not settings.PAYSTACK_SECRET_KEY:
        raise PaystackError("Paystack is not configured")
    return {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _to_minor_units(amount: Decimal) -> int:
    """KES 1,250.50 -> 125050. Paystack rejects a fractional minor unit."""
    return int((Decimal(amount) * _MINOR_UNITS).quantize(Decimal("1")))


def _from_minor_units(value: Any) -> Decimal | None:
    try:
        return (Decimal(str(value)) / _MINOR_UNITS).quantize(Decimal("0.01"))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _parse_paid_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def initialize_transaction(
    *,
    email: str,
    amount: Decimal,
    payment_id: uuid.UUID,
    tenancy_reference: str,
    callback_url: str,
) -> InitializeResult:
    """Open a card transaction and get back the URL to send the tenant to.

    `reference` is our own payment id rather than a Paystack-generated one, so a
    webhook can be matched to a payment even if the response below never
    arrives.
    """
    reference = f"rentflow-{payment_id}"
    payload = {
        "email": email,
        "amount": _to_minor_units(amount),
        "currency": "KES",
        "reference": reference,
        "callback_url": callback_url,
        "metadata": {
            "payment_id": str(payment_id),
            "tenancy_reference": tenancy_reference,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                f"{settings.PAYSTACK_BASE_URL}/transaction/initialize",
                json=payload,
                headers=_headers(),
            )
        except httpx.HTTPError as exc:
            raise PaystackError(f"Could not reach Paystack: {exc}") from exc

    body = _json(response)
    if response.status_code >= 400 or not body.get("status"):
        raise PaystackError(str(body.get("message") or "Paystack rejected the transaction"))

    data = body.get("data") or {}
    authorization_url = data.get("authorization_url")
    if not authorization_url:
        raise PaystackError("Paystack did not return an authorization URL")

    return InitializeResult(
        reference=str(data.get("reference") or reference),
        authorization_url=str(authorization_url),
        access_code=str(data.get("access_code") or ""),
    )


async def verify_transaction(reference: str) -> ChargeResult:
    """Ask Paystack what actually happened. This, not the webhook, is what the
    money is banked on."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                f"{settings.PAYSTACK_BASE_URL}/transaction/verify/{reference}",
                headers=_headers(),
            )
        except httpx.HTTPError as exc:
            raise PaystackError(f"Could not reach Paystack: {exc}") from exc

    body = _json(response)
    if response.status_code >= 400 or not body.get("status"):
        raise PaystackError(str(body.get("message") or "Paystack could not verify the transaction"))

    data = body.get("data") or {}
    state = str(data.get("status") or "unknown")
    return ChargeResult(
        reference=str(data.get("reference") or reference),
        success=state == "success",
        status=state,
        amount=_from_minor_units(data.get("amount")),
        paid_at=_parse_paid_at(data.get("paid_at") or data.get("paidAt")),
        channel=str(data.get("channel")) if data.get("channel") else None,
        gateway_response=str(data.get("gateway_response")) if data.get("gateway_response") else None,
    )


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise PaystackError(f"Paystack returned a non-JSON response ({response.status_code})") from None
    return body if isinstance(body, dict) else {}


def verify_webhook_signature(payload: bytes, signature: str | None) -> bool:
    """Paystack signs the raw body with HMAC-SHA512 keyed by the secret key.

    Verified against the exact bytes received — re-serialising the parsed JSON
    would change the whitespace and never match.
    """
    if not settings.PAYSTACK_SECRET_KEY:
        logger.warning("Rejected a Paystack webhook: PAYSTACK_SECRET_KEY is not configured")
        return False
    if not signature:
        return False

    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), payload, hashlib.sha512).hexdigest()
    return hmac.compare_digest(signature, expected)


def parse_event(body: dict[str, Any]) -> ChargeResult:
    """Read the charge outcome out of an already-verified webhook body."""
    event = str(body.get("event") or "")
    data = body.get("data") or {}
    reference = str(data.get("reference") or "")
    if not reference:
        raise PaystackError("Webhook carried no transaction reference")

    state = str(data.get("status") or "")
    return ChargeResult(
        reference=reference,
        success=event == "charge.success" and state == "success",
        status=state or event,
        amount=_from_minor_units(data.get("amount")),
        paid_at=_parse_paid_at(data.get("paid_at") or data.get("paidAt")),
        channel=str(data.get("channel")) if data.get("channel") else None,
        gateway_response=str(data.get("gateway_response")) if data.get("gateway_response") else None,
    )


async def claim_webhook(reference: str) -> bool:
    """First caller for a given reference wins; duplicates are dropped."""
    key = f"paystack:webhook:{reference}"
    return bool(await redis_client.set(key, "1", ex=_WEBHOOK_LOCK_TTL, nx=True))
