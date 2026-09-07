"""Sprint 24 (US-102): the chained golden path.

Every individual stage below already has its own dedicated test elsewhere
(invoice generation in test_billing.py, STK push and the Daraja callback in
the same file, lease generation in test_tenancy.py, the disbursement state
machine in test_phase2.py). What none of those cover is the *whole* thing
run back to back through nothing but the public HTTP API, the way a real
owner would actually use RentFlow in their first hour on the platform —
which is exactly the "golden path" Phase 1's own status note in
sprint-plan.md says was verified by hand against a live server and never
committed as a test. This closes that gap.
"""

import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from app.models.billing import Payment
from tests.conftest import Actor
from tests.test_billing import daraja_callback
from tests.test_portfolio import make_property
from tests.test_tenancy import make_tenancy, make_tenant


async def test_full_tenant_lifecycle_golden_path(owner: Actor, client: AsyncClient, db) -> None:
    """register -> property -> 6 units -> tenant -> tenancy + lease -> invoice
    -> M-Pesa payment + receipt -> dashboards reflect it (Phase 1's golden path)."""

    # ---- property, with a portfolio of units bulk-created in one call (US-008)
    prop = await make_property(owner, name="Riverside Apartments")
    bulk = await owner.post(
        "/api/v1/units/bulk",
        json={
            "property_id": prop["id"],
            "count": 6,
            "name_prefix": "RA-",
            "start_number": 1,
            "unit_type": "1 bedroom",
            "bedrooms": 1,
            "bathrooms": 1,
            "monthly_rent": "25000.00",
            "deposit_amount": "25000.00",
        },
    )
    assert bulk.status_code == 201, bulk.text
    units = bulk.json()["units"]
    assert bulk.json()["created"] == 6
    assert {u["unit_number"] for u in units} == {f"RA-{n}" for n in range(1, 7)}

    portfolio = (await owner.get("/api/v1/dashboard/portfolio")).json()
    assert portfolio["stats"]["total_units"] == 6
    assert portfolio["stats"]["vacant_units"] == 6
    assert portfolio["stats"]["occupied_units"] == 0

    # ---- tenant, onboarded onto one of those six units
    tenant = await make_tenant(owner, full_name="Amina Hassan")
    target_unit = units[0]
    tenancy = await make_tenancy(
        owner, tenant["id"], target_unit["id"], monthly_rent="25000.00", billing_day=1
    )

    # A lease PDF exists the moment the tenancy does (US-016) — no separate step.
    assert tenancy["lease_document_id"] is not None
    assert tenancy["lease_url"]
    lease_docs = [
        d
        for d in (await owner.get(f"/api/v1/tenants/{tenant['id']}/documents")).json()
        if d["category"] == "lease"
    ]
    assert len(lease_docs) == 1

    # The unit the tenancy landed on flips to occupied; the other five don't.
    unit_after = (await owner.get(f"/api/v1/units/{target_unit['id']}")).json()
    assert unit_after["status"] == "occupied"
    portfolio = (await owner.get("/api/v1/dashboard/portfolio")).json()
    assert portfolio["stats"]["occupied_units"] == 1
    assert portfolio["stats"]["vacant_units"] == 5

    # ---- invoice for the new tenancy
    invoice = (await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancy["id"]})).json()
    assert invoice["status"] == "pending"
    assert invoice["reference_code"].startswith(f"INV-{date.today():%Y-%m}")

    # ---- M-Pesa: STK push, then the Daraja callback that actually settles it
    pushed = (
        await owner.post(
            "/api/v1/payments/stk-push",
            json={"tenancy_id": tenancy["id"], "amount": "25000.00"},
        )
    ).json()
    assert pushed["payment"]["status"] == "pending"

    payment_row = await db.get(Payment, uuid.UUID(pushed["payment"]["id"]))
    callback = await client.post(
        "/api/v1/mpesa/callback",
        json=daraja_callback(payment_row.mpesa_checkout_request_id, "SLK9GOLDEN1", 25000),
    )
    assert callback.status_code == 200
    assert callback.json()["ResultCode"] == "0"

    settled_payment = (await owner.get(f"/api/v1/payments/{pushed['payment']['id']}")).json()
    assert settled_payment["status"] == "confirmed"
    assert settled_payment["mpesa_receipt"] == "SLK9GOLDEN1"
    assert settled_payment["receipt"]["reference_code"].startswith("RCT-")
    assert settled_payment["receipt_url"]

    settled_invoice = (await owner.get(f"/api/v1/invoices/{invoice['id']}")).json()
    assert settled_invoice["status"] == "paid"
    assert Decimal(settled_invoice["balance"]) == Decimal("0.00")

    # ---- both dashboards a real owner would look at next reflect all of this
    portfolio = (await owner.get("/api/v1/dashboard/portfolio")).json()
    assert portfolio["stats"]["occupied_units"] == 1
    assert Decimal(str(portfolio["stats"]["monthly_rent_contracted"])) == Decimal("25000.00")

    financial = (await owner.get("/api/v1/dashboard/financial")).json()
    assert Decimal(str(financial["collected"])) >= Decimal("25000.00")
    assert any(p["reference_code"] == settled_payment["reference_code"] for p in financial["recent_payments"])
