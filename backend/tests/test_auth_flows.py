"""Sprint 1: registration, 2FA login, sessions, tenant isolation, RBAC, trial."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User
from tests.conftest import TEST_PASSWORD, Actor, fresh_password, unique_phone, unique_suffix

PASSWORD = TEST_PASSWORD


async def _register(client: AsyncClient, **overrides) -> dict:
    suffix = unique_suffix()
    payload = {
        "full_name": "Jane Wanjiru",
        "organization_name": f"Acacia {suffix}",
        "email": f"jane-{suffix}@example.com",
        "phone_number": unique_phone(),
        "password": PASSWORD,
        "account_type": "owner",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ registration


async def test_registration_creates_org_user_and_trial(client: AsyncClient, db) -> None:
    payload = await _register(client)
    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()

    assert body["organization"]["subscription_plan"] == "trial"
    assert body["organization"]["trial_ends_at"] is not None
    assert body["user"]["role"] == "owner"
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]

    organization = await db.scalar(
        select(Organization).where(Organization.id == uuid.UUID(body["organization"]["id"]))
    )
    remaining = organization.trial_ends_at - datetime.now(UTC)
    assert timedelta(days=29) < remaining <= timedelta(days=30)


async def test_agency_registration_assigns_agency_admin(client: AsyncClient) -> None:
    payload = await _register(client, account_type="agency")
    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "agency_admin"
    assert response.json()["organization"]["operating_mode"] == "agency"


async def test_duplicate_email_is_rejected_with_a_clear_message(client: AsyncClient) -> None:
    payload = await _register(client)
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201

    second = await _register(client, email=payload["email"])
    response = await client.post("/api/v1/auth/register", json=second)

    assert response.status_code == 409
    assert "email address" in response.json()["detail"]


async def test_duplicate_phone_is_rejected(client: AsyncClient) -> None:
    payload = await _register(client)
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201

    second = await _register(client, phone_number=payload["phone_number"])
    response = await client.post("/api/v1/auth/register", json=second)

    assert response.status_code == 409
    assert "phone number" in response.json()["detail"]


async def test_phone_number_is_normalized_to_e164(client: AsyncClient) -> None:
    payload = await _register(client, phone_number="0712345678")
    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["user"]["phone_number"] == "+254712345678"


# -------------------------------------------------------------------------- login


async def test_login_requires_otp_then_issues_tokens(client: AsyncClient, fake_redis) -> None:
    payload = await _register(client)
    register = await client.post("/api/v1/auth/register", json=payload)
    user_id = register.json()["user"]["id"]

    challenge = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": PASSWORD}
    )
    assert challenge.status_code == 200
    assert challenge.json()["otp_required"] is True
    assert challenge.json()["tokens"] is None

    code = await fake_redis.get(f"otp:login:{user_id}")
    verified = await client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge.json()["challenge_token"], "otp_code": code},
    )

    assert verified.status_code == 200, verified.text
    assert verified.json()["access_token"]


async def test_wrong_otp_is_rejected(client: AsyncClient) -> None:
    payload = await _register(client)
    await client.post("/api/v1/auth/register", json=payload)

    challenge = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": PASSWORD}
    )
    response = await client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge.json()["challenge_token"], "otp_code": "000000"},
    )

    assert response.status_code == 401


async def test_bad_password_is_rejected(client: AsyncClient) -> None:
    payload = await _register(client)
    await client.post("/api/v1/auth/register", json=payload)

    response = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": "not-the-password"}
    )
    assert response.status_code == 401


async def test_five_failed_logins_trigger_a_lockout(client: AsyncClient) -> None:
    payload = await _register(client)
    await client.post("/api/v1/auth/register", json=payload)

    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"email": payload["email"], "password": "wrong"})

    # Even the correct password is refused while the lockout stands.
    response = await client.post("/api/v1/auth/login", json={"email": payload["email"], "password": PASSWORD})
    assert response.status_code == 403
    assert "Too many failed attempts" in response.json()["detail"]


async def test_trusted_device_skips_the_otp(client: AsyncClient) -> None:
    """The registering device is trusted, so it logs straight back in (US-002)."""
    payload = await _register(client)
    headers = {"X-Device-Id": "device-abc-123", "User-Agent": "Mozilla/5.0 (Android 14) Chrome/120"}
    await client.post("/api/v1/auth/register", json=payload, headers=headers)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": PASSWORD},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["otp_required"] is False
    assert response.json()["tokens"]["access_token"]


async def test_a_different_device_still_needs_the_otp(client: AsyncClient) -> None:
    payload = await _register(client)
    await client.post("/api/v1/auth/register", json=payload, headers={"X-Device-Id": "device-abc-123"})

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": PASSWORD},
        headers={"X-Device-Id": "a-completely-different-device"},
    )

    assert response.json()["otp_required"] is True


# ------------------------------------------------------------------------ tokens


async def test_refresh_rotates_the_token(client: AsyncClient, owner: Actor) -> None:
    original = owner.tokens["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})

    assert response.status_code == 200
    assert response.json()["refresh_token"] != original


async def test_replaying_an_old_refresh_token_kills_every_session(client: AsyncClient, owner: Actor) -> None:
    """Reuse of a rotated token is treated as theft (US-002)."""
    original = owner.tokens["refresh_token"]
    rotated = (await client.post("/api/v1/auth/refresh", json={"refresh_token": original})).json()

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401
    assert "reuse detected" in replay.json()["detail"]

    # The token issued by the legitimate rotation is dead too.
    after = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert after.status_code == 401


async def test_access_token_is_required(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 403


async def test_garbage_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


# ---------------------------------------------------------------------- sessions


async def test_sessions_list_marks_the_current_session(owner: Actor) -> None:
    response = await owner.get("/api/v1/auth/sessions")

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True


async def test_revoking_other_sessions_leaves_the_current_one(
    client: AsyncClient, owner: Actor, fake_redis
) -> None:
    # Open a second session by logging in from another device.
    challenge = await client.post(
        "/api/v1/auth/login",
        json={"email": owner.user["email"], "password": PASSWORD},
        headers={"X-Device-Id": "second-device"},
    )
    code = await fake_redis.get(f"otp:login:{owner.user['id']}")
    await client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge.json()["challenge_token"], "otp_code": code},
        headers={"X-Device-Id": "second-device"},
    )

    assert len((await owner.get("/api/v1/auth/sessions")).json()) == 2

    revoked = await owner.post("/api/v1/auth/sessions/revoke-others")
    assert revoked.status_code == 200

    remaining = (await owner.get("/api/v1/auth/sessions")).json()
    assert len(remaining) == 1
    assert remaining[0]["is_current"] is True


async def test_logout_ends_the_session(client: AsyncClient, owner: Actor) -> None:
    response = await owner.post("/api/v1/auth/logout", json={"refresh_token": owner.tokens["refresh_token"]})
    assert response.status_code == 200

    # The refresh token no longer works, even though the access token has not expired.
    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": owner.tokens["refresh_token"]})
    assert refresh.status_code == 401


# ---------------------------------------------------------------------- profile


async def test_me_returns_the_role_permission_list(owner: Actor) -> None:
    response = await owner.get("/api/v1/auth/me")

    assert response.status_code == 200
    permissions = response.json()["permissions"]
    assert "property:manage" in permissions
    assert "org:manage" in permissions


async def test_changing_phone_number_clears_verification(owner: Actor) -> None:
    response = await owner.patch("/api/v1/auth/me", json={"phone_number": "0733111222"})

    assert response.status_code == 200
    assert response.json()["phone_number"] == "+254733111222"
    assert response.json()["is_phone_verified"] is False


async def test_password_change_requires_the_current_password(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/auth/change-password",
        json={"current_password": fresh_password(), "new_password": fresh_password()},
    )

    assert response.status_code == 400
    assert "current password is incorrect" in response.json()["detail"]


async def test_password_change_succeeds_and_allows_the_new_password(
    client: AsyncClient, owner: Actor
) -> None:
    new_password = fresh_password()
    response = await owner.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": new_password},
    )
    assert response.status_code == 200

    login = await client.post(
        "/api/v1/auth/login", json={"email": owner.user["email"], "password": new_password}
    )
    assert login.status_code == 200


async def test_account_deletion_is_a_reversible_request(owner: Actor) -> None:
    requested = await owner.post("/api/v1/auth/me/delete")
    assert requested.status_code == 200
    assert (await owner.get("/api/v1/auth/me")).json()["deletion_requested_at"] is not None

    cancelled = await owner.post("/api/v1/auth/me/delete/cancel")
    assert cancelled.status_code == 200
    assert (await owner.get("/api/v1/auth/me")).json()["deletion_requested_at"] is None


# ----------------------------------------------------------- email verification


async def test_email_verification_link_verifies_the_account(client: AsyncClient, db, owner: Actor) -> None:
    from app.models.session import TokenPurpose

    # The raw token is only ever sent to the user, so re-issue one to test with.
    from app.services import auth_service

    user = await db.get(User, uuid.UUID(owner.user["id"]))
    raw = await auth_service.issue_link_token(db, user, TokenPurpose.EMAIL_VERIFICATION, 24)
    await db.commit()

    response = await client.post("/api/v1/auth/verify-email", json={"token": raw})

    assert response.status_code == 200
    assert response.json()["is_email_verified"] is True

    # Single use — a replay fails.
    replay = await client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert replay.status_code == 400


async def test_forgot_password_does_not_leak_whether_an_account_exists(client: AsyncClient) -> None:
    known = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody-at-all@example.com"})
    assert known.status_code == 200
    assert "If that account exists" in known.json()["message"]


# ---------------------------------------------------------------- multi-tenancy


async def test_a_token_cannot_read_another_organizations_data(owner: Actor, other_owner: Actor) -> None:
    created = await owner.post(
        "/api/v1/properties",
        json={"name": "Kilimani Heights", "address": "Kilimani Road", "county": "Nairobi"},
    )
    property_id = created.json()["id"]

    # The other organization gets 403 — never 404, which would confirm the id exists.
    response = await other_owner.get(f"/api/v1/properties/{property_id}")
    assert response.status_code == 403
    assert "do not have access" in response.json()["detail"]


async def test_listings_never_include_another_organizations_rows(owner: Actor, other_owner: Actor) -> None:
    await owner.post("/api/v1/properties", json={"name": "Mine Only", "address": "Somewhere in Nairobi"})

    listed = await other_owner.get("/api/v1/properties")
    assert listed.status_code == 200
    assert listed.json() == []


async def test_a_missing_id_is_a_404_not_a_403(owner: Actor) -> None:
    response = await owner.get(f"/api/v1/properties/{uuid.uuid4()}")
    assert response.status_code == 404


# ----------------------------------------------------------------- trial gating


async def test_expired_trial_blocks_writes_but_allows_reads(owner: Actor, db) -> None:
    """An expired trial becomes read-only, never invisible (US-006)."""
    organization = await db.get(Organization, uuid.UUID(owner.user["organization_id"]))
    organization.trial_ends_at = datetime.now(UTC) - timedelta(days=1)
    await db.commit()

    write = await owner.post("/api/v1/properties", json={"name": "Too Late", "address": "Nairobi"})
    assert write.status_code == 402
    assert "free trial has ended" in write.json()["detail"]

    read = await owner.get("/api/v1/properties")
    assert read.status_code == 200


async def test_organization_endpoint_reports_trial_state(owner: Actor) -> None:
    response = await owner.get("/api/v1/organizations/me")

    assert response.status_code == 200
    body = response.json()
    assert body["is_trial"] is True
    assert body["is_trial_expired"] is False
    assert body["is_read_only"] is False
    assert 28 <= body["trial_days_remaining"] <= 30
