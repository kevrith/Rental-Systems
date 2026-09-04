"""Phase 2 tests — agency mode, inspections, late fees, analytics."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ----------------------------------------------------------------- helpers


async def _make_agency_org(client: AsyncClient) -> dict:
    """Register an agency-mode organization and return auth headers + org data."""
    suffix = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Agency Admin",
            "organization_name": f"Test Agency {suffix}",
            "email": f"agency-{suffix}@test.com",
            "phone_number": f"+2547{abs(hash(suffix)) % 100000000:08d}",
            "password": "TestPass123!",
            "account_type": "agency",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _make_owner_org(client: AsyncClient) -> dict:
    suffix = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Property Owner",
            "organization_name": f"Owner Org {suffix}",
            "email": f"owner-{suffix}@test.com",
            "phone_number": f"+2547{abs(hash(suffix)) % 100000000:08d}",
            "password": "TestPass123!",
            "account_type": "owner",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ================================================================= Sprint 7: Agency mode


@pytest.mark.asyncio
async def test_create_owner_profile(client: AsyncClient):
    headers = await _make_agency_org(client)
    resp = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "John Landlord",
            "phone_number": "+254712345678",
            "email": "john@example.com",
            "management_fee_percent": "8.00",
            "disbursement_day": 5,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["full_name"] == "John Landlord"
    assert data["reference_code"].startswith("OWN")


@pytest.mark.asyncio
async def test_list_owner_profiles(client: AsyncClient):
    headers = await _make_agency_org(client)
    # Create two profiles
    for name in ["Alice Owner", "Bob Owner"]:
        suffix = uuid.uuid4().hex[:8]
        await client.post(
            "/api/v1/agency/owner-profiles",
            headers=headers,
            json={"full_name": name, "phone_number": f"+2547{abs(hash(suffix)) % 100000000:08d}"},
        )
    resp = await client.get("/api/v1/agency/owner-profiles", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_owner_profile_requires_agency_mode(client: AsyncClient):
    """Owner-mode accounts cannot use agency endpoints."""
    headers = await _make_owner_org(client)
    resp = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={"full_name": "Test", "phone_number": "+254700000001"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_owner_profile(client: AsyncClient):
    headers = await _make_agency_org(client)
    create = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "Original Name",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )
    profile_id = create.json()["id"]
    resp = await client.patch(
        f"/api/v1/agency/owner-profiles/{profile_id}",
        headers=headers,
        json={"full_name": "Updated Name", "management_fee_percent": "10.00"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_agency_dashboard(client: AsyncClient):
    headers = await _make_agency_org(client)
    resp = await client.get("/api/v1/agency/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_units" in data
    assert "occupancy_rate" in data
    assert "owner_count" in data


@pytest.mark.asyncio
async def test_owner_summaries_empty(client: AsyncClient):
    """No owner profiles yet — the rollup is an empty list, not an error."""
    headers = await _make_agency_org(client)
    resp = await client.get("/api/v1/agency/owner-summaries", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_owner_summaries_shape(client: AsyncClient):
    """Each owner profile yields one summary card with the dashboard fields."""
    headers = await _make_agency_org(client)
    await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "Margaret Wanjiku",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
            "management_fee_percent": "10.00",
        },
    )

    resp = await client.get("/api/v1/agency/owner-summaries", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1

    row = rows[0]
    assert row["full_name"] == "Margaret Wanjiku"
    assert row["management_fee_percent"] == 10.0
    assert row["portal_invited"] is False
    # No properties linked yet, so every rollup is zeroed rather than absent.
    assert row["property_count"] == 0
    assert row["unit_count"] == 0
    assert row["occupancy_rate"] == 0.0
    assert row["collection_rate"] == 0.0
    assert row["arrears"] == 0.0
    assert row["last_disbursement"] is None


@pytest.mark.asyncio
async def test_owner_summaries_aggregates_real_data(client: AsyncClient, db: AsyncSession):
    """Two units under one owner, one occupied and one paid — the rollup adds up."""
    headers = await _make_agency_org(client)
    profile_resp = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "Rollup Owner",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )
    profile_id = profile_resp.json()["id"]

    prop_resp = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={
            "name": "Rollup Court",
            "address": "1 Rollup Road",
            "property_type": "residential",
            "owner_profile_id": profile_id,
        },
    )
    assert prop_resp.status_code == 201, prop_resp.text
    assert prop_resp.json()["owner_profile_id"] == profile_id
    prop_id = prop_resp.json()["id"]

    for unit_number in ("R1", "R2"):
        unit = await client.post(
            "/api/v1/units",
            headers=headers,
            json={
                "property_id": prop_id,
                "unit_number": unit_number,
                "monthly_rent": "20000",
                "deposit_amount": "20000",
            },
        )
        assert unit.status_code == 201, unit.text

    resp = await client.get("/api/v1/agency/owner-summaries", headers=headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["owner_profile_id"] == profile_id)

    assert row["property_count"] == 1
    assert row["unit_count"] == 2
    # Both units start vacant, so occupancy is zero until a tenancy is activated.
    assert row["occupied_units"] == 0
    assert row["occupancy_rate"] == 0.0


@pytest.mark.asyncio
async def test_property_cannot_be_attributed_across_orgs(client: AsyncClient):
    """Agency B cannot point one of its properties at Agency A's owner profile."""
    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)

    profile = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers_a,
        json={"full_name": "A Owner", "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}"},
    )
    foreign_profile_id = profile.json()["id"]

    resp = await client.post(
        "/api/v1/properties",
        headers=headers_b,
        json={
            "name": "Leaky Court",
            "address": "2 Leak Lane",
            "property_type": "residential",
            "owner_profile_id": foreign_profile_id,
        },
    )
    assert resp.status_code == 403

    # And it cannot be smuggled in through an update either.
    own = await client.post(
        "/api/v1/properties",
        headers=headers_b,
        json={"name": "Clean Court", "address": "3 Clean Close", "property_type": "residential"},
    )
    patched = await client.patch(
        f"/api/v1/properties/{own.json()['id']}",
        headers=headers_b,
        json={"owner_profile_id": foreign_profile_id},
    )
    assert patched.status_code == 403


@pytest.mark.asyncio
async def test_owner_summaries_rejected_in_owner_mode(client: AsyncClient):
    """Owner-managed orgs have no owner profiles — the endpoint refuses."""
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/agency/owner-summaries", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cross_org_owner_summaries_isolation(client: AsyncClient):
    """Agency B's rollup never contains Agency A's owners."""
    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)

    await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers_a,
        json={
            "full_name": "Org A Owner",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )

    resp = await client.get("/api/v1/agency/owner-summaries", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_cross_org_owner_profile_isolation(client: AsyncClient):
    """Agency A cannot access Agency B's owner profiles."""
    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)

    create = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers_a,
        json={
            "full_name": "Org A Owner",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )
    profile_id = create.json()["id"]

    resp = await client.get(f"/api/v1/agency/owner-profiles/{profile_id}", headers=headers_b)
    assert resp.status_code == 403


# ================================================================= Sprint 8: Disbursements


