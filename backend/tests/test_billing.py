"""Sprint 4: M-Pesa STK push, cash payments, invoices, receipts, arrears."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.services import invoice_service, receipt_service
from tests.conftest import Actor
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant


async def setup_tenancy(owner: Actor, rent: str = "25000.00", billing_day: int = 1) -> dict:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"], monthly_rent=rent)
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], monthly_rent=rent, billing_day=billing_day)
    return {"property": prop, "unit": unit, "tenant": tenant, "tenancy": tenancy}


def daraja_callback(checkout_id: str, receipt: str, amount: float, phone: str = "254712345678") -> dict:
    return {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "merchant-1",
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": amount},
                        {"Name": "MpesaReceiptNumber", "Value": receipt},
                        {"Name": "TransactionDate", "Value": "20260903120000"},
                        {"Name": "PhoneNumber", "Value": phone},
                    ]
                },
            }
        }
    }


# ------------------------------------------------------------------------ invoices


async def test_invoice_itemises_rent_and_gets_a_dated_reference(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="30000.00")

    response = await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    assert response.status_code == 201, response.text
    invoice = response.json()
    assert invoice["reference_code"].startswith(f"INV-{date.today():%Y-%m}")
    assert Decimal(invoice["total"]) == Decimal("30000.00")
    assert invoice["status"] == "pending"

    rent_line = next(i for i in invoice["line_items"] if i["kind"] == "rent")
    assert Decimal(rent_line["amount"]) == Decimal("30000.00")


async def test_generating_the_same_period_twice_is_refused(owner: Actor) -> None:
    """Idempotency is what makes the daily Celery run safe (US-021)."""
    setup = await setup_tenancy(owner)
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    second = await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


async def test_invoice_pdf_is_generated_and_filed(owner: Actor) -> None:
    setup = await setup_tenancy(owner)
    invoice = (
        await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    ).json()

    assert invoice["document_id"] is not None
    assert invoice["document_url"]

    documents = await owner.get(f"/api/v1/tenants/{setup['tenant']['id']}/documents")
    assert any(d["category"] == "invoice" for d in documents.json())


async def test_arrears_are_carried_forward_onto_the_next_invoice(owner: Actor, db) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    tenancy_id = uuid.UUID(setup["tenancy"]["id"])

    from app.models.tenant import Tenancy

    tenancy = await db.get(Tenancy, tenancy_id)

    # Bill the previous two months so an unpaid balance exists.
    two_months_ago = date.today().replace(day=1) - timedelta(days=45)
    await invoice_service.generate_invoice_for_tenancy(db, tenancy, two_months_ago, notify=False)
    await db.commit()

    current = await invoice_service.generate_invoice_for_tenancy(db, tenancy, date.today(), notify=False)
    await db.commit()

    kinds = {item.kind.value: item.amount for item in current.line_items}
    assert "arrears" in kinds
    assert Decimal(kinds["arrears"]) == Decimal("10000.00")
    assert Decimal(current.total) == Decimal("20000.00")


# ------------------------------------------------------------------- cash payment


async def test_cash_payment_settles_the_invoice_and_issues_a_receipt(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="25000.00")
    invoice = (
        await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    ).json()

    response = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
            "notes": "Collected at the gate",
        },
    )

    assert response.status_code == 201, response.text
    payment = response.json()
    assert payment["status"] == "confirmed"
    assert payment["reference_code"].startswith("PMT-")
    assert payment["receipt"]["reference_code"].startswith("RCT-")
    assert payment["receipt_url"]
    assert Decimal(payment["receipt"]["balance_after"]) == Decimal("0.00")

    settled = await owner.get(f"/api/v1/invoices/{invoice['id']}")
    assert settled.json()["status"] == "paid"
    assert Decimal(settled.json()["balance"]) == Decimal("0.00")


async def test_partial_payment_leaves_a_tracked_balance(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="25000.00")
    invoice = (
        await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    ).json()

    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "10000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )

    updated = (await owner.get(f"/api/v1/invoices/{invoice['id']}")).json()
    assert updated["status"] == "partially_paid"
    assert Decimal(updated["balance"]) == Decimal("15000.00")


async def test_payments_settle_the_oldest_invoice_first(owner: Actor, db) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    from app.models.tenant import Tenancy

    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))

    old = await invoice_service.generate_invoice_for_tenancy(
        db, tenancy, date.today().replace(day=1) - timedelta(days=45), notify=False
    )
    await db.commit()
    old_id = old.id

    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "10000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )

    settled = await db.get(Invoice, old_id)
    await db.refresh(settled)
    assert settled.status == InvoiceStatus.PAID


async def test_receipt_signature_is_verifiable(owner: Actor, db) -> None:
    """A doctored receipt fails re-derivation of its HMAC (US-023)."""
    setup = await setup_tenancy(owner)
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    created = (
        await owner.post(
            "/api/v1/payments",
            json={
                "tenancy_id": setup["tenancy"]["id"],
                "amount": "25000.00",
                "payment_date": date.today().isoformat(),
                "method": "cash",
            },
        )
    ).json()

    from sqlalchemy.orm import selectinload

    payment = await db.scalar(
        select(Payment).options(selectinload(Payment.receipt)).where(Payment.id == uuid.UUID(created["id"]))
    )
    assert receipt_service.is_authentic(payment.receipt, payment) is True

    # Alter the amount and the signature no longer matches.
    payment.amount = Decimal("999999.00")
    assert receipt_service.is_authentic(payment.receipt, payment) is False


async def test_a_negative_payment_is_rejected(owner: Actor) -> None:
    setup = await setup_tenancy(owner)

    response = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "-500",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )
    assert response.status_code == 422


# ------------------------------------------------------------------------ M-Pesa


async def test_stk_push_creates_a_pending_payment(owner: Actor) -> None:
    setup = await setup_tenancy(owner)

    response = await owner.post(
        "/api/v1/payments/stk-push",
        json={"tenancy_id": setup["tenancy"]["id"], "amount": "25000.00"},
    )

    assert response.status_code == 202, response.text
    assert response.json()["payment"]["status"] == "pending"
    assert response.json()["payment"]["method"] == "mpesa"
    assert response.json()["message"]


async def test_daraja_callback_confirms_the_payment_and_receipts_it(
    owner: Actor, client: AsyncClient, db
) -> None:
    setup = await setup_tenancy(owner)
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    pushed = (
        await owner.post(
            "/api/v1/payments/stk-push",
            json={"tenancy_id": setup["tenancy"]["id"], "amount": "25000.00"},
        )
    ).json()

    payment = await db.get(Payment, uuid.UUID(pushed["payment"]["id"]))
    checkout_id = payment.mpesa_checkout_request_id

    response = await client.post(
        "/api/v1/mpesa/callback", json=daraja_callback(checkout_id, "SLK7RT91XZ", 25000)
    )

    assert response.status_code == 200
    assert response.json()["ResultCode"] == "0"
    assert response.json()["detail"] == "Payment confirmed"

    settled = (await owner.get(f"/api/v1/payments/{pushed['payment']['id']}")).json()
    assert settled["status"] == "confirmed"
    assert settled["mpesa_receipt"] == "SLK7RT91XZ"
    assert settled["receipt"]["reference_code"].startswith("RCT-")


async def test_a_duplicate_callback_is_ignored(owner: Actor, client: AsyncClient, db) -> None:
    """Daraja retries; the money must only ever be banked once (US-019)."""
    setup = await setup_tenancy(owner)
    pushed = (
        await owner.post(
            "/api/v1/payments/stk-push",
            json={"tenancy_id": setup["tenancy"]["id"], "amount": "25000.00"},
        )
    ).json()
    payment = await db.get(Payment, uuid.UUID(pushed["payment"]["id"]))
    body = daraja_callback(payment.mpesa_checkout_request_id, "SLK7RT91AA", 25000)

    first = await client.post("/api/v1/mpesa/callback", json=body)
    second = await client.post("/api/v1/mpesa/callback", json=body)

    assert first.json()["detail"] == "Payment confirmed"
    assert second.json()["detail"] == "Duplicate callback ignored"

    payments = (await owner.get("/api/v1/payments", params={"tenancy_id": setup["tenancy"]["id"]})).json()
    confirmed = [p for p in payments if p["status"] == "confirmed"]
    assert len(confirmed) == 1


async def test_the_same_mpesa_receipt_cannot_be_banked_twice(owner: Actor, client: AsyncClient, db) -> None:
    setup = await setup_tenancy(owner)

    first_push = (
        await owner.post(
            "/api/v1/payments/stk-push",
            json={"tenancy_id": setup["tenancy"]["id"], "amount": "25000.00"},
        )
    ).json()
    second_push = (
        await owner.post(
            "/api/v1/payments/stk-push",
            json={"tenancy_id": setup["tenancy"]["id"], "amount": "25000.00"},
        )
    ).json()

    first = await db.get(Payment, uuid.UUID(first_push["payment"]["id"]))
    second = await db.get(Payment, uuid.UUID(second_push["payment"]["id"]))

    await client.post(
        "/api/v1/mpesa/callback",
        json=daraja_callback(first.mpesa_checkout_request_id, "SHARED-REF-1", 25000),
    )
    response = await client.post(
        "/api/v1/mpesa/callback",
        json=daraja_callback(second.mpesa_checkout_request_id, "SHARED-REF-1", 25000),
    )

    assert response.json()["detail"] == "Duplicate M-Pesa receipt ignored"
    await db.refresh(second)
    assert second.status == PaymentStatus.FAILED


async def test_a_cancelled_push_is_marked_cancelled(owner: Actor, client: AsyncClient, db) -> None:
    setup = await setup_tenancy(owner)
    pushed = (
        await owner.post(
            "/api/v1/payments/stk-push",
            json={"tenancy_id": setup["tenancy"]["id"], "amount": "25000.00"},
        )
    ).json()
    payment = await db.get(Payment, uuid.UUID(pushed["payment"]["id"]))

    response = await client.post(
        "/api/v1/mpesa/callback",
        json={
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "m-1",
                    "CheckoutRequestID": payment.mpesa_checkout_request_id,
                    "ResultCode": 1032,
                    "ResultDesc": "Request cancelled by user",
                }
            }
        },
    )

    assert response.status_code == 200
    await db.refresh(payment)
    assert payment.status == PaymentStatus.CANCELLED
    assert "cancelled by user" in payment.failure_reason


async def test_an_unrecognised_callback_is_answered_not_crashed(client: AsyncClient) -> None:
    response = await client.post("/api/v1/mpesa/callback", json={"nonsense": True})

    assert response.status_code == 200
    assert "Ignored" in response.json()["detail"]


async def test_a_callback_for_an_unknown_checkout_id_is_handled(client: AsyncClient) -> None:
    response = await client.post("/api/v1/mpesa/callback", json=daraja_callback("ws_CO_UNKNOWN", "REF", 100))
    assert response.json()["detail"] == "No matching payment"


# ------------------------------------------------------------------------ arrears


async def test_arrears_report_buckets_by_age(owner: Actor, db) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    from app.models.tenant import Tenancy

    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))

    old = await invoice_service.generate_invoice_for_tenancy(
        db, tenancy, date.today() - timedelta(days=75), notify=False
    )
    await db.commit()
    # Force the due date into the 61-90 day bucket.
    old.due_date = date.today() - timedelta(days=70)
    await db.commit()

    response = await owner.get("/api/v1/arrears")

    assert response.status_code == 200
    report = response.json()
    assert report["tenants_in_arrears"] == 1
    assert Decimal(report["total_arrears"]) == Decimal("10000.00")
    assert Decimal(report["aging"]["days_61_90"]) == Decimal("10000.00")

    row = report["rows"][0]
    assert row["tenant_name"] == "Peter Otieno"
    assert row["days_overdue"] == 70
    assert row["bucket"] == "days_61_90"


async def test_arrears_exclude_paid_invoices(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "10000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )

    report = (await owner.get("/api/v1/arrears")).json()
    assert report["tenants_in_arrears"] == 0
    assert Decimal(report["total_arrears"]) == Decimal("0.00")


async def test_arrears_export_produces_csv(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    response = await owner.get("/api/v1/arrears/export.csv")

    assert response.status_code == 200
    assert "Tenant,Phone,Property" in response.text
    assert "Peter Otieno" in response.text


async def test_reminders_can_be_sent_to_every_defaulter(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})

    response = await owner.post("/api/v1/arrears/remind", json={})

    assert response.status_code == 200
    assert response.json()["sent"] == 1


# ---------------------------------------------------------------------- dashboard


async def test_financial_dashboard_reports_collection_rate(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="20000.00")
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "15000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )

    response = await owner.get("/api/v1/dashboard/financial")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["expected_rent"]) == Decimal("20000.00")
    assert Decimal(body["collected"]) == Decimal("15000.00")
    assert body["collection_rate"] == 75.0
    assert Decimal(body["total_arrears"]) == Decimal("5000.00")
    assert body["occupancy_rate"] == 100.0
    assert len(body["monthly_chart"]) == 6
    assert len(body["recent_payments"]) == 1
    assert body["recent_payments"][0]["tenant_name"] == "Peter Otieno"


async def test_payments_from_another_organization_are_invisible(owner: Actor, other_owner: Actor) -> None:
    setup = await setup_tenancy(owner)
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    created = (
        await owner.post(
            "/api/v1/payments",
            json={
                "tenancy_id": setup["tenancy"]["id"],
                "amount": "1000",
                "payment_date": date.today().isoformat(),
                "method": "cash",
            },
        )
    ).json()

    assert (await other_owner.get(f"/api/v1/payments/{created['id']}")).status_code == 403
    assert (await other_owner.get("/api/v1/payments")).json() == []
