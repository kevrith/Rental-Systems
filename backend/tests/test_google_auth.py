"""Sign in with Google: registration, login, account linking.

`verify_google_credential` is monkeypatched to a canned identity throughout —
these tests are about RentFlow's own account logic, not Google's token format,
and the real function is exercised by hitting Google's actual JWKS endpoint.
"""

import pytest
from httpx import AsyncClient

from app.services import auth_service
from app.services.google_oauth import GoogleIdentity
from tests.conftest import register_owner, unique_phone, unique_suffix


def _identity(**overrides) -> GoogleIdentity:
    suffix = unique_suffix()
    defaults: dict = {
        "sub": f"google-sub-{suffix}",
        "email": f"google-{suffix}@example.com",
        "email_verified": True,
        "full_name": "Jane Wanjiru",
    }
    defaults.update(overrides)
    return GoogleIdentity(**defaults)


def _stub(monkeypatch: pytest.MonkeyPatch, identity: GoogleIdentity) -> None:
    async def fake_verify(credential: str) -> GoogleIdentity:
        return identity

    monkeypatch.setattr(auth_service, "verify_google_credential", fake_verify)


def _register_payload(**overrides) -> dict:
    payload = {
        "credential": "whatever",
        "organization_name": f"Acacia {unique_suffix()}",
        "phone_number": unique_phone(),
        "account_type": "owner",
    }
    payload.update(overrides)
    return payload


async def test_unknown_google_account_asks_for_registration(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    _stub(monkeypatch, identity)

    response = await client.post("/api/v1/auth/google", json={"credential": "whatever"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_registration"
    assert body["email"] == identity.email
    assert body["full_name"] == identity.full_name
    assert body["tokens"] is None


async def test_google_register_creates_org_and_verified_user(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    _stub(monkeypatch, identity)

    response = await client.post("/api/v1/auth/google/register", json=_register_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == identity.email
    assert body["user"]["is_email_verified"] is True
    assert body["organization"]["subscription_plan"] == "trial"
    assert body["tokens"]["access_token"]


async def test_google_login_after_registration_skips_otp(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    _stub(monkeypatch, identity)
    assert (await client.post("/api/v1/auth/google/register", json=_register_payload())).status_code == 201

    response = await client.post("/api/v1/auth/google", json={"credential": "whatever"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signed_in"
    assert body["tokens"]["access_token"]


async def test_google_register_rejects_duplicate_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity()
    _stub(monkeypatch, identity)
    assert (await client.post("/api/v1/auth/google/register", json=_register_payload())).status_code == 201

    # Same Google identity (the stub returns it regardless of credential), a
    # fresh org/phone — still collides on email.
    response = await client.post("/api/v1/auth/google/register", json=_register_payload())

    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


async def test_google_login_links_existing_password_account_by_verified_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await register_owner(client)
    identity = _identity(email=actor.user["email"])
    _stub(monkeypatch, identity)

    response = await client.post("/api/v1/auth/google", json={"credential": "whatever"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signed_in"
    assert body["tokens"]["access_token"]


async def test_google_auth_rejects_unverified_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity(email_verified=False)
    _stub(monkeypatch, identity)

    response = await client.post("/api/v1/auth/google", json={"credential": "whatever"})

    assert response.status_code == 400


async def test_google_register_rejects_unverified_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity(email_verified=False)
    _stub(monkeypatch, identity)

    response = await client.post("/api/v1/auth/google/register", json=_register_payload())

    assert response.status_code == 400