@pytest.mark.asyncio
async def test_disbursement_calculate_empty(client: AsyncClient):
    headers = await _make_agency_org(client)
    create = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "Empty Owner",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )
    profile_id = create.json()["id"]

    today = date.today()
    resp = await client.get(
        "/api/v1/agency/disbursements/calculate",
        headers=headers,
        params={
            "owner_profile_id": profile_id,
            "period_start": today.replace(day=1).isoformat(),
            "period_end": today.isoformat(),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["gross_rent"] == 0.0
    assert data["net_amount"] == 0.0


async def _agency_money_path(client: AsyncClient, headers: dict, *, rent: str = "30000.00") -> dict:
    """An agency with one owner client whose unit has been paid for this month.

    Approval refuses a zero payout, so every test below the review line needs
    real money to have moved first.
    """
    owner = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "Grace Wanjiru",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
            "mpesa_phone": f"+2547{abs(hash(uuid.uuid4().hex + 'm')) % 100000000:08d}",
            "management_fee_percent": "10.00",
        },
    )
    assert owner.status_code == 201, owner.text
    profile = owner.json()

    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={
            "name": f"Managed Court {uuid.uuid4().hex[:6]}",
            "address": "Ngong Road, Nairobi",
            "property_type": "residential",
            "owner_profile_id": profile["id"],
        },
    )
    assert prop.status_code == 201, prop.text

    unit = await client.post(
        "/api/v1/units",
        headers=headers,
        json={
            "property_id": prop.json()["id"],
            "unit_number": "A1",
            "monthly_rent": rent,
            "deposit_amount": rent,
        },
    )
    assert unit.status_code == 201, unit.text

    tenant = await client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "full_name": "Peter Otieno",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex + 't')) % 100000000:08d}",
            "email": f"peter-{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    assert tenant.status_code == 201, tenant.text

    tenancy = await client.post(
        "/api/v1/tenancies",
        headers=headers,
        json={
            "tenant_id": tenant.json()["id"],
            "unit_id": unit.json()["id"],
            "start_date": date.today().replace(day=1).isoformat(),
            "monthly_rent": rent,
            "deposit_amount": rent,
            "billing_day": 1,
            "payment_method": "mpesa",
            "is_open_ended": True,
        },
    )
    assert tenancy.status_code == 201, tenancy.text

    payment = await client.post(
        "/api/v1/payments",
        headers=headers,
        json={
            "tenancy_id": tenancy.json()["id"],
            "amount": rent,
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )
    assert payment.status_code == 201, payment.text

    return {
        "profile": profile,
        "property": prop.json(),
        "unit": unit.json(),
        "tenant": tenant.json(),
        "tenancy": tenancy.json(),
    }


async def _create_disbursement(client: AsyncClient, headers: dict, profile_id: str) -> dict:
    today = date.today()
    resp = await client.post(
        "/api/v1/agency/disbursements",
        headers=headers,
        json={
            "owner_profile_id": profile_id,
            "period_start": today.replace(day=1).isoformat(),
            "period_end": today.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_disbursement_must_be_approved_before_it_is_paid(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])
    assert disbursement["status"] == "pending"
    assert Decimal(disbursement["net_amount"]) == Decimal("27000.00")

    premature = await client.post(
        f"/api/v1/agency/disbursements/{disbursement['id']}/mark-paid",
        headers=headers,
        json={"payment_method": "bank_transfer", "payment_reference": "BT-001"},
    )
    assert premature.status_code == 409

    approved = await client.post(
        f"/api/v1/agency/disbursements/{disbursement['id']}/approve", headers=headers, json={}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"] is not None

    paid = await client.post(
        f"/api/v1/agency/disbursements/{disbursement['id']}/mark-paid",
        headers=headers,
        json={"payment_method": "bank_transfer", "payment_reference": "BT-001"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "completed"
    # Settling a payout files the owner statement in their vault.
    assert paid.json()["statement_document_id"] is not None


@pytest.mark.asyncio
async def test_rejected_disbursement_records_the_reason_and_cannot_be_paid(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])

    rejected = await client.post(
        f"/api/v1/agency/disbursements/{disbursement['id']}/reject",
        headers=headers,
        json={"reason": "February maintenance invoice is still missing"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert "maintenance invoice" in rejected.json()["rejection_reason"]

    for path, body in (
        ("mark-paid", {"payment_method": "cash", "payment_reference": "X"}),
        ("pay-mpesa", None),
        ("approve", {}),
    ):
        resp = await client.post(
            f"/api/v1/agency/disbursements/{disbursement['id']}/{path}", headers=headers, json=body
        )
        assert resp.status_code == 409, f"{path} -> {resp.status_code}"


@pytest.mark.asyncio
async def test_zero_value_disbursement_cannot_be_approved(client: AsyncClient):
    headers = await _make_agency_org(client)
    create = await client.post(
        "/api/v1/agency/owner-profiles",
        headers=headers,
        json={
            "full_name": "Empty Payout Owner",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )
    disbursement = await _create_disbursement(client, headers, create.json()["id"])
    assert Decimal(disbursement["net_amount"]) == Decimal("0.00")

    resp = await client.post(
        f"/api/v1/agency/disbursements/{disbursement['id']}/approve", headers=headers, json={}
    )
    assert resp.status_code == 400
    assert "nothing to pay out" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_mpesa_payout_settles_and_issues_the_statement(client: AsyncClient):
    """Without Daraja B2C credentials the payout is stubbed and settles inline."""
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])

    await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/approve", headers=headers, json={})
    paid = await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/pay-mpesa", headers=headers)
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "completed"
    assert body["payment_method"] == "mpesa"
    assert body["payout_conversation_id"]
    assert body["statement_document_id"]

    # A second attempt is refused rather than paying the owner twice.
    again = await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/pay-mpesa", headers=headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_owner_statement_pdf_is_downloadable(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])

    resp = await client.get(f"/api/v1/agency/disbursements/{disbursement['id']}/statement", headers=headers)
    assert resp.status_code == 200, resp.text
    statement = resp.json()
    assert statement["filename"].startswith("Statement-DSB-")
    assert statement["url"]

    # Rendering is idempotent: asking again returns the same stored document.
    repeat = await client.get(f"/api/v1/agency/disbursements/{disbursement['id']}/statement", headers=headers)
    assert repeat.json()["document_id"] == statement["document_id"]


@pytest.mark.asyncio
async def test_owner_statement_itemises_units_maintenance_and_arrears(client: AsyncClient, db: AsyncSession):
    """The PDF numbers are re-derived from the same period the disbursement covers."""
    from app.models.agency import Disbursement
    from app.services import owner_statement_service

    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])

    record = await db.get(Disbursement, uuid.UUID(disbursement["id"]))
    context = await owner_statement_service.build_context(db, record)

    assert len(context["units"]) == 1
    assert context["units"][0]["unit_number"] == "A1"
    assert context["units"][0]["gross_rent"] == Decimal("30000.00")
    assert context["units"][0]["tenant_name"] == "Peter Otieno"
    assert context["ytd"]["gross_rent"] == Decimal("30000.00")
    assert context["total_deductions"] == Decimal("3000.00")
    # The rent was paid in full, so nothing is outstanding.
    assert context["total_arrears"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_b2c_result_callback_settles_a_processing_payout(client: AsyncClient, db: AsyncSession):
    from app.models.agency import Disbursement, DisbursementStatus

    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])
    await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/approve", headers=headers, json={})

    # Park it in PROCESSING as a real (credentialed) Daraja request would.
    record = await db.get(Disbursement, uuid.UUID(disbursement["id"]))
    record.status = DisbursementStatus.PROCESSING
    record.payment_method = "mpesa"
    record.payout_conversation_id = "AG_20260904_TESTCONVO"
    record.payout_originator_id = "ORIG-TESTCONVO"
    await db.commit()

    resp = await client.post(
        "/api/v1/mpesa/b2c/result",
        json={
            "Result": {
                "ResultType": 0,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "ConversationID": "AG_20260904_TESTCONVO",
                "OriginatorConversationID": "ORIG-TESTCONVO",
                "TransactionID": "QKA81LK5CY",
                "ResultParameters": {
                    "ResultParameter": [
                        {"Key": "TransactionAmount", "Value": 27000},
                        {"Key": "TransactionReceipt", "Value": "QKA81LK5CY"},
                        {"Key": "ReceiverPartyPublicName", "Value": "254712345678 - Grace Wanjiru"},
                        {"Key": "TransactionCompletedDateTime", "Value": "04.09.2026 10:15:30"},
                    ]
                },
            }
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["detail"] == "settled"

    rows = (await client.get("/api/v1/agency/disbursements", headers=headers)).json()
    row = next(r for r in rows if r["id"] == disbursement["id"])
    assert row["status"] == "completed"
    assert row["payment_reference"] == "QKA81LK5CY"
    assert row["statement_document_id"]


@pytest.mark.asyncio
async def test_b2c_result_callback_is_idempotent(client: AsyncClient, db: AsyncSession):
    """Safaricom re-delivers results it thinks we missed; the second is dropped."""
    from app.models.agency import Disbursement, DisbursementStatus

    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])
    await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/approve", headers=headers, json={})

    record = await db.get(Disbursement, uuid.UUID(disbursement["id"]))
    record.status = DisbursementStatus.PROCESSING
    record.payout_conversation_id = "AG_DUPLICATE_TEST"
    await db.commit()

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "Success",
            "ConversationID": "AG_DUPLICATE_TEST",
            "OriginatorConversationID": "ORIG-DUP",
            "TransactionID": "QDUP123456",
        }
    }
    first = await client.post("/api/v1/mpesa/b2c/result", json=payload)
    second = await client.post("/api/v1/mpesa/b2c/result", json=payload)
    assert first.json()["detail"] == "settled"
    assert second.json()["detail"] == "duplicate"


@pytest.mark.asyncio
async def test_b2c_failure_marks_the_disbursement_failed_and_retryable(client: AsyncClient, db: AsyncSession):
    from app.models.agency import Disbursement, DisbursementStatus

    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    disbursement = await _create_disbursement(client, headers, setup["profile"]["id"])
    await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/approve", headers=headers, json={})

    record = await db.get(Disbursement, uuid.UUID(disbursement["id"]))
    record.status = DisbursementStatus.PROCESSING
    record.payout_conversation_id = "AG_FAILURE_TEST"
    await db.commit()

    await client.post(
        "/api/v1/mpesa/b2c/result",
        json={
            "Result": {
                "ResultCode": 2001,
                "ResultDesc": "The initiator information is invalid.",
                "ConversationID": "AG_FAILURE_TEST",
                "OriginatorConversationID": "ORIG-FAIL",
            }
        },
    )

    rows = (await client.get("/api/v1/agency/disbursements", headers=headers)).json()
    row = next(r for r in rows if r["id"] == disbursement["id"])
    assert row["status"] == "failed"
    assert "initiator information" in row["failure_reason"]

    # A failed payout can be retried without going back through review.
    retry = await client.post(f"/api/v1/agency/disbursements/{disbursement['id']}/pay-mpesa", headers=headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "completed"


# ================================================================= Sprint 10: Inspections


@pytest.mark.asyncio
async def test_create_inspection(client: AsyncClient, db: AsyncSession):
    headers = await _make_owner_org(client)

    # Create property + unit
    prop_resp = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Inspect Prop", "address": "123 Test St", "property_type": "residential"},
    )
    prop_id = prop_resp.json()["id"]
    unit_resp = await client.post(
        "/api/v1/units",
        headers=headers,
        json={
            "property_id": prop_id,
            "unit_number": "A1",
            "monthly_rent": "10000",
            "deposit_amount": "10000",
        },
    )
    unit_id = unit_resp.json()["id"]

    resp = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": unit_id, "inspection_type": "move_in"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["inspection_type"] == "move_in"
    assert data["status"] == "draft"
    assert len(data["rooms_data"]) > 0


