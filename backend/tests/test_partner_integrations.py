"""Sprint 23: property portal sync, accounting sync, and bank transfer (US-099,
US-100, US-101)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import encrypt
from app.models.integrations import (
    AccountingConnection,
    AccountingProvider,
    AccountingSyncRecord,
    AccountingSyncStatus,
)
from app.services import accounting_service, portal_integration_service
from tests.conftest import Actor
from tests.test_billing import setup_tenancy
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant


async def _fake_call_portal(db, connection, method, path, payload=None):
    """Stands in for the real HTTP call. Takes `db` because the credential is
    now decrypted with the organisation's own key (Sprint 26), which needs a
    session."""
    return {"id": "PORTAL-EXT-1"}


# ------------------------------------------------------------------- bank transfer


async def test_bank_transfer_reference_is_stored(owner: Actor) -> None:
    """Regression: `reference` used to be silently dropped for anything but
    M-Pesa — see `payment_service.record_cash_payment`."""
    setup = await setup_tenancy(owner)
    response = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "payment_date": date.today().isoformat(),
            "method": "bank_transfer",
            "reference": "FT26091234567",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["bank_reference"] == "FT26091234567"
    assert response.json()["mpesa_receipt"] is None


async def test_bank_instructions_reflect_organization_settings(owner: Actor) -> None:
    before = await owner.get("/api/v1/payments/bank-instructions")
    assert before.json()["configured"] is False

    await owner.patch(
        "/api/v1/organizations/me",
        json={
            "bank_name": "Equity Bank",
            "bank_account_name": "Acacia Rentals Ltd",
            "bank_account_number": "1234567890",
            "bank_branch": "Westlands",
        },
    )
    after = await owner.get("/api/v1/payments/bank-instructions")
    body = after.json()
    assert body["configured"] is True
    assert body["bank_name"] == "Equity Bank"
    assert body["account_number"] == "1234567890"


async def test_bank_statement_preview_matches_a_row_by_reference_code(owner: Actor) -> None:
    setup = await setup_tenancy(owner)
    ref = setup["tenancy"]["reference_code"]
    csv_body = (
        "Date,Description,Amount\n"
        f"2026-09-01,RENT {ref} JOHN,25000.00\n"
        "2026-09-02,UNKNOWN DEPOSIT,5000.00\n"
    ).encode()

    response = await owner.post(
        "/api/v1/payments/bank-statements/preview",
        files={"file": ("statement.csv", csv_body, "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched_count"] == 1
    assert body["unmatched_count"] == 1
    matched_row = next(row for row in body["rows"] if row["matched_tenancy_id"])
    assert matched_row["reference_guess"] == ref


async def test_bank_statement_commit_records_a_confirmed_payment(owner: Actor) -> None:
    setup = await setup_tenancy(owner)
    ref = setup["tenancy"]["reference_code"]
    csv_body = f"Date,Description,Amount\n2026-09-01,RENT {ref},25000.00\n".encode()

    preview = await owner.post(
        "/api/v1/payments/bank-statements/preview",
        files={"file": ("statement.csv", csv_body, "text/csv")},
    )
    row = preview.json()["rows"][0]

    commit = await owner.post(
        "/api/v1/payments/bank-statements/commit",
        json={"rows": [{**row, "tenancy_id": row["matched_tenancy_id"], "record_payment": True}]},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["upload"]["matched_count"] == 1
    assert result["upload"]["unmatched_count"] == 0
    assert not result["payment_failures"]

    payments = await owner.get(f"/api/v1/payments?tenancy_id={setup['tenancy']['id']}")
    bank_payments = [p for p in payments.json() if p["method"] == "bank_transfer"]
    assert len(bank_payments) == 1
    assert bank_payments[0]["bank_reference"]

    history = await owner.get("/api/v1/payments/bank-statements")
    assert history.status_code == 200
    assert len(history.json()) == 1

    detail = await owner.get(f"/api/v1/payments/bank-statements/{history.json()[0]['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["entries"]) == 1
    assert detail.json()["entries"][0]["is_matched"] is True


async def test_bank_statements_are_isolated_per_organization(owner: Actor, other_owner: Actor) -> None:
    csv_body = b"Date,Description,Amount\n2026-09-01,MYSTERY DEPOSIT,5000.00\n"
    preview = await owner.post(
        "/api/v1/payments/bank-statements/preview",
        files={"file": ("statement.csv", csv_body, "text/csv")},
    )
    row = preview.json()["rows"][0]
    commit = await owner.post(
        "/api/v1/payments/bank-statements/commit",
        json={"rows": [{**row, "tenancy_id": None, "record_payment": False}]},
    )
    upload_id = commit.json()["upload"]["id"]

    other_list = await other_owner.get("/api/v1/payments/bank-statements")
    assert other_list.json() == []

    other_detail = await other_owner.get(f"/api/v1/payments/bank-statements/{upload_id}")
    assert other_detail.status_code in (403, 404)


async def test_bank_statement_unmatched_row_is_not_recorded(owner: Actor) -> None:
    csv_body = b"Date,Description,Amount\n2026-09-01,MYSTERY DEPOSIT,5000.00\n"
    preview = await owner.post(
        "/api/v1/payments/bank-statements/preview",
        files={"file": ("statement.csv", csv_body, "text/csv")},
    )
    row = preview.json()["rows"][0]
    assert row["matched_tenancy_id"] is None

    commit = await owner.post(
        "/api/v1/payments/bank-statements/commit",
        json={"rows": [{**row, "tenancy_id": None, "record_payment": True}]},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["upload"]["unmatched_count"] == 1
    assert commit.json()["upload"]["matched_count"] == 0


# ------------------------------------------------------------------ property portals


async def test_portal_api_key_is_never_returned(owner: Actor) -> None:
    save = await owner.put("/api/v1/integrations/portals/pigiame", json={"api_key": "super-secret-key-123"})
    assert save.status_code == 200, save.text
    assert "super-secret-key-123" not in save.text

    listed = await owner.get("/api/v1/integrations/portals")
    assert "super-secret-key-123" not in listed.text
    assert listed.json()[0]["configured"] is True


async def test_portal_connections_are_isolated_per_organization(owner: Actor, other_owner: Actor) -> None:
    await owner.put("/api/v1/integrations/portals/buyrentkenya", json={"api_key": "key-1234"})
    other_list = await other_owner.get("/api/v1/integrations/portals")
    assert other_list.json() == []


async def test_publishing_a_listing_syncs_to_connected_portals(
    owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(portal_integration_service, "_call_portal", _fake_call_portal)

    save = await owner.put(
        "/api/v1/integrations/portals/buyrentkenya", json={"api_key": "key-1234", "account_id": "acc-1"}
    )
    assert save.status_code == 200, save.text

    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    listing = await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")
    assert listing.status_code == 200, listing.text

    sync_rows = await owner.get(f"/api/v1/integrations/portals/listings/{listing.json()['id']}")
    assert sync_rows.status_code == 200, sync_rows.text
    rows = sync_rows.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "published"
    assert rows[0]["external_listing_id"] == "PORTAL-EXT-1"


async def test_occupying_a_unit_deactivates_its_portal_listings(
    owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(portal_integration_service, "_call_portal", _fake_call_portal)
    await owner.put("/api/v1/integrations/portals/buyrentkenya", json={"api_key": "key-1234"})

    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    listing = (await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")).json()

    tenant = await make_tenant(owner)
    await make_tenancy(owner, tenant["id"], unit["id"])

    sync_rows = (await owner.get(f"/api/v1/integrations/portals/listings/{listing['id']}")).json()
    assert sync_rows[0]["status"] == "deactivated"


async def test_portal_inquiry_from_an_unknown_connection_is_a_safe_no_op(owner: Actor) -> None:
    """A stale or unrecognised `connection_id` must never 500 — it is a
    partner's server calling us, not someone who can act on an error."""
    response = await owner.client.post(
        "/api/v1/portal-webhooks/00000000-0000-0000-0000-000000000000/inquiries",
        json={
            "external_listing_id": "PORTAL-EXT-1",
            "full_name": "Grace Wafula",
            "phone_number": "+254712345000",
            "message": "Is it still available?",
        },
    )
    assert response.status_code == 202
    assert response.json()["accepted"] is False


