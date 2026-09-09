"""Paystack card collections — the card route into the same confirmation path
M-Pesa uses (see `payment_service._confirm`).

The webhook is the only unauthenticated way money can be marked received, so
most of what is worth testing here is what it *refuses*: an unsigned body, a
tampered one, a replayed one, and a "success" event that Paystack's own verify
endpoint does not corroborate.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models.billing import Payment, PaymentMethod, PaymentStatus
from app.services import paystack_service
from tests.conftest import Actor
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant

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


async def test_webhook_confirms_a_card_payment_end_to_end(
    owner: Actor, client: AsyncClient, db, monkeypatch
) -> None:
    """A signed charge.success, corroborated by verify, settles the invoice and
    receipts it — the same outcome an M-Pesa callback produces."""
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)

    prop = await make_property(owner, name="Card Court")
    unit = await make_unit(owner, prop["id"], unit_number="C1", monthly_rent="25000.00")
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], monthly_rent="25000.00", billing_day=1)
    invoice = (await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancy["id"]})).json()

    reference = f"rentflow-{uuid.uuid4()}"
    payment = Payment(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        reference_code="PMT-CARD-1",
        tenancy_id=uuid.UUID(tenancy["id"]),
        amount=Decimal("25000.00"),
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
        paystack_reference=reference,
    )
    db.add(payment)
    await db.commit()

    async def fake_verify(ref: str) -> paystack_service.ChargeResult:
        return paystack_service.ChargeResult(
            reference=ref,
            success=True,
            status="success",
            amount=Decimal("25000.00"),
            paid_at=datetime.now(UTC),
            channel="card",
            gateway_response="Successful",
        )

    monkeypatch.setattr(paystack_service, "verify_transaction", fake_verify)

    body = json.dumps(_charge_event(reference, 25000)).encode()
    response = await client.post(
        "/api/v1/paystack/webhook",
        content=body,
        headers={"x-paystack-signature": _sign(body), "content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Payment confirmed"

    settled = (await owner.get(f"/api/v1/payments/{payment.id}")).json()
    assert settled["status"] == "confirmed"
    assert settled["method"] == "card"
    assert settled["receipt"]["reference_code"].startswith("RCT-")

    settled_invoice = (await owner.get(f"/api/v1/invoices/{invoice['id']}")).json()
    assert settled_invoice["status"] == "paid"


async def test_webhook_ignores_a_replayed_delivery(
    owner: Actor, client: AsyncClient, db, monkeypatch
) -> None:
    """Paystack re-delivers what it thinks we missed; the money is banked once."""
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)

    prop = await make_property(owner, name="Replay Court")
    unit = await make_unit(owner, prop["id"], unit_number="R1", monthly_rent="10000.00")
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], monthly_rent="10000.00", billing_day=1)

    reference = f"rentflow-{uuid.uuid4()}"
    payment = Payment(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        reference_code="PMT-CARD-2",
        tenancy_id=uuid.UUID(tenancy["id"]),
        amount=Decimal("10000.00"),
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
        paystack_reference=reference,
    )
    db.add(payment)
    await db.commit()

    async def fake_verify(ref: str) -> paystack_service.ChargeResult:
        return paystack_service.ChargeResult(
            reference=ref, success=True, status="success", amount=Decimal("10000.00")
        )

    monkeypatch.setattr(paystack_service, "verify_transaction", fake_verify)

    body = json.dumps(_charge_event(reference, 10000)).encode()
    headers = {"x-paystack-signature": _sign(body), "content-type": "application/json"}

    first = await client.post("/api/v1/paystack/webhook", content=body, headers=headers)
    second = await client.post("/api/v1/paystack/webhook", content=body, headers=headers)

    assert first.json()["detail"] == "Payment confirmed"
    assert second.json()["detail"] == "Duplicate event ignored"

    payments = (await owner.get("/api/v1/payments")).json()
    confirmed = [p for p in payments if p["paystack_reference"] == reference]
    assert len(confirmed) == 1


async def test_webhook_does_not_bank_a_charge_paystack_will_not_corroborate(
    owner: Actor, client: AsyncClient, db, monkeypatch
) -> None:
    """A forged-but-correctly-signed body still has to survive verification."""
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", SECRET_KEY)

    prop = await make_property(owner, name="Forged Court")
    unit = await make_unit(owner, prop["id"], unit_number="F1", monthly_rent="5000.00")
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], monthly_rent="5000.00", billing_day=1)

    reference = f"rentflow-{uuid.uuid4()}"
    payment = Payment(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        reference_code="PMT-CARD-3",
        tenancy_id=uuid.UUID(tenancy["id"]),
        amount=Decimal("5000.00"),
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
        paystack_reference=reference,
    )
    db.add(payment)
    await db.commit()

    async def fake_verify(ref: str) -> paystack_service.ChargeResult:
        return paystack_service.ChargeResult(
            reference=ref, success=False, status="abandoned", gateway_response="Abandoned"
        )

    monkeypatch.setattr(paystack_service, "verify_transaction", fake_verify)

    body = json.dumps(_charge_event(reference, 5000)).encode()
    response = await client.post(
        "/api/v1/paystack/webhook",
        content=body,
        headers={"x-paystack-signature": _sign(body), "content-type": "application/json"},
    )
    assert response.status_code == 200

    settled = (await owner.get(f"/api/v1/payments/{payment.id}")).json()
    assert settled["status"] == "failed"


async def test_portal_reports_card_as_unavailable_without_a_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", None)
    assert paystack_service.is_configured() is False
