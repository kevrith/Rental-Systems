"""Sprint 22: fraud pattern detection (US-097) and security hardening (US-098)."""

from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from tests.conftest import TEST_PASSWORD, Actor
from tests.test_billing import setup_tenancy


async def _record_cash(owner: Actor, tenancy_id: str, amount: str) -> dict:
    response = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": tenancy_id,
            "amount": amount,
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _open_alerts(owner: Actor) -> list[dict]:
    response = await owner.get("/api/v1/security/fraud-alerts", params={"status": "open"})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------- IP whitelist


async def test_ip_whitelist_blocks_login_from_an_unlisted_address(client: AsyncClient, owner: Actor) -> None:
    update = await owner.patch("/api/v1/organizations/me", json={"ip_whitelist": ["203.0.113.4/32"]})
    assert update.status_code == 200, update.text

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": owner.user["email"], "password": TEST_PASSWORD},
        headers={"x-forwarded-for": "8.8.8.8"},
    )
    assert response.status_code == 403
    assert "not allowed from this network" in response.json()["detail"]


async def test_ip_whitelist_allows_a_matching_cidr(client: AsyncClient, owner: Actor) -> None:
    update = await owner.patch("/api/v1/organizations/me", json={"ip_whitelist": ["41.90.64.0/20"]})
    assert update.status_code == 200, update.text

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": owner.user["email"], "password": TEST_PASSWORD},
        headers={"x-forwarded-for": "41.90.64.10"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["otp_required"] is True


async def test_an_invalid_ip_entry_is_rejected_at_the_schema_level(owner: Actor) -> None:
    response = await owner.patch("/api/v1/organizations/me", json={"ip_whitelist": ["not-an-ip"]})
    assert response.status_code == 422


# ------------------------------------------------------------- session policy


async def test_role_session_timeout_policy_applies_immediately(owner: Actor) -> None:
    response = await owner.patch("/api/v1/organizations/me", json={"role_session_timeouts": {"owner": 111}})
    assert response.status_code == 200, response.text

    me = await owner.get("/api/v1/auth/me")
    assert me.json()["inactivity_timeout_minutes"] == 111


async def test_an_invalid_role_in_the_policy_is_rejected(owner: Actor) -> None:
    response = await owner.patch(
        "/api/v1/organizations/me", json={"role_session_timeouts": {"astronaut": 30}}
    )
    assert response.status_code == 422


# -------------------------------------------------------------- fraud detection


async def test_rapid_cash_payments_trigger_a_fraud_alert(owner: Actor) -> None:
    configured = await owner.patch(
        "/api/v1/organizations/me",
        json={"fraud_max_cash_payments_per_window": 2, "fraud_cash_window_minutes": 60},
    )
    assert configured.status_code == 200, configured.text

    for _ in range(2):
        setup = await setup_tenancy(owner, rent="10000.00")
        await _record_cash(owner, setup["tenancy"]["id"], "10000.00")

    alerts = await _open_alerts(owner)
    assert any(a["alert_type"] == "rapid_cash_payments" for a in alerts)


async def test_unusual_amount_triggers_a_fraud_alert(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await _record_cash(owner, setup["tenancy"]["id"], "150000.00")

    alerts = await _open_alerts(owner)
    match = next(a for a in alerts if a["alert_type"] == "unusual_amount")
    assert match["entity_type"] == "payment"
    assert Decimal(str(match["details"]["monthly_rent"])) == Decimal("10000.00")


async def test_duplicate_amount_in_quick_succession_triggers_a_velocity_alert(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await _record_cash(owner, setup["tenancy"]["id"], "10000.00")
    await _record_cash(owner, setup["tenancy"]["id"], "10000.00")

    alerts = await _open_alerts(owner)
    assert any(a["alert_type"] == "velocity_duplicate" for a in alerts)


async def test_suppressing_an_alert_silences_the_same_pattern(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await _record_cash(owner, setup["tenancy"]["id"], "150000.00")

    alerts = await _open_alerts(owner)
    alert = next(a for a in alerts if a["alert_type"] == "unusual_amount")

    suppressed = await owner.patch(
        f"/api/v1/security/fraud-alerts/{alert['id']}", json={"status": "suppressed"}
    )
    assert suppressed.status_code == 200
    assert suppressed.json()["status"] == "suppressed"

    # Same tenancy, same pattern key (`unusual_amount:<tenancy_id>`) — the
    # suppression should silence it even though the amount itself differs.
    await _record_cash(owner, setup["tenancy"]["id"], "5.00")

    reopened = await _open_alerts(owner)
    assert not any(a["alert_type"] == "unusual_amount" for a in reopened)


async def test_a_resolved_alert_cannot_be_resolved_twice(owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await _record_cash(owner, setup["tenancy"]["id"], "999999.00")
    alert = next(a for a in await _open_alerts(owner) if a["alert_type"] == "unusual_amount")

    await owner.patch(f"/api/v1/security/fraud-alerts/{alert['id']}", json={"status": "resolved"})
    second = await owner.patch(f"/api/v1/security/fraud-alerts/{alert['id']}", json={"status": "resolved"})
    assert second.status_code == 400


async def test_fraud_alerts_are_isolated_per_organization(owner: Actor, other_owner: Actor) -> None:
    setup = await setup_tenancy(owner, rent="10000.00")
    await _record_cash(owner, setup["tenancy"]["id"], "500000.00")

    other_alerts = await _open_alerts(other_owner)
    assert other_alerts == []


# ----------------------------------------------------------------- audit export


async def test_audit_log_export_csv_contains_recorded_actions(owner: Actor) -> None:
    await owner.patch("/api/v1/organizations/me", json={"legal_name": "Acacia Holdings Ltd"})

    response = await owner.get("/api/v1/security/audit-log/export", params={"format": "csv"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "organization.updated" in response.text


async def test_audit_log_export_pdf_is_a_pdf(owner: Actor) -> None:
    await owner.patch("/api/v1/organizations/me", json={"legal_name": "Acacia Holdings Ltd"})

    response = await owner.get("/api/v1/security/audit-log/export", params={"format": "pdf"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
