"""Paystack primitives — signature verification, event parsing, amounts.

Paystack carries RentFlow's own subscription revenue and nothing else. Rent is
collected by each landlord into their own M-Pesa and never passes through this
platform's Paystack account, so there is no tenant-facing card flow to test
here; `test_subscription_billing.py` covers what these primitives are used for.

The webhook is the only unauthenticated way a charge can be marked received, so
what matters most is what it *refuses*.
"""

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services import paystack_service

SECRET_KEY = "sk_test_paystack_key_for_tests"


def _sign(payload: bytes, secret: str = SECRET_KEY) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()


def _charge_event(reference: str, amount_kes: int, *, status: str = "success") -> dict:
    return {
        "event": "charge.success" if status == "success" else "charge.failed",
        "data": {
            "reference": reference,
            "status": status,
            "amount": amount_kes * 100,
            "currency": "KES",
            "channel": "card",
            "paid_at": "2026-09-09T09:30:00.000Z",
            "gateway_response": "Successful" if status == "success" else "Declined",
        },
    }


# ----------------------------------------------------------------- signatures


def test_signature_accepts_a_correctly_signed_body(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    payload = json.dumps(_charge_event("rentflow-1", 25000)).encode()
    assert paystack_service.verify_webhook_signature(payload, _sign(payload)) is True


def test_signature_rejects_a_tampered_body(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    payload = json.dumps(_charge_event("rentflow-1", 25000)).encode()
    signature = _sign(payload)
    tampered = json.dumps(_charge_event("rentflow-1", 999_000)).encode()
    assert paystack_service.verify_webhook_signature(tampered, signature) is False


def test_signature_rejects_a_body_signed_with_another_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    payload = json.dumps(_charge_event("rentflow-1", 25000)).encode()
    assert paystack_service.verify_webhook_signature(payload, _sign(payload, "sk_test_other")) is False


def test_signature_rejects_a_missing_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    payload = json.dumps(_charge_event("rentflow-1", 25000)).encode()
    assert paystack_service.verify_webhook_signature(payload, None) is False


def test_signature_rejects_everything_when_no_key_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", None)
    payload = json.dumps(_charge_event("rentflow-1", 25000)).encode()
    assert paystack_service.verify_webhook_signature(payload, _sign(payload)) is False
    assert paystack_service.is_configured() is False


# ----------------------------------------------------------------- event parsing


def test_parse_event_reads_a_successful_charge() -> None:
    result = paystack_service.parse_event(_charge_event("rentflow-abc", 25000))
    assert result.success is True
    assert result.reference == "rentflow-abc"
    assert result.amount == Decimal("25000.00")
    assert result.paid_at is not None and result.paid_at.tzinfo is not None


def test_parse_event_does_not_treat_a_failed_charge_as_success() -> None:
    result = paystack_service.parse_event(_charge_event("rentflow-abc", 25000, status="failed"))
    assert result.success is False


def test_parse_event_rejects_a_body_with_no_reference() -> None:
    with pytest.raises(paystack_service.PaystackError):
        paystack_service.parse_event({"event": "charge.success", "data": {}})


def test_amounts_convert_to_and_from_paystack_minor_units() -> None:
    assert paystack_service._to_minor_units(Decimal("1250.50")) == 125050
    assert paystack_service._from_minor_units(125050) == Decimal("1250.50")


# ----------------------------------------------------------------- the endpoint


async def test_webhook_refuses_an_unsigned_delivery(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)
    response = await client.post("/api/v1/paystack/webhook", json=_charge_event("rentflow-x", 100))
    assert response.status_code == 401