async def test_portal_inquiry_from_a_known_listing_lands_in_the_lead_pipeline(
    owner: Actor, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.integrations import PortalConnection

    monkeypatch.setattr(portal_integration_service, "_call_portal", _fake_call_portal)
    await owner.put("/api/v1/integrations/portals/pigiame", json={"api_key": "key-1234"})

    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    # The GET itself creates and publishes the listing, which is what pushes
    # "PORTAL-EXT-1" onto the sync row the inquiry below needs to resolve.
    await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")

    org = (await owner.get("/api/v1/organizations/me")).json()
    connection = await db.scalar(
        select(PortalConnection).where(PortalConnection.organization_id == uuid.UUID(org["id"]))
    )
    assert connection is not None

    response = await owner.client.post(
        f"/api/v1/portal-webhooks/{connection.id}/inquiries",
        json={
            "external_listing_id": "PORTAL-EXT-1",
            "full_name": "Grace Wafula",
            "phone_number": "+254712345000",
            "message": "Is it still available?",
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["accepted"] is True

    inquiries = await owner.get("/api/v1/vacancies/inquiries")
    assert inquiries.status_code == 200
    matches = [row for row in inquiries.json() if row["unit_id"] == unit["id"]]
    assert len(matches) == 1
    assert matches[0]["source"] == "pigiame"


# --------------------------------------------------------------- accounting software


async def test_accounting_connect_without_credentials_returns_503(owner: Actor) -> None:
    response = await owner.get("/api/v1/integrations/accounting/quickbooks/connect")
    assert response.status_code == 503


async def test_accounting_connections_are_isolated_per_organization(
    owner: Actor, other_owner: Actor, db
) -> None:
    org = (await owner.get("/api/v1/organizations/me")).json()
    connection = AccountingConnection(
        organization_id=uuid.UUID(org["id"]),
        provider=AccountingProvider.QUICKBOOKS,
        access_token_encrypted=encrypt("at"),
        refresh_token_encrypted=encrypt("rt"),
        external_account_id="REALM-1",
    )
    db.add(connection)
    await db.commit()

    other_list = await other_owner.get("/api/v1/integrations/accounting")
    assert other_list.json() == []

    other_report = await other_owner.get("/api/v1/integrations/accounting/quickbooks/report")
    assert other_report.json() == {"synced": 0, "failed": 0, "pending": 0, "recent_failures": []}


async def test_accounting_oauth_callback_stores_connection(
    owner: Actor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "QUICKBOOKS_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "QUICKBOOKS_CLIENT_SECRET", "client-secret")

    async def fake_exchange(provider, code):
        return {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}

    monkeypatch.setattr(accounting_service, "_exchange_code", fake_exchange)

    org = (await owner.get("/api/v1/organizations/me")).json()
    state = accounting_service._sign_state(uuid.UUID(org["id"]), AccountingProvider.QUICKBOOKS)

    response = await owner.client.get(
        "/api/v1/oauth/accounting/quickbooks/callback",
        params={"code": "auth-code", "state": state, "realmId": "REALM-1"},
    )
    assert response.status_code == 307
    assert "connected=quickbooks" in response.headers["location"]

    connections = await owner.get("/api/v1/integrations/accounting")
    assert connections.status_code == 200
    body = connections.json()
    assert len(body) == 1
    assert body[0]["external_account_id"] == "REALM-1"
    assert body[0]["provider"] == "quickbooks"


async def test_accounting_sync_records_a_payment(owner: Actor, db, monkeypatch: pytest.MonkeyPatch) -> None:
    setup = await setup_tenancy(owner)
    await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": setup["tenancy"]["id"],
            "amount": "25000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )

    org = (await owner.get("/api/v1/organizations/me")).json()
    connection = AccountingConnection(
        organization_id=uuid.UUID(org["id"]),
        provider=AccountingProvider.QUICKBOOKS,
        access_token_encrypted=encrypt("at"),
        refresh_token_encrypted=encrypt("rt"),
        external_account_id="REALM-1",
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    async def fake_post_entity(connection, access_token, kind, payload):
        return "QB-EXT-1"

    monkeypatch.setattr(accounting_service, "_post_entity", fake_post_entity)

    await accounting_service.sync_connection(db, connection)

    records = list(
        await db.scalars(
            select(AccountingSyncRecord).where(AccountingSyncRecord.connection_id == connection.id)
        )
    )
    assert len(records) == 1
    assert records[0].status == AccountingSyncStatus.SYNCED
    assert records[0].external_id == "QB-EXT-1"

    # Re-running the sweep never double-posts the same payment.
    await accounting_service.sync_connection(db, connection)
    records_again = list(
        await db.scalars(
            select(AccountingSyncRecord).where(AccountingSyncRecord.connection_id == connection.id)
        )
    )
    assert len(records_again) == 1


async def test_accounting_sync_batch_advances_past_already_synced_rows(
    owner: Actor, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: with a batch size smaller than the backlog, a plain
    `ORDER BY paid_at LIMIT n` would keep re-fetching the same oldest,
    already-synced rows forever and never reach the newer ones."""
    setup = await setup_tenancy(owner)
    for _ in range(2):
        await owner.post(
            "/api/v1/payments",
            json={
                "tenancy_id": setup["tenancy"]["id"],
                "amount": "1000.00",
                "payment_date": date.today().isoformat(),
                "method": "cash",
            },
        )

    org = (await owner.get("/api/v1/organizations/me")).json()
    connection = AccountingConnection(
        organization_id=uuid.UUID(org["id"]),
        provider=AccountingProvider.QUICKBOOKS,
        access_token_encrypted=encrypt("at"),
        refresh_token_encrypted=encrypt("rt"),
        external_account_id="REALM-1",
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    async def fake_post_entity(connection, access_token, kind, payload):
        return "QB-EXT-1"

    monkeypatch.setattr(accounting_service, "_post_entity", fake_post_entity)
    monkeypatch.setattr(accounting_service, "SYNC_BATCH_SIZE", 1)

    await accounting_service.sync_connection(db, connection)
    await accounting_service.sync_connection(db, connection)

    synced = list(
        await db.scalars(
            select(AccountingSyncRecord).where(
                AccountingSyncRecord.connection_id == connection.id,
                AccountingSyncRecord.status == AccountingSyncStatus.SYNCED,
            )
        )
    )
    assert len(synced) == 2
