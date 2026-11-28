"""Caretaker PIN sign-in, and trusting the phone at invitation and tenant set-up.

A caretaker chooses a 6-digit PIN when they accept their invitation. After that
they sign in with phone number and PIN, but only from the phone they registered.
A new phone or a forgotten PIN needs a code the landlord hands over.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_url_token, hash_token
from app.models.session import Invitation, TokenPurpose, VerificationToken
from tests.conftest import TEST_PASSWORD, Actor, fresh_password, unique_phone
from tests.test_tenancy import make_tenant

PIN = "482913"
OTHER_PIN = "907351"


def _device(name: str) -> dict[str, str]:
    """Headers for one browser. The id is what the server remembers a phone by."""
    return {"x-device-id": f"{name}-{uuid.uuid4().hex}", "user-agent": f"Test phone {name}"}


async def _invite(
    owner: Actor, db: AsyncSession, *, role: str = "caretaker", email: str | None = None
) -> tuple[str, str]:
    """Invite someone and return (raw invitation token, their phone number)."""
    phone = unique_phone()
    payload = {"full_name": "Test Caretaker", "phone_number": phone, "role": role, "property_ids": []}
    if email:
        payload["email"] = email
    invited = await owner.post("/api/v1/team/invitations", json=payload)
    assert invited.status_code == 201, invited.text
    invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invited.json()["id"])))
    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()
    return raw, phone


async def _accept(client: AsyncClient, token: str, headers: dict[str, str], **credential: str):
    return await client.post(
        "/api/v1/invitations/accept", json={"token": token, **credential}, headers=headers
    )


async def _pin_login(client: AsyncClient, phone: str, pin: str, headers: dict[str, str]):
    return await client.post(
        "/api/v1/auth/login/pin", json={"phone_number": phone, "pin": pin}, headers=headers
    )


async def _caretaker_with_pin(
    owner: Actor, client: AsyncClient, db: AsyncSession, phone_device: dict[str, str]
) -> tuple[str, dict]:
    token, phone = await _invite(owner, db)
    accepted = await _accept(client, token, phone_device, pin=PIN)
    assert accepted.status_code == 200, accepted.text
    return phone, accepted.json()


async def test_a_caretaker_chooses_a_pin_and_signs_in_with_it_on_the_same_phone(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    phone_a = _device("a")
    phone, accepted = await _caretaker_with_pin(owner, client, db, phone_a)
    assert accepted["user"]["role"] == "caretaker"

    signed_in = await _pin_login(client, phone, PIN, phone_a)
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["access_token"]


async def test_a_pin_account_has_no_usable_password(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    phone_a = _device("a")
    phone, accepted = await _caretaker_with_pin(owner, client, db, phone_a)

    # The placeholder email and a guessed password must not be a way in.
    for password in (PIN, TEST_PASSWORD, "!"):
        attempt = await client.post(
            "/api/v1/auth/login",
            json={"email": accepted["user"]["email"], "password": password},
            headers=phone_a,
        )
        assert attempt.status_code in (401, 422)


async def test_the_pin_does_not_work_from_another_phone_and_does_not_lock_the_real_one(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    phone_a = _device("a")
    phone, _ = await _caretaker_with_pin(owner, client, db, phone_a)

    # Someone who knows the number and even the right PIN, on an unregistered
    # phone, gets nowhere and is not counted against the caretaker.
    stranger = _device("stranger")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS + 3):
        refused = await _pin_login(client, phone, PIN, stranger)
        assert refused.status_code == 401
    no_header = await client.post("/api/v1/auth/login/pin", json={"phone_number": phone, "pin": PIN})
    assert no_header.status_code == 401

    still_works = await _pin_login(client, phone, PIN, phone_a)
    assert still_works.status_code == 200, still_works.text


async def test_wrong_pins_lock_the_phone_for_a_while(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    phone_a = _device("a")
    phone, _ = await _caretaker_with_pin(owner, client, db, phone_a)

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        wrong = await _pin_login(client, phone, OTHER_PIN, phone_a)
        assert wrong.status_code == 401

    # Locked: even the right PIN waits.
    locked = await _pin_login(client, phone, PIN, phone_a)
    assert locked.status_code == 403
    assert "Try again" in locked.json()["detail"]["message"]


async def test_too_many_wrong_pins_in_a_day_need_a_new_code(
    client: AsyncClient, owner: Actor, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, fake_redis
) -> None:
    monkeypatch.setattr(settings, "PIN_MAX_FAILURES_PER_DAY", 2)
    phone_a = _device("a")
    phone, accepted = await _caretaker_with_pin(owner, client, db, phone_a)
    caretaker_id = accepted["user"]["id"]

    for _ in range(2):
        assert (await _pin_login(client, phone, OTHER_PIN, phone_a)).status_code == 401
    # The five-minute lockout is a separate, shorter mechanism. Clear it to show
    # it is the daily cap, not the short lockout, that now refuses the right PIN.
    await fake_redis.delete(f"login_fails:pin:{phone}", f"login_lockout:pin:{phone}")
    capped = await _pin_login(client, phone, PIN, phone_a)
    assert capped.status_code == 401
    assert "new sign-in code" in capped.json()["detail"]

    # A code from the owner unlocks it and the new PIN works straight away.
    code = (await owner.post(f"/api/v1/team/{caretaker_id}/signin-code")).json()["code"]
    enrolled = await client.post(
        "/api/v1/auth/login/pin/enroll",
        json={"phone_number": phone, "code": code, "pin": OTHER_PIN},
        headers=phone_a,
    )
    assert enrolled.status_code == 200, enrolled.text
    assert (await _pin_login(client, phone, OTHER_PIN, phone_a)).status_code == 200
    assert (await _pin_login(client, phone, PIN, phone_a)).status_code == 401


async def test_a_new_phone_needs_a_handed_over_code_and_moves_the_caretaker_there(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    phone_a, phone_b = _device("a"), _device("b")
    phone, accepted = await _caretaker_with_pin(owner, client, db, phone_a)
    old_refresh = accepted["tokens"]["refresh_token"]

    code = (await owner.post(f"/api/v1/team/{accepted['user']['id']}/signin-code")).json()["code"]
    enrolled = await client.post(
        "/api/v1/auth/login/pin/enroll",
        json={"phone_number": phone, "code": code, "pin": OTHER_PIN},
        headers=phone_b,
    )
    assert enrolled.status_code == 200, enrolled.text

    assert (await _pin_login(client, phone, OTHER_PIN, phone_b)).status_code == 200
    # The old phone and its sessions stop working the moment the new one is set up.
    assert (await _pin_login(client, phone, OTHER_PIN, phone_a)).status_code == 401
    assert (await _pin_login(client, phone, PIN, phone_a)).status_code == 401
    stale = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert stale.status_code == 401

    # The code was single use.
    again = await client.post(
        "/api/v1/auth/login/pin/enroll",
        json={"phone_number": phone, "code": code, "pin": PIN},
        headers=phone_b,
    )
    assert again.status_code == 401


async def test_setting_a_pin_refuses_wrong_codes_obvious_pins_and_unknown_numbers(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    phone_a = _device("a")
    phone, accepted = await _caretaker_with_pin(owner, client, db, phone_a)
    code = (await owner.post(f"/api/v1/team/{accepted['user']['id']}/signin-code")).json()["code"]

    async def enroll(**fields: str):
        body = {"phone_number": phone, "code": code, "pin": OTHER_PIN} | fields
        return await client.post("/api/v1/auth/login/pin/enroll", json=body, headers=_device("c"))

    wrong_code = await enroll(code="0" * len(code))
    unknown_number = await enroll(phone_number="+254700000999")
    # Wrong code and unknown number are indistinguishable.
    assert wrong_code.status_code == unknown_number.status_code == 401
    assert wrong_code.json() == unknown_number.json()

    for obvious in ("123456", "000000", "121212", "12345", "abcdef"):
        assert (await enroll(pin=obvious)).status_code == 422

    no_device = await client.post(
        "/api/v1/auth/login/pin/enroll",
        json={"phone_number": phone, "code": code, "pin": OTHER_PIN},
    )
    assert no_device.status_code == 400


async def test_only_caretakers_can_choose_a_pin_and_only_one_credential_is_taken(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    manager_token, _ = await _invite(owner, db, role="property_manager")
    refused = await _accept(client, manager_token, _device("a"), pin=PIN)
    assert refused.status_code == 400

    token, _ = await _invite(owner, db)
    both = await _accept(client, token, _device("a"), pin=PIN, password=fresh_password())
    neither = await _accept(client, token, _device("a"))
    weak = await _accept(client, token, _device("a"), pin="123456")
    assert both.status_code == neither.status_code == weak.status_code == 422

    # No phone identifier, no PIN: there would be nothing to sign in from later.
    no_device = await client.post("/api/v1/invitations/accept", json={"token": token, "pin": PIN})
    assert no_device.status_code == 400


async def test_a_caretaker_without_a_pin_cannot_use_pin_sign_in(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    token, phone = await _invite(owner, db, email=f"c-{uuid.uuid4().hex[:8]}@example.com")
    phone_a = _device("a")
    assert (await _accept(client, token, phone_a, password=fresh_password())).status_code == 200

    assert (await _pin_login(client, phone, PIN, phone_a)).status_code == 401


async def test_accepting_an_invitation_trusts_the_phone(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    email = f"c-{uuid.uuid4().hex[:8]}@example.com"
    token, _ = await _invite(owner, db, role="property_manager", email=email)
    password, phone_a = fresh_password(), _device("a")
    assert (await _accept(client, token, phone_a, password=password)).status_code == 200

    # First sign-in on the phone they joined from needs no code...
    here = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=phone_a
    )
    assert here.status_code == 200, here.text
    assert here.json()["otp_required"] is False
    # ...but a different phone still does.
    elsewhere = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=_device("b")
    )
    assert elsewhere.json()["otp_required"] is True


async def test_tenant_portal_setup_trusts_the_phone(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    email = f"t-{uuid.uuid4().hex[:8]}@example.com"
    tenant = await make_tenant(owner, phone_number=unique_phone(), email=email)
    assert (await owner.post("/api/v1/portal/invite", json={"tenant_id": tenant["id"]})).status_code == 200

    token_row = await db.scalar(
        select(VerificationToken)
        .where(VerificationToken.purpose == TokenPurpose.TENANT_PORTAL_INVITE)
        .order_by(VerificationToken.created_at.desc())
        .limit(1)
    )
    raw = generate_url_token()
    token_row.token_hash = hash_token(f"{tenant['id']}:{raw}")
    await db.commit()

    password, phone_a = fresh_password(), _device("a")
    setup = await client.post(
        f"/api/v1/portal/setup?tenant_id={tenant['id']}",
        json={"token": raw, "password": password},
        headers=phone_a,
    )
    assert setup.status_code == 200, setup.text

    here = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=phone_a
    )
    assert here.json()["otp_required"] is False
    elsewhere = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=_device("b")
    )
    assert elsewhere.json()["otp_required"] is True


async def test_in_manual_mode_a_tenant_asking_for_a_link_is_told_to_ask_their_caretaker(
    client: AsyncClient, owner: Actor, db: AsyncSession, manual_otp_delivery
) -> None:
    tenant = await make_tenant(owner, phone_number=unique_phone())
    before = await db.scalar(select(func.count()).select_from(VerificationToken))

    known = await client.post("/api/v1/portal/magic-link", json={"phone_number": tenant["phone_number"]})
    unknown = await client.post("/api/v1/portal/magic-link", json={"phone_number": "+254700000998"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert "caretaker" in known.json()["message"]
    # Nothing was minted for a link nobody will send.
    assert await db.scalar(select(func.count()).select_from(VerificationToken)) == before