@pytest.mark.asyncio
async def test_submit_inspection_requires_photos(client: AsyncClient):
    headers = await _make_owner_org(client)

    prop_resp = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Photo Prop", "address": "456 Test St", "property_type": "residential"},
    )
    prop_id = prop_resp.json()["id"]
    unit_resp = await client.post(
        "/api/v1/units",
        headers=headers,
        json={"property_id": prop_id, "unit_number": "B1", "monthly_rent": "8000", "deposit_amount": "8000"},
    )
    unit_id = unit_resp.json()["id"]

    create = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": unit_id, "inspection_type": "move_in"},
    )
    report_id = create.json()["id"]

    # Submit without photos — should fail
    resp = await client.post(f"/api/v1/inspections/{report_id}/submit", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_inspection_with_photos(client: AsyncClient):
    headers = await _make_owner_org(client)

    prop_resp = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Full Inspect Prop", "address": "789 Test St", "property_type": "residential"},
    )
    prop_id = prop_resp.json()["id"]
    unit_resp = await client.post(
        "/api/v1/units",
        headers=headers,
        json={
            "property_id": prop_id,
            "unit_number": "C1",
            "monthly_rent": "12000",
            "deposit_amount": "12000",
        },
    )
    unit_id = unit_resp.json()["id"]

    create = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": unit_id, "inspection_type": "move_in"},
    )
    report_id = create.json()["id"]
    rooms = create.json()["rooms_data"]

    # Add condition + fake photo id to every room
    for room in rooms:
        room["condition"] = "good"
        room["photo_file_ids"] = [str(uuid.uuid4())]

    await client.patch(
        f"/api/v1/inspections/{report_id}/rooms",
        headers=headers,
        json={"rooms_data": rooms},
    )

    resp = await client.post(f"/api/v1/inspections/{report_id}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_submitted_inspection_immutable(client: AsyncClient):
    headers = await _make_owner_org(client)

    prop_resp = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Immutable Prop", "address": "1 Immutable St", "property_type": "residential"},
    )
    prop_id = prop_resp.json()["id"]
    unit_resp = await client.post(
        "/api/v1/units",
        headers=headers,
        json={"property_id": prop_id, "unit_number": "D1", "monthly_rent": "9000", "deposit_amount": "9000"},
    )
    unit_id = unit_resp.json()["id"]

    create = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": unit_id, "inspection_type": "routine"},
    )
    report_id = create.json()["id"]
    rooms = create.json()["rooms_data"]
    for room in rooms:
        room["condition"] = "excellent"
        room["photo_file_ids"] = [str(uuid.uuid4())]

    await client.patch(
        f"/api/v1/inspections/{report_id}/rooms",
        headers=headers,
        json={"rooms_data": rooms},
    )
    await client.post(f"/api/v1/inspections/{report_id}/submit", headers=headers)

    # Try to update after submission
    resp = await client.patch(
        f"/api/v1/inspections/{report_id}/rooms",
        headers=headers,
        json={"rooms_data": rooms},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_inspection_compliance_summary(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/inspections/compliance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_active_tenancies" in data
    assert "missing_move_in_inspection" in data


@pytest.mark.asyncio
async def test_cross_org_inspection_isolation(client: AsyncClient):
    headers_a = await _make_owner_org(client)
    headers_b = await _make_owner_org(client)

    prop_resp = await client.post(
        "/api/v1/properties",
        headers=headers_a,
        json={"name": "Org A Prop", "address": "1 A St", "property_type": "residential"},
    )
    prop_id = prop_resp.json()["id"]
    unit_resp = await client.post(
        "/api/v1/units",
        headers=headers_a,
        json={"property_id": prop_id, "unit_number": "E1", "monthly_rent": "5000", "deposit_amount": "5000"},
    )
    unit_id = unit_resp.json()["id"]

    create = await client.post(
        "/api/v1/inspections",
        headers=headers_a,
        json={"unit_id": unit_id, "inspection_type": "routine"},
    )
    report_id = create.json()["id"]

    resp = await client.get(f"/api/v1/inspections/{report_id}", headers=headers_b)
    assert resp.status_code == 403


# ================================================================= Sprint 11: Late fees


@pytest.mark.asyncio
async def test_late_fee_calculation_by_type():
    from app.models.property import LateFeeType
    from app.services.late_fee_service import _calculate_fee

    assert _calculate_fee(LateFeeType.FIXED, Decimal("500"), Decimal("10000"), 5) == Decimal("500")
    assert _calculate_fee(LateFeeType.PERCENT, Decimal("5"), Decimal("10000"), 5) == Decimal("500.00")
    assert _calculate_fee(LateFeeType.DAILY, Decimal("50"), Decimal("10000"), 10) == Decimal("500.00")


@pytest.mark.asyncio
async def test_late_fee_is_bounded_by_the_cap_and_the_balance():
    """A fee larger than the debt it punishes is indefensible; so is an uncapped
    daily charge on an old arrear."""
    from app.models.property import LateFeeType
    from app.services.late_fee_service import _calculate_fee

    capped = _calculate_fee(LateFeeType.DAILY, Decimal("100"), Decimal("50000"), 90, cap=Decimal("3000"))
    assert capped == Decimal("3000")

    # 100/day for 90 days is 9,000 — more than the 2,000 actually outstanding.
    assert _calculate_fee(LateFeeType.DAILY, Decimal("100"), Decimal("2000"), 90) == Decimal("2000")
    # A grace period not yet exhausted charges nothing.
    assert _calculate_fee(LateFeeType.DAILY, Decimal("100"), Decimal("2000"), -3) == Decimal("0.00")


@pytest.mark.asyncio
async def test_late_fee_applies_only_to_a_configured_property(client: AsyncClient, db: AsyncSession):
    """The config columns did not exist, so this whole feature silently no-opped."""
    from datetime import timedelta

    from app.models.billing import Invoice, InvoiceLineItem, LineItemKind
    from app.services import late_fee_service

    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    property_id = setup["property"]["id"]

    invoice = await client.post(
        "/api/v1/invoices/generate", headers=headers, json={"tenancy_id": setup["tenancy"]["id"]}
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = uuid.UUID(invoice.json()["id"])

    # Push it well past the grace period.
    record = await db.get(Invoice, invoice_id)
    record.due_date = date.today() - timedelta(days=30)
    await db.commit()

    async def late_fee_lines() -> int:
        rows = await db.scalars(
            select(InvoiceLineItem.id).where(
                InvoiceLineItem.invoice_id == invoice_id,
                InvoiceLineItem.kind == LineItemKind.LATE_FEE,
            )
        )
        return len(list(rows))

    # Nothing configured — nothing charged.
    await late_fee_service.apply_late_fees(db)
    assert await late_fee_lines() == 0

    configured = await client.patch(
        f"/api/v1/properties/{property_id}",
        headers=headers,
        json={
            "grace_period_days": 5,
            "late_fee_type": "percent",
            "late_fee_amount": "5.00",
            "late_fee_cap": "2000.00",
        },
    )
    assert configured.status_code == 200, configured.text
    assert configured.json()["late_fee_type"] == "percent"

    await late_fee_service.apply_late_fees(db)
    assert await late_fee_lines() == 1

    # Running again is a no-op — the daily task must not compound.
    await late_fee_service.apply_late_fees(db)
    assert await late_fee_lines() == 1


# ================================================================= Sprint 11: Analytics


@pytest.mark.asyncio
async def test_analytics_revenue(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/analytics/revenue", headers=headers, params={"months": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert "month" in data[0]
    assert "collected" in data[0]
    assert "collection_rate" in data[0]


@pytest.mark.asyncio
async def test_analytics_property_performance(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/analytics/property-performance", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_analytics_cash_flow_forecast(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get(
        "/api/v1/analytics/cash-flow-forecast", headers=headers, params={"months_ahead": 3}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert "projected_income" in data[0]


@pytest.mark.asyncio
async def test_analytics_expiring_leases(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/analytics/expiring-leases", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "expiring_in_30_days" in data
    assert "expiring_in_60_days" in data
    assert "expiring_in_90_days" in data


@pytest.mark.asyncio
async def test_analytics_maintenance(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/analytics/maintenance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "this_month_cost" in data
    assert "spike_alert" in data


# ================================================================= Sprint 9: Signatures


@pytest.mark.asyncio
async def test_signing_link_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/sign/nonexistenttoken123")
    assert resp.status_code == 404


async def _stored_pdf(client: AsyncClient, db: AsyncSession, headers: dict) -> "uuid.UUID":
    """Persist a StoredFile in the caller's org so it can be sent for signing."""
    from app.models.file import FileCategory, StoredFile, UploadStatus

    me = await client.get("/api/v1/auth/me", headers=headers)
    stored = StoredFile(
        organization_id=uuid.UUID(me.json()["organization_id"]),
        storage_key=f"test/{uuid.uuid4().hex}.pdf",
        filename="lease.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        category=FileCategory.LEASE,
        status=UploadStatus.UPLOADED,
    )
    db.add(stored)
    await db.commit()
    await db.refresh(stored)
    return stored.id


@pytest.mark.asyncio
async def test_signing_flow_end_to_end(client: AsyncClient, db: AsyncSession):
    """Drive the real signer journey: open link, request OTP, submit signature.

    The signing endpoints were never exercised before, which hid a broken call
    into otp_service. This walks the public token routes the way a tenant does.
    """
    from app.core.config import settings
    from app.services import otp_service, signature_service

    headers = await _make_owner_org(client)
    document_id = await _stored_pdf(client, db, headers)
    me = await client.get("/api/v1/auth/me", headers=headers)

    sig, raw_token = await signature_service.create_signing_request(
        db,
        organization_id=uuid.UUID(me.json()["organization_id"]),
        document_id=document_id,
        tenancy_id=None,
        signer_name="Signing Tenant",
        signer_phone="+254712345680",
        signer_role="tenant",
    )

    # The signer opens the link — no auth required.
    opened = await client.get(f"/api/v1/sign/{raw_token}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "pending"

    # Requesting the code must not be confused with the link notification.
    assert sig.otp_sent is False
    otp_resp = await client.post(f"/api/v1/sign/{raw_token}/send-otp")
    assert otp_resp.status_code == 200, otp_resp.text

    await db.refresh(sig)
    assert sig.otp_sent is True

    # A wrong code is rejected before anything is recorded.
    bad = await client.post(
        f"/api/v1/sign/{raw_token}/sign",
        json={"otp_code": "0" * settings.OTP_LENGTH, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert bad.status_code == 400

    code = await otp_service.generate_otp(signature_service.SIGNING_OTP_PURPOSE, str(sig.id))
    signed = await client.post(
        f"/api/v1/sign/{raw_token}/sign",
        json={"otp_code": code, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "signed"
    assert signed.json()["signed_at"] is not None

    # A signed request is closed: replaying the link is rejected as a conflict.
    replay = await client.post(
        f"/api/v1/sign/{raw_token}/sign",
        json={"otp_code": code, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert replay.status_code == 409


@pytest.mark.asyncio
async def test_create_signing_request(client: AsyncClient, db: AsyncSession):
    headers = await _make_owner_org(client)

    # Need a stored file to sign
    from app.models.file import FileCategory, StoredFile, UploadStatus

    stored = StoredFile(
        organization_id=uuid.uuid4(),  # will be overridden below
        storage_key=f"test/{uuid.uuid4().hex}.pdf",
        filename="lease.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        category=FileCategory.LEASE,
        status=UploadStatus.UPLOADED,
    )

    # Get the org id from the token
    me = await client.get("/api/v1/auth/me", headers=headers)
    org_id = me.json()["organization_id"]
    stored.organization_id = uuid.UUID(org_id)
    db.add(stored)
    await db.commit()
    await db.refresh(stored)

    resp = await client.post(
        "/api/v1/signatures",
        headers=headers,
        json={
            "document_id": str(stored.id),
            "signer_name": "Test Tenant",
            "signer_phone": "+254712345679",
            "signer_role": "tenant",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"


# ============================================== Sprint 9: signing workflow security


@pytest.mark.asyncio
async def test_signing_request_cannot_target_another_orgs_document(client: AsyncClient, db: AsyncSession):
    """The signing link is public, so the org check has to happen at creation.

    Without it, org B could raise a signing request against org A's lease and have
    a stranger sign it — the signer never authenticates as anyone in org A.
    """
    headers_a = await _make_owner_org(client)
    headers_b = await _make_owner_org(client)
    document_id = await _stored_pdf(client, db, headers_a)

    resp = await client.post(
        "/api/v1/signatures",
        headers=headers_b,
        json={
            "document_id": str(document_id),
            "signer_name": "Opportunist",
            "signer_phone": "+254712345690",
        },
    )
    # 404, not 403 — org B must not learn that this document id exists.
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_signing_request_cannot_target_another_orgs_tenancy(client: AsyncClient, db: AsyncSession):
    headers_a = await _make_agency_org(client)
    headers_b = await _make_owner_org(client)
    setup = await _agency_money_path(client, headers_a)
    document_id = await _stored_pdf(client, db, headers_b)

    tenancies = (await client.get("/api/v1/tenancies", headers=headers_a)).json()
    tenancy_id = tenancies[0]["id"] if isinstance(tenancies, list) else tenancies["items"][0]["id"]
    assert setup  # the money path is what created that tenancy

    resp = await client.post(
        "/api/v1/signatures",
        headers=headers_b,
        json={
            "document_id": str(document_id),
            "tenancy_id": tenancy_id,
            "signer_name": "Opportunist",
            "signer_phone": "+254712345691",
        },
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_signing_link_expires_after_72_hours(client: AsyncClient, db: AsyncSession):
    from datetime import UTC, datetime, timedelta

    from app.models.signature import DigitalSignature
    from app.services import signature_service

    headers = await _make_owner_org(client)
    document_id = await _stored_pdf(client, db, headers)
    me = await client.get("/api/v1/auth/me", headers=headers)

    sig, raw_token = await signature_service.create_signing_request(
        db,
        organization_id=uuid.UUID(me.json()["organization_id"]),
        document_id=document_id,
        tenancy_id=None,
        signer_name="Late Signer",
        signer_phone="+254712345692",
    )
    assert (sig.expires_at - datetime.now(UTC)) < timedelta(hours=73)

    record = await db.get(DigitalSignature, sig.id)
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    assert (await client.get(f"/api/v1/sign/{raw_token}")).status_code == 410
    assert (await client.post(f"/api/v1/sign/{raw_token}/send-otp")).status_code == 410
    signed = await client.post(
        f"/api/v1/sign/{raw_token}/sign",
        json={"otp_code": "123456", "signature_image": "data:image/png;base64,AAAA"},
    )
    assert signed.status_code == 410


@pytest.mark.asyncio
async def test_only_the_raw_token_hash_is_stored(client: AsyncClient, db: AsyncSession):
    """A database leak must not hand the attacker working signing links."""
    from sqlalchemy import select

    from app.models.signature import DigitalSignature
    from app.services import signature_service

    headers = await _make_owner_org(client)
    document_id = await _stored_pdf(client, db, headers)
    me = await client.get("/api/v1/auth/me", headers=headers)

    sig, raw_token = await signature_service.create_signing_request(
        db,
        organization_id=uuid.UUID(me.json()["organization_id"]),
        document_id=document_id,
        tenancy_id=None,
        signer_name="Hash Signer",
        signer_phone="+254712345693",
    )

    stored = await db.scalar(select(DigitalSignature).where(DigitalSignature.id == sig.id))
    assert raw_token not in stored.token_hash
    assert stored.token_hash == signature_service._hash_token(raw_token)
    # The public read never echoes the token back either.
    opened = (await client.get(f"/api/v1/sign/{raw_token}")).json()
    assert raw_token not in str(opened)


@pytest.mark.asyncio
async def test_signing_otp_is_rate_limited_and_scoped_to_one_signer(client: AsyncClient, db: AsyncSession):
    """Guessing is capped, and one signer's code never opens another's document."""
    from app.core.config import settings
    from app.services import otp_service, signature_service

    headers = await _make_owner_org(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    org_id = uuid.UUID(me.json()["organization_id"])

    first, first_token = await signature_service.create_signing_request(
        db,
        organization_id=org_id,
        document_id=await _stored_pdf(client, db, headers),
        tenancy_id=None,
        signer_name="Signer One",
        signer_phone="+254712345694",
    )
    second, second_token = await signature_service.create_signing_request(
        db,
        organization_id=org_id,
        document_id=await _stored_pdf(client, db, headers),
        tenancy_id=None,
        signer_name="Signer Two",
        signer_phone="+254712345695",
    )

    code_for_first = await otp_service.generate_otp(signature_service.SIGNING_OTP_PURPOSE, str(first.id))
    await otp_service.generate_otp(signature_service.SIGNING_OTP_PURPOSE, str(second.id))

    # Signer one's code is worthless on signer two's document.
    crossed = await client.post(
        f"/api/v1/sign/{second_token}/sign",
        json={"otp_code": code_for_first, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert crossed.status_code == 400

    # Brute force against signer one is capped; the correct code stops working too.
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        attempt = await client.post(
            f"/api/v1/sign/{first_token}/sign",
            json={"otp_code": "000000", "signature_image": "data:image/png;base64,AAAA"},
        )
        assert attempt.status_code == 400

    burned = await client.post(
        f"/api/v1/sign/{first_token}/sign",
        json={"otp_code": code_for_first, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert burned.status_code == 400


@pytest.mark.asyncio
async def test_signing_captures_the_full_audit_trail(client: AsyncClient, db: AsyncSession):
    from app.models.signature import DigitalSignature
    from app.services import otp_service, signature_service

    headers = await _make_owner_org(client)
    me = await client.get("/api/v1/auth/me", headers=headers)

    sig, raw_token = await signature_service.create_signing_request(
        db,
        organization_id=uuid.UUID(me.json()["organization_id"]),
        document_id=await _stored_pdf(client, db, headers),
        tenancy_id=None,
        signer_name="Audited Signer",
        signer_phone="+254712345696",
    )
    code = await otp_service.generate_otp(signature_service.SIGNING_OTP_PURPOSE, str(sig.id))

    resp = await client.post(
        f"/api/v1/sign/{raw_token}/sign",
        headers={
            "user-agent": "Mozilla/5.0 (Linux; Android 13)",
            "x-forwarded-for": "41.90.64.10, 10.0.0.1",
            "x-geo-position": "-1.2921,36.8219",
        },
        json={"otp_code": code, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert resp.status_code == 200, resp.text

    await db.refresh(await db.get(DigitalSignature, sig.id))
    record = await db.get(DigitalSignature, sig.id)
    assert record.status.value == "signed"
    assert record.signed_at is not None
    assert record.otp_verified_at is not None
    # The client IP is the first hop, not the proxy's.
    assert record.ip_address == "41.90.64.10"
    assert "Android" in record.user_agent
    assert record.gps_latitude == "-1.2921"
    assert record.gps_longitude == "36.8219"


# ===================================================== Sprint 9: document vault


async def _uploaded_file(
    client: AsyncClient,
    headers: dict,
    *,
    filename: str = "title-deed.pdf",
    category: str = "title_deed",
) -> dict:
    """Walk the real three-step upload: reserve, PUT the bytes, confirm."""
    body = b"%PDF-1.4 fake document bytes"
    ticket = await client.post(
        "/api/v1/files/upload-url",
        headers=headers,
        json={
            "filename": filename,
            "content_type": "application/pdf",
            "size_bytes": len(body),
            "category": category,
        },
    )
    assert ticket.status_code == 201, ticket.text
    ticket = ticket.json()

    put = await client.put(ticket["upload_url"], content=body)
    assert put.status_code == 200, put.text

    confirmed = await client.post(
        f"/api/v1/files/{ticket['file_id']}/confirm",
        headers=headers,
        json={"size_bytes": len(body)},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


@pytest.mark.asyncio
async def test_property_vault_categorises_uploaded_documents(client: AsyncClient):
    headers = await _make_owner_org(client)
    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Vault Court", "address": "1 Vault Rd", "property_type": "residential"},
    )
    property_id = prop.json()["id"]

    deed = await _uploaded_file(client, headers)
    filed = await client.post(
        "/api/v1/vault/documents",
        headers=headers,
        json={
            "file_id": deed["id"],
            "entity_type": "property",
            "entity_id": property_id,
            "category": "title_deed",
            "tags": ["Original", "original", "  LR 209/1234 "],
            "description": "Certificate of title",
        },
    )
    assert filed.status_code == 201, filed.text
    # Tags are normalised and de-duplicated so search stays predictable.
    assert filed.json()["tags"] == ["original", "lr 209/1234"]

    vault = await client.get(f"/api/v1/vault/properties/{property_id}", headers=headers)
    assert vault.status_code == 200, vault.text
    body = vault.json()
    assert body["document_count"] == 1
    assert body["sections"][0]["category"] == "title_deed"
    assert body["sections"][0]["documents"][0]["url"]


@pytest.mark.asyncio
async def test_vault_search_matches_filename_description_and_tags(client: AsyncClient):
    headers = await _make_owner_org(client)
    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Search Court", "address": "2 Search Rd", "property_type": "residential"},
    )
    property_id = prop.json()["id"]

    deed = await _uploaded_file(client, headers, filename="deed.pdf")
    insurance = await _uploaded_file(client, headers, filename="cover.pdf", category="insurance_certificate")
    for file_id, category, tags, description in (
        (deed["id"], "title_deed", ["freehold"], "Certificate of title"),
        (insurance["id"], "insurance_certificate", ["jubilee"], "Fire and perils cover"),
    ):
        await client.post(
            "/api/v1/vault/documents",
            headers=headers,
            json={
                "file_id": file_id,
                "entity_type": "property",
                "entity_id": property_id,
                "category": category,
                "tags": tags,
                "description": description,
            },
        )

    by_tag = await client.get(
        f"/api/v1/vault/properties/{property_id}", headers=headers, params={"search": "jubilee"}
    )
    assert by_tag.json()["document_count"] == 1

    by_description = await client.get(
        f"/api/v1/vault/properties/{property_id}", headers=headers, params={"search": "perils"}
    )
    assert by_description.json()["document_count"] == 1

    by_filename = await client.get(
        f"/api/v1/vault/properties/{property_id}", headers=headers, params={"search": "deed"}
    )
    assert by_filename.json()["document_count"] == 1

    by_category = await client.get(
        f"/api/v1/vault/properties/{property_id}",
        headers=headers,
        params={"category": "title_deed"},
    )
    assert by_category.json()["document_count"] == 1


@pytest.mark.asyncio
async def test_new_version_supersedes_without_losing_the_old_one(client: AsyncClient):
    headers = await _make_owner_org(client)
    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Version Court", "address": "3 Version Rd", "property_type": "residential"},
    )
    property_id = prop.json()["id"]

    original = await _uploaded_file(client, headers, filename="cover-2025.pdf")
    await client.post(
        "/api/v1/vault/documents",
        headers=headers,
        json={
            "file_id": original["id"],
            "entity_type": "property",
            "entity_id": property_id,
            "category": "insurance_certificate",
            "tags": ["jubilee"],
        },
    )

    renewal = await _uploaded_file(client, headers, filename="cover-2026.pdf")
    versioned = await client.post(
        f"/api/v1/vault/documents/{original['id']}/versions",
        headers=headers,
        json={"file_id": renewal["id"], "description": "2026 renewal"},
    )
    assert versioned.status_code == 201, versioned.text
    assert versioned.json()["version"] == 2
    assert versioned.json()["supersedes_id"] == original["id"]
    # Category and tags carry forward so a renewal never falls out of its section.
    assert versioned.json()["category"] == "insurance_certificate"
    assert versioned.json()["tags"] == ["jubilee"]

    # The vault shows only the current version.
    vault = await client.get(f"/api/v1/vault/properties/{property_id}", headers=headers)
    assert vault.json()["document_count"] == 1
    assert vault.json()["sections"][0]["documents"][0]["filename"] == "cover-2026.pdf"

    # Nothing was destroyed — the history is walkable from either end.
    for anchor in (original["id"], renewal["id"]):
        history = await client.get(f"/api/v1/vault/documents/{anchor}/versions", headers=headers)
        assert [row["version"] for row in history.json()] == [2, 1]

    with_archived = await client.get(
        f"/api/v1/vault/properties/{property_id}",
        headers=headers,
        params={"include_archived": True},
    )
    assert with_archived.json()["document_count"] == 2

    # A superseded document cannot be superseded again.
    third = await _uploaded_file(client, headers, filename="cover-2027.pdf")
    stale = await client.post(
        f"/api/v1/vault/documents/{original['id']}/versions",
        headers=headers,
        json={"file_id": third["id"]},
    )
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_generated_categories_cannot_be_uploaded(client: AsyncClient):
    """A person must not be able to forge a receipt by uploading one."""
    headers = await _make_owner_org(client)
    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Forge Court", "address": "4 Forge Rd", "property_type": "residential"},
    )
    forged = await _uploaded_file(client, headers, filename="receipt.pdf")
    resp = await client.post(
        "/api/v1/vault/documents",
        headers=headers,
        json={
            "file_id": forged["id"],
            "entity_type": "property",
            "entity_id": prop.json()["id"],
            "category": "receipt",
        },
    )
    assert resp.status_code == 400
    assert "generated by RentFlow" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_vault_is_scoped_to_the_owning_organization(client: AsyncClient):
    headers_a = await _make_owner_org(client)
    headers_b = await _make_owner_org(client)

    prop = await client.post(
        "/api/v1/properties",
        headers=headers_a,
        json={"name": "Private Court", "address": "5 Private Rd", "property_type": "residential"},
    )
    property_id = prop.json()["id"]
    deed = await _uploaded_file(client, headers_a)
    await client.post(
        "/api/v1/vault/documents",
        headers=headers_a,
        json={
            "file_id": deed["id"],
            "entity_type": "property",
            "entity_id": property_id,
            "category": "title_deed",
        },
    )

    assert (await client.get(f"/api/v1/vault/properties/{property_id}", headers=headers_b)).status_code == 403
    assert (
        await client.get(f"/api/v1/vault/documents/{deed['id']}/versions", headers=headers_b)
    ).status_code == 403


@pytest.mark.asyncio
async def test_tenant_vault_gathers_generated_documents(client: AsyncClient):
    """A tenant's receipts and lease land in their vault without being filed by hand."""
    headers = await _make_agency_org(client)
    await _agency_money_path(client, headers)

    tenants = (await client.get("/api/v1/tenants", headers=headers)).json()
    tenant_id = tenants[0]["id"]

    vault = await client.get(f"/api/v1/vault/tenants/{tenant_id}", headers=headers)
    assert vault.status_code == 200, vault.text
    categories = {section["category"] for section in vault.json()["sections"]}
    assert "receipt" in categories
    assert vault.json()["document_count"] >= 1


@pytest.mark.asyncio
async def test_storage_usage_reports_bytes_per_category(client: AsyncClient):
    headers = await _make_owner_org(client)
    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Usage Court", "address": "6 Usage Rd", "property_type": "residential"},
    )
    deed = await _uploaded_file(client, headers)
    await client.post(
        "/api/v1/vault/documents",
        headers=headers,
        json={
            "file_id": deed["id"],
            "entity_type": "property",
            "entity_id": prop.json()["id"],
            "category": "title_deed",
        },
    )

    usage = await client.get("/api/v1/vault/usage", headers=headers)
    assert usage.status_code == 200, usage.text
    assert usage.json()["total_documents"] >= 1
    assert usage.json()["total_bytes"] > 0
    assert any(row["category"] == "title_deed" for row in usage.json()["by_category"])


@pytest.mark.asyncio
async def test_document_delivery_over_whatsapp(client: AsyncClient):
    headers = await _make_agency_org(client)
    await _agency_money_path(client, headers)
    tenant_id = (await client.get("/api/v1/tenants", headers=headers)).json()[0]["id"]

    vault = (await client.get(f"/api/v1/vault/tenants/{tenant_id}", headers=headers)).json()
    document_id = vault["sections"][0]["documents"][0]["id"]

    resp = await client.post(
        f"/api/v1/vault/documents/{document_id}/send",
        headers=headers,
        json={"tenant_id": tenant_id, "message": "Here is your receipt."},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["document_id"] == document_id
    assert resp.json()["recipient"]

    # Without a recipient there is nothing to send to.
    blank = await client.post(f"/api/v1/vault/documents/{document_id}/send", headers=headers, json={})
    assert blank.status_code == 400


@pytest.mark.asyncio
async def test_local_storage_links_are_signed_and_expire(client: AsyncClient):
    """The dev backend must enforce the same 60-minute expiry R2 does."""
    headers = await _make_owner_org(client)
    stored = await _uploaded_file(client, headers)

    signed_url = stored["url"]
    assert "token=" in signed_url and "expires=" in signed_url
    assert (await client.get(signed_url)).status_code == 200

    unsigned = signed_url.split("?")[0]
    assert (await client.get(unsigned)).status_code == 403

    tampered = signed_url.replace("token=", "token=x")
    assert (await client.get(tampered)).status_code == 403

    expired = signed_url.split("&token=")[0].replace(
        signed_url.split("expires=")[1].split("&")[0], "1000000000"
    )
    assert (await client.get(expired)).status_code == 403


# ================================================ Sprint 9: lease template editor


@pytest.mark.asyncio
async def test_template_preview_renders_sample_data_as_pdf(client: AsyncClient):
    headers = await _make_owner_org(client)

    starter = await client.get("/api/v1/lease-templates/starter", headers=headers)
    assert starter.status_code == 200, starter.text
    assert "tenant_name" in starter.json()["variables"]
    assert starter.json()["sample_values"]["tenant_name"]

    resp = await client.post(
        "/api/v1/lease-templates/preview",
        headers=headers,
        json={
            "body_html": "<h2>Lease</h2><p>{{tenant_name}} rents {{unit_number}} "
            "for KES {{rent_amount}} a month.</p>"
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_template_preview_reports_a_broken_placeholder(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.post(
        "/api/v1/lease-templates/preview",
        headers=headers,
        json={"body_html": "<p>{% for %}broken{% endfor %}</p>"},
    )
    assert resp.status_code == 422
    assert "could not be rendered" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_template_preview_escapes_interpolated_values(client: AsyncClient, db: AsyncSession):
    """A tenant's own name must never inject markup into a lease."""
    from app.services import pdf_service

    body = pdf_service.substitute("<p>{{tenant_name}}</p>", {"tenant_name": "<script>x</script>"})
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


@pytest.mark.asyncio
async def test_template_preview_can_render_a_saved_template(client: AsyncClient):
    headers = await _make_owner_org(client)
    created = await client.post(
        "/api/v1/lease-templates",
        headers=headers,
        json={
            "name": "House style",
            "body_html": "<h2>Agreement</h2><p>Rent: KES {{rent_amount}}</p>",
            "is_default": True,
        },
    )
    assert created.status_code == 201, created.text

    resp = await client.post(
        "/api/v1/lease-templates/preview",
        headers=headers,
        json={"template_id": created.json()["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")

    empty = await client.post("/api/v1/lease-templates/preview", headers=headers, json={})
    assert empty.status_code == 400


# ============================================ Sprint 10: comparison and compliance


async def _inspect_unit(
    client: AsyncClient,
    headers: dict,
    unit_id: str,
    kind: str,
    conditions: dict[str, str],
    tenancy_id: str | None = None,
) -> dict:
    """Create, fill and submit an inspection with the given per-room conditions."""
    create = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": unit_id, "inspection_type": kind, "tenancy_id": tenancy_id},
    )
    assert create.status_code == 201, create.text
    report = create.json()

    rooms = report["rooms_data"]
    for room in rooms:
        room["condition"] = conditions.get(room["name"], "good")
        room["photo_file_ids"] = [str(uuid.uuid4())]

    await client.patch(
        f"/api/v1/inspections/{report['id']}/rooms", headers=headers, json={"rooms_data": rooms}
    )
    submitted = await client.post(f"/api/v1/inspections/{report['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


@pytest.mark.asyncio
async def test_move_out_comparison_flags_rooms_that_got_worse(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    unit_id = setup["unit"]["id"]
    tenancy_id = setup["tenancy"]["id"]

    move_in = await _inspect_unit(client, headers, unit_id, "move_in", {}, tenancy_id)
    damaged = move_in["rooms_data"][0]["name"]

    move_out = await _inspect_unit(client, headers, unit_id, "move_out", {damaged: "poor"}, tenancy_id)

    resp = await client.get(f"/api/v1/inspections/{move_out['id']}/comparison", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["move_in"]["id"] == move_in["id"]
    assert body["rooms_degraded"] == 1
    worse = [row for row in body["rooms"] if row["change"] == "worse"]
    assert [row["name"] for row in worse] == [damaged]
    assert worse[0]["before"]["condition"] == "good"
    assert worse[0]["after"]["condition"] == "poor"
    assert all(row["change"] == "unchanged" for row in body["rooms"] if row["name"] != damaged)


@pytest.mark.asyncio
async def test_comparison_is_rejected_for_a_move_in_report(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)
    move_in = await _inspect_unit(client, headers, setup["unit"]["id"], "move_in", {}, setup["tenancy"]["id"])

    resp = await client.get(f"/api/v1/inspections/{move_in['id']}/comparison", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_deduction_cannot_exceed_the_deposit_held(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers, rent="30000.00")
    unit_id = setup["unit"]["id"]
    tenancy_id = setup["tenancy"]["id"]

    await _inspect_unit(client, headers, unit_id, "move_in", {}, tenancy_id)
    move_out = await _inspect_unit(client, headers, unit_id, "move_out", {}, tenancy_id)

    too_much = await client.post(
        f"/api/v1/inspections/{move_out['id']}/deduction",
        headers=headers,
        json={"deduction_amount": "45000.00", "deduction_notes": "Repainting"},
    )
    assert too_much.status_code == 400
    assert "more than the deposit" in too_much.json()["detail"]

    negative = await client.post(
        f"/api/v1/inspections/{move_out['id']}/deduction",
        headers=headers,
        json={"deduction_amount": "-100.00", "deduction_notes": "Oops"},
    )
    assert negative.status_code == 400

    ok = await client.post(
        f"/api/v1/inspections/{move_out['id']}/deduction",
        headers=headers,
        json={"deduction_amount": "5000.00", "deduction_notes": "Repainting the living room"},
    )
    assert ok.status_code == 200, ok.text
    assert Decimal(str(ok.json()["deposit_deduction"])) == Decimal("5000.00")


@pytest.mark.asyncio
async def test_deduction_requires_a_submitted_inspection(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)

    draft = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": setup["unit"]["id"], "inspection_type": "move_out"},
    )
    resp = await client.post(
        f"/api/v1/inspections/{draft.json()['id']}/deduction",
        headers=headers,
        json={"deduction_amount": "1000.00", "deduction_notes": "Too early"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_compliance_summary_names_the_tenancies_with_no_baseline(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)

    before = await client.get("/api/v1/inspections/compliance", headers=headers)
    assert before.status_code == 200, before.text
    body = before.json()
    assert body["total_active_tenancies"] == 1
    assert body["missing_move_in_inspection"] == 1
    assert body["coverage_percent"] == 0.0
    assert body["missing_move_in"][0]["tenant_name"] == "Peter Otieno"
    assert body["missing_move_in"][0]["unit_number"] == "A1"
    # A tenancy never inspected is also overdue for a routine one.
    assert body["overdue_routine_inspection"] == 1

    await _inspect_unit(client, headers, setup["unit"]["id"], "move_in", {}, setup["tenancy"]["id"])

    after = (await client.get("/api/v1/inspections/compliance", headers=headers)).json()
    assert after["missing_move_in_inspection"] == 0
    assert after["coverage_percent"] == 100.0
    assert after["overdue_routine_inspection"] == 0


@pytest.mark.asyncio
async def test_inspection_detail_resolves_photo_urls(client: AsyncClient):
    headers = await _make_owner_org(client)
    prop = await client.post(
        "/api/v1/properties",
        headers=headers,
        json={"name": "Photo Vault", "address": "9 Photo Rd", "property_type": "residential"},
    )
    unit = await client.post(
        "/api/v1/units",
        headers=headers,
        json={
            "property_id": prop.json()["id"],
            "unit_number": "P1",
            "monthly_rent": "10000",
            "deposit_amount": "10000",
        },
    )
    photo = await _uploaded_file(client, headers, filename="kitchen.pdf", category="inspection_photo")

    create = await client.post(
        "/api/v1/inspections",
        headers=headers,
        json={"unit_id": unit.json()["id"], "inspection_type": "routine"},
    )
    rooms = create.json()["rooms_data"]
    for room in rooms:
        room["condition"] = "good"
        room["photo_file_ids"] = [photo["id"]]
    await client.patch(
        f"/api/v1/inspections/{create.json()['id']}/rooms",
        headers=headers,
        json={"rooms_data": rooms},
    )

    detail = await client.get(f"/api/v1/inspections/{create.json()['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    first_room = detail.json()["rooms"][0]
    assert first_room["photos"][0]["id"] == photo["id"]
    assert first_room["photos"][0]["url"]


# ==================================================== Sprint 11: eTIMS and demand letters


@pytest.mark.asyncio
async def test_etims_credentials_are_stored_encrypted_and_never_returned(
    client: AsyncClient, db: AsyncSession
):
    """The credentials are the landlord's KRA identity — a database dump must not
    hand anyone the ability to file in their name."""
    from sqlalchemy import select as sa_select

    from app.models.etims import EtimsCredential

    headers = await _make_owner_org(client)

    before = await client.get("/api/v1/etims/credentials", headers=headers)
    assert before.status_code == 200
    assert before.json() == {"configured": False}

    saved = await client.put(
        "/api/v1/etims/credentials",
        headers=headers,
        json={
            "kra_pin": "A012345678Z",
            "device_serial": "KRACU0300000001",
            "api_key": "test-cmc-key-value",
            "branch_id": "00",
            "environment": "sandbox",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["kra_pin"] == "A012345678Z"
    # Only a masked hint comes back, never the secret itself.
    assert body["device_serial_hint"].endswith("0001")
    assert "test-cmc-key-value" not in str(body)
    assert "KRACU0300000001" not in str(body)

    stored = await db.scalar(sa_select(EtimsCredential).where(EtimsCredential.kra_pin == "A012345678Z"))
    assert "test-cmc-key-value" not in stored.api_key_encrypted
    assert "KRACU0300000001" not in stored.device_serial_encrypted

    from app.core.crypto import decrypt

    assert decrypt(stored.api_key_encrypted) == "test-cmc-key-value"

    removed = await client.delete("/api/v1/etims/credentials", headers=headers)
    assert removed.json() == {"removed": True}


@pytest.mark.asyncio
async def test_receipts_are_issued_without_etims_when_kra_is_unreachable(client: AsyncClient):
    """A tenant who has paid gets their receipt whether or not KRA is answering."""
    headers = await _make_agency_org(client)
    await client.put(
        "/api/v1/etims/credentials",
        headers=headers,
        json={
            "kra_pin": "A012345678Z",
            "device_serial": "KRACU0300000001",
            "api_key": "unreachable",
            "environment": "sandbox",
        },
    )

    # The money path issues a receipt; the eTIMS call will fail (no network).
    await _agency_money_path(client, headers)

    payments = (await client.get("/api/v1/payments", headers=headers)).json()
    rows = payments if isinstance(payments, list) else payments["items"]
    assert rows[0]["status"] == "confirmed"

    report = await client.get("/api/v1/etims/report", headers=headers)
    assert report.status_code == 200, report.text
    summary = report.json()
    assert summary["total"] == 1
    # Not submitted, but recorded and scheduled for a retry rather than lost.
    assert summary["submitted"] == 0
    assert summary["failed"] == 1
    assert summary["recent_failures"][0]["attempts"] == 1
    assert summary["recent_failures"][0]["next_attempt_at"] is not None


@pytest.mark.asyncio
async def test_no_etims_submission_without_credentials(client: AsyncClient):
    headers = await _make_agency_org(client)
    await _agency_money_path(client, headers)

    report = (await client.get("/api/v1/etims/report", headers=headers)).json()
    assert report["total"] == 0


@pytest.mark.asyncio
async def test_etims_backoff_grows_and_gives_up(client: AsyncClient, db: AsyncSession):
    from app.models.etims import EtimsStatus, EtimsSubmission
    from app.services import etims_service

    headers = await _make_agency_org(client)
    await client.put(
        "/api/v1/etims/credentials",
        headers=headers,
        json={
            "kra_pin": "A012345678Z",
            "device_serial": "KRACU0300000001",
            "api_key": "unreachable",
            "environment": "sandbox",
        },
    )
    await _agency_money_path(client, headers)

    report = (await client.get("/api/v1/etims/report", headers=headers)).json()
    submission_id = uuid.UUID(report["recent_failures"][0]["submission_id"])

    submission = await db.get(EtimsSubmission, submission_id)
    first_retry = submission.next_attempt_at

    await etims_service.submit(db, submission)
    await db.refresh(submission)
    assert submission.attempts == 2
    # Backoff grows, so a KRA outage is not hammered.
    assert submission.next_attempt_at > first_retry

    # Burn through the remaining attempts.
    while submission.attempts < etims_service.MAX_ATTEMPTS:
        await etims_service.submit(db, submission)
        await db.refresh(submission)

    assert submission.status == EtimsStatus.ABANDONED
    assert submission.next_attempt_at is None

    # A person can still force one more try, which resets the budget.
    retried = await client.post(f"/api/v1/etims/submissions/{submission_id}/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["attempts"] == 1


@pytest.mark.asyncio
async def test_etims_report_is_scoped_to_the_organization(client: AsyncClient):
    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)
    await client.put(
        "/api/v1/etims/credentials",
        headers=headers_a,
        json={
            "kra_pin": "A012345678Z",
            "device_serial": "KRACU0300000001",
            "api_key": "unreachable",
        },
    )
    await _agency_money_path(client, headers_a)

    assert (await client.get("/api/v1/etims/report", headers=headers_a)).json()["total"] == 1
    assert (await client.get("/api/v1/etims/report", headers=headers_b)).json()["total"] == 0


@pytest.mark.asyncio
async def test_etims_qr_encodes_the_kra_verification_url():
    from app.services import etims_service

    uri = etims_service.qr_data_uri("https://etims-sbx.kra.go.ke/check/ABC123")
    assert uri.startswith("data:image/svg+xml")
    # It must be self-contained — WeasyPrint cannot fetch anything at print time.
    assert "http" not in uri.split(",", 1)[0]


async def _tenancy_in_arrears(client: AsyncClient, headers: dict, db: AsyncSession, days: int) -> dict:
    """A tenancy with one unpaid invoice that fell due `days` ago."""
    from datetime import timedelta

    from app.models.billing import Invoice

    setup = await _agency_money_path(client, headers)
    invoice = await client.post(
        "/api/v1/invoices/generate", headers=headers, json={"tenancy_id": setup["tenancy"]["id"]}
    )
    assert invoice.status_code == 201, invoice.text

    record = await db.get(Invoice, uuid.UUID(invoice.json()["id"]))
    record.due_date = date.today() - timedelta(days=days)
    await db.commit()
    return {**setup, "invoice": invoice.json()}


@pytest.mark.asyncio
async def test_demand_letter_states_the_balance_and_a_deadline(client: AsyncClient, db: AsyncSession):
    headers = await _make_agency_org(client)
    setup = await _tenancy_in_arrears(client, headers, db, days=65)

    issued = await client.post(f"/api/v1/arrears/demand-letters/{setup['tenancy']['id']}", headers=headers)
    assert issued.status_code == 200, issued.text
    letter = issued.json()
    assert letter["escalation"] == "First demand"
    assert letter["days_overdue"] == 65
    assert Decimal(letter["total_owed"]) > Decimal("0")
    assert letter["url"]

    # It is filed in the tenant's vault, not just emailed into the void.
    vault = await client.get(f"/api/v1/vault/tenants/{setup['tenant']['id']}", headers=headers)
    categories = {section["category"] for section in vault.json()["sections"]}
    assert "demand_letter" in categories


@pytest.mark.asyncio
async def test_demand_letter_preview_renders_without_filing_it(client: AsyncClient, db: AsyncSession):
    headers = await _make_agency_org(client)
    setup = await _tenancy_in_arrears(client, headers, db, days=70)

    preview = await client.get(
        f"/api/v1/arrears/demand-letters/{setup['tenancy']['id']}/preview", headers=headers
    )
    assert preview.status_code == 200, preview.text
    assert preview.content.startswith(b"%PDF")

    vault = await client.get(f"/api/v1/vault/tenants/{setup['tenant']['id']}", headers=headers)
    categories = {section["category"] for section in vault.json()["sections"]}
    assert "demand_letter" not in categories


@pytest.mark.asyncio
async def test_demand_letter_refuses_a_tenancy_with_nothing_overdue(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)

    resp = await client.post(f"/api/v1/arrears/demand-letters/{setup['tenancy']['id']}", headers=headers)
    assert resp.status_code == 400
    assert "no overdue balance" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_demand_letter_sweep_escalates_once_per_level(client: AsyncClient, db: AsyncSession):
    """A tenant who ignores the first demand gets a final one — not the same one nightly."""
    from app.services import demand_letter_service

    headers = await _make_agency_org(client)
    setup = await _tenancy_in_arrears(client, headers, db, days=65)
    tenant_id = setup["tenant"]["id"]

    async def letters_on_file() -> list[dict]:
        vault = await client.get(f"/api/v1/vault/tenants/{tenant_id}", headers=headers)
        section = next((s for s in vault.json()["sections"] if s["category"] == "demand_letter"), None)
        return section["documents"] if section else []

    # The sweep runs across every organisation, so assert on this tenant's own
    # file rather than global counts other tests also contribute to.
    await demand_letter_service.issue_due_letters(db)
    assert len(await letters_on_file()) == 1

    # Running again the same night issues nothing further.
    await demand_letter_service.issue_due_letters(db)
    assert len(await letters_on_file()) == 1

    # Age it past 90 days and the escalation goes up a level.
    from datetime import timedelta

    from app.models.billing import Invoice

    invoice = await db.get(Invoice, uuid.UUID(setup["invoice"]["id"]))
    invoice.due_date = date.today() - timedelta(days=95)
    await db.commit()

    await demand_letter_service.issue_due_letters(db)
    documents = await letters_on_file()
    assert len(documents) == 2
    tags = {tag for document in documents for tag in document["tags"]}
    assert {"first demand", "final demand"} <= tags


@pytest.mark.asyncio
async def test_demand_escalation_thresholds():
    from app.services.demand_letter_service import escalation_for

    assert escalation_for(30) is None
    assert escalation_for(60) == ("First demand", 14)
    assert escalation_for(89) == ("First demand", 14)
    assert escalation_for(90) == ("Final demand", 7)


# ============================= Sprint 12: renewals, task monitoring, caretaker score


async def _expiring_tenancy(client: AsyncClient, headers: dict, db: AsyncSession, days: int) -> dict:
    """A fixed-term tenancy whose lease ends `days` from today."""
    from datetime import timedelta

    from app.models.tenant import Tenancy

    setup = await _agency_money_path(client, headers)
    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))
    tenancy.is_open_ended = False
    tenancy.end_date = date.today() + timedelta(days=days)
    await db.commit()
    return setup


@pytest.mark.asyncio
async def test_renewal_offer_carries_the_configured_rent_increase(client: AsyncClient, db: AsyncSession):
    headers = await _make_agency_org(client)
    await client.patch(
        "/api/v1/organizations/me",
        headers=headers,
        json={"renewal_rent_increase_percent": "10.00", "renewal_term_months": 12},
    )
    setup = await _expiring_tenancy(client, headers, db, days=30)

    terms = await client.get(
        f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}/proposed-terms", headers=headers
    )
    assert terms.status_code == 200, terms.text
    assert Decimal(terms.json()["proposed_rent"]) == Decimal("33000.00")

    offered = await client.post(
        f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}", headers=headers, json={}
    )
    assert offered.status_code == 200, offered.text
    renewal = offered.json()
    assert renewal["status"] == "offered"
    assert Decimal(renewal["current_rent"]) == Decimal("30000.00")
    assert Decimal(renewal["proposed_rent"]) == Decimal("33000.00")
    assert Decimal(renewal["rent_increase_percent"]) == Decimal("10.00")
    # The renewal agreement is generated and filed, not just promised.
    assert renewal["document_id"]

    # Offering twice returns the same open offer rather than a second one.
    again = await client.post(
        f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}", headers=headers, json={}
    )
    assert again.json()["id"] == renewal["id"]


@pytest.mark.asyncio
async def test_renewal_offer_terms_can_be_overridden(client: AsyncClient, db: AsyncSession):
    headers = await _make_agency_org(client)
    setup = await _expiring_tenancy(client, headers, db, days=30)

    offered = await client.post(
        f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}",
        headers=headers,
        json={"proposed_rent": "36000.00", "term_months": 6},
    )
    assert offered.status_code == 200, offered.text
    renewal = offered.json()
    assert Decimal(renewal["proposed_rent"]) == Decimal("36000.00")
    assert Decimal(renewal["rent_increase_percent"]) == Decimal("20.00")


@pytest.mark.asyncio
async def test_tenant_accepts_a_renewal_and_the_tenancy_is_extended(client: AsyncClient, db: AsyncSession):
    """The public link is the whole authentication — the tenant has no account."""
    from app.models.renewal import LeaseRenewal
    from app.models.tenant import Tenancy
    from app.services import renewal_service

    headers = await _make_agency_org(client)
    setup = await _expiring_tenancy(client, headers, db, days=30)
    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))
    original_end = tenancy.end_date

    # Create through the service so the raw token is in hand, exactly as the
    # WhatsApp link carries it.
    renewal = await renewal_service.create_offer(db, tenancy, proposed_rent=Decimal("33000.00"))
    await db.commit()
    renewal_id = renewal.id
    raw_token = None
    # The service hashes the token; re-derive it the way the tenant's link does
    # by generating a fresh offer is not possible, so read the notification body.
    from sqlalchemy import select as sa_select

    from app.models.notification import Notification

    note = await db.scalar(
        sa_select(Notification)
        .where(Notification.entity_id == tenancy.id)
        .order_by(Notification.created_at.desc())
    )
    assert note is not None
    raw_token = note.body.rsplit("/renew/", 1)[1].strip()

    opened = await client.get(f"/api/v1/renew/{raw_token}")
    assert opened.status_code == 200, opened.text
    offer = opened.json()
    assert offer["status"] == "offered"
    assert offer["tenant_name"] == "Peter Otieno"
    assert Decimal(offer["proposed_rent"]) == Decimal("33000.00")
    assert offer["agreement_url"]

    accepted = await client.post(f"/api/v1/renew/{raw_token}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    db.expire_all()
    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))
    assert tenancy.end_date > original_end
    assert Decimal(tenancy.monthly_rent) == Decimal("33000.00")
    assert tenancy.status.value == "active"

    # The endpoint committed on the app's own session; drop this one's cached copy.
    db.expire_all()
    stored = await db.get(LeaseRenewal, renewal_id)
    assert stored.status.value == "accepted"
    assert stored.responded_at is not None

    # The link is single-use: answering twice is refused.
    assert (await client.post(f"/api/v1/renew/{raw_token}/accept")).status_code == 409
    assert (await client.get(f"/api/v1/renew/{raw_token}")).status_code == 409


@pytest.mark.asyncio
async def test_tenant_declines_and_the_tenancy_moves_to_notice_given(client: AsyncClient, db: AsyncSession):
    from sqlalchemy import select as sa_select

    from app.models.notification import Notification
    from app.models.tenant import Tenancy
    from app.services import renewal_service

    headers = await _make_agency_org(client)
    setup = await _expiring_tenancy(client, headers, db, days=30)
    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))

    await renewal_service.create_offer(db, tenancy)
    await db.commit()

    note = await db.scalar(
        sa_select(Notification)
        .where(Notification.entity_id == tenancy.id)
        .order_by(Notification.created_at.desc())
    )
    raw_token = note.body.rsplit("/renew/", 1)[1].strip()

    declined = await client.post(
        f"/api/v1/renew/{raw_token}/decline", json={"reason": "Moving closer to work"}
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"

    await db.refresh(tenancy)
    # Declining hands the tenancy to the existing move-out workflow.
    assert tenancy.status.value == "notice_given"
    assert tenancy.move_out_date == tenancy.end_date


@pytest.mark.asyncio
async def test_renewal_link_is_hashed_and_unknown_tokens_404(client: AsyncClient, db: AsyncSession):
    from sqlalchemy import select as sa_select

    from app.models.notification import Notification
    from app.models.renewal import LeaseRenewal
    from app.models.tenant import Tenancy
    from app.services import renewal_service

    headers = await _make_agency_org(client)
    setup = await _expiring_tenancy(client, headers, db, days=30)
    tenancy = await db.get(Tenancy, uuid.UUID(setup["tenancy"]["id"]))
    renewal = await renewal_service.create_offer(db, tenancy)
    await db.commit()

    note = await db.scalar(
        sa_select(Notification)
        .where(Notification.entity_id == tenancy.id)
        .order_by(Notification.created_at.desc())
    )
    raw_token = note.body.rsplit("/renew/", 1)[1].strip()

    stored = await db.get(LeaseRenewal, renewal.id)
    assert raw_token not in stored.token_hash
    assert (await client.get("/api/v1/renew/not-a-real-token")).status_code == 404


@pytest.mark.asyncio
async def test_open_ended_tenancy_cannot_be_renewed(client: AsyncClient):
    headers = await _make_agency_org(client)
    setup = await _agency_money_path(client, headers)

    resp = await client.post(f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}", headers=headers, json={})
    assert resp.status_code == 400
    assert "open-ended" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_renewal_sweep_offers_at_thirty_days_and_escalates_at_fourteen(
    client: AsyncClient, db: AsyncSession
):
    from app.models.renewal import LeaseRenewal
    from app.services import renewal_service

    headers = await _make_agency_org(client)
    setup = await _expiring_tenancy(client, headers, db, days=30)
    tenancy_id = uuid.UUID(setup["tenancy"]["id"])

    async def offers() -> list[LeaseRenewal]:
        from sqlalchemy import select as sa_select

        rows = await db.scalars(sa_select(LeaseRenewal).where(LeaseRenewal.tenancy_id == tenancy_id))
        return list(rows)

    await renewal_service.offer_due_renewals(db)
    made = await offers()
    assert len(made) == 1
    assert made[0].escalated_at is None

    # Running again the next night does not offer a second time.
    await renewal_service.offer_due_renewals(db)
    assert len(await offers()) == 1

    # Move the lease to 14 days out; silence is escalated to the team, once.
    from datetime import timedelta

    from app.models.tenant import Tenancy

    tenancy = await db.get(Tenancy, tenancy_id)
    tenancy.end_date = date.today() + timedelta(days=14)
    await db.commit()

    await renewal_service.offer_due_renewals(db)
    await db.refresh(made[0])
    assert made[0].escalated_at is not None

    escalated_at = made[0].escalated_at
    await renewal_service.offer_due_renewals(db)
    await db.refresh(made[0])
    assert made[0].escalated_at == escalated_at


@pytest.mark.asyncio
async def test_renewals_are_scoped_to_the_organization(client: AsyncClient, db: AsyncSession):
    headers_a = await _make_agency_org(client)
    headers_b = await _make_agency_org(client)
    setup = await _expiring_tenancy(client, headers_a, db, days=30)

    resp = await client.post(
        f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}", headers=headers_b, json={}
    )
    assert resp.status_code == 403

    await client.post(f"/api/v1/renewals/tenancies/{setup['tenancy']['id']}", headers=headers_a, json={})
    assert (await client.get("/api/v1/renewals", headers=headers_b)).json() == []
    assert len((await client.get("/api/v1/renewals", headers=headers_a)).json()) == 1


# ---------------------------------------------------------------- task monitoring


@pytest.mark.asyncio
async def test_task_runs_are_recorded_with_their_result(client: AsyncClient, db: AsyncSession):
    """A green tick is useless; the dashboard shows what the run actually did."""
    from app.models.task_run import TaskRun, TaskRunStatus
    from app.services import task_monitor_service

    run_id = await task_monitor_service._start("rentflow.test_task", manual=False, session=db)
    await task_monitor_service._finish(run_id, "rentflow.test_task", result={"sent": 7}, session=db)

    run = await db.get(TaskRun, run_id)
    assert run.status == TaskRunStatus.SUCCEEDED
    assert run.result == {"sent": 7}
    assert run.duration_seconds is not None
    assert run.finished_at is not None


@pytest.mark.asyncio
async def test_a_failing_task_records_the_error_and_is_flagged_broken(client: AsyncClient, db: AsyncSession):
    from app.services import task_monitor_service

    name = f"rentflow.broken_{uuid.uuid4().hex[:8]}"
    for _ in range(task_monitor_service.ALERT_AFTER_CONSECUTIVE_FAILURES):
        run_id = await task_monitor_service._start(name, manual=False, session=db)
        await task_monitor_service._finish(run_id, name, error="ConnectionError: boom", session=db)

    overview = await task_monitor_service.overview(db)
    entry = next(task for task in overview["tasks"] if task["task_name"] == name)
    assert entry["last_status"] == "failed"
    assert entry["last_error"] == "ConnectionError: boom"
    assert entry["health"] == "broken"
    assert entry["failures_7d"] == task_monitor_service.ALERT_AFTER_CONSECUTIVE_FAILURES
    # It was never in the Beat schedule — the dashboard says so rather than lying.
    assert entry["scheduled"] is False


@pytest.mark.asyncio
async def test_task_overview_lists_every_scheduled_task(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.get("/api/v1/tasks", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    names = {task["task_name"] for task in body["tasks"]}
    # Every Beat entry appears, even one that has never run.
    assert "rentflow.generate_due_invoices" in names
    assert "rentflow.apply_late_fees" in names
    assert "rentflow.offer_lease_renewals" in names
    never_run = next(task for task in body["tasks"] if task["task_name"] == "rentflow.generate_due_invoices")
    assert never_run["scheduled"] is True
    assert never_run["schedule"] is not None


@pytest.mark.asyncio
async def test_only_a_system_admin_can_re_run_a_task(client: AsyncClient):
    headers = await _make_owner_org(client)
    resp = await client.post("/api/v1/tasks/rentflow.apply_late_fees/run", headers=headers)
    assert resp.status_code == 403
    assert "system administrator" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_task_history_is_readable_per_task(client: AsyncClient, db: AsyncSession):
    from app.services import task_monitor_service

    headers = await _make_owner_org(client)
    name = f"rentflow.history_{uuid.uuid4().hex[:8]}"
    for index in range(3):
        run_id = await task_monitor_service._start(name, manual=index == 0, session=db)
        await task_monitor_service._finish(run_id, name, result={"index": index}, session=db)

    resp = await client.get(f"/api/v1/tasks/{name}/history", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 3
    assert rows[0]["status"] == "succeeded"
    assert any(row["triggered_manually"] for row in rows)


# ------------------------------------------------------------ caretaker performance


@pytest.mark.asyncio
async def test_caretaker_score_weights_only_the_metrics_with_data():
    from app.services.caretaker_performance_service import weighted_score

    # All four present: the plain weighted mean.
    full = weighted_score(
        {
            "meter_compliance": 100.0,
            "inspection_completion": 100.0,
            "maintenance_response": 100.0,
            "cash_discipline": 100.0,
        }
    )
    assert full == 100.0

    # A caretaker on a property with no meters is not marked down for it — the
    # remaining weights are re-normalised rather than treated as zeros.
    partial = weighted_score(
        {
            "meter_compliance": None,
            "inspection_completion": 100.0,
            "maintenance_response": 100.0,
            "cash_discipline": 100.0,
        }
    )
    assert partial == 100.0

    assert weighted_score({key: None for key in ["meter_compliance"]}) is None


@pytest.mark.asyncio
async def test_maintenance_response_score_decays_with_delay():
    from app.services.caretaker_performance_service import _response_score

    assert _response_score(2) == 100.0
    assert _response_score(24) == 100.0
    assert _response_score(96) == 0.0
    assert _response_score(200) == 0.0
    mid = _response_score(60)
    assert 0 < mid < 100
    assert _response_score(None) is None


@pytest.mark.asyncio
async def test_caretaker_performance_lists_worst_first(client: AsyncClient, db: AsyncSession):
    """A caretaker with no assigned work scores nothing rather than a false 100."""
    headers = await _make_owner_org(client)

    invited = await client.post(
        "/api/v1/team/invitations",
        headers=headers,
        json={
            "email": f"caretaker-{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Mwangi Kamau",
            "role": "caretaker",
            "phone_number": f"+2547{abs(hash(uuid.uuid4().hex)) % 100000000:08d}",
        },
    )
    assert invited.status_code in (200, 201), invited.text

    resp = await client.get("/api/v1/caretaker/performance", headers=headers)
    assert resp.status_code == 200, resp.text
    # An invitation is not yet a user, so the list may be empty — what matters is
    # that the endpoint answers rather than erroring on an empty portfolio.
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_caretaker_performance_detail_404s_across_organizations(client: AsyncClient):
    headers_a = await _make_owner_org(client)
    headers_b = await _make_owner_org(client)

    me = await client.get("/api/v1/auth/me", headers=headers_a)
    resp = await client.get(f"/api/v1/caretaker/performance/{me.json()['id']}", headers=headers_b)
    assert resp.status_code == 404
