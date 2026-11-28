"""Manual OTP delivery: a landlord or caretaker hands the code over.

While `OTP_DELIVERY=manual` RentFlow texts nothing. These tests drive the whole
handover: the owner skipping the code they could only give themselves, a
caretaker being given a code, tenants getting a link or a code, and a signer
being given a signing link and code.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileCategory
from app.models.signature import DigitalSignature
from app.models.user import User
from app.services import otp_service, signature_service
from app.services.storage_service import store_bytes
from tests.conftest import TEST_PASSWORD, Actor, fresh_password, register_owner, unique_phone
from tests.test_portfolio import make_property, make_unit
from tests.test_sprint25 import accept_portal_invite
from tests.test_tenancy import make_tenancy, make_tenant

pytestmark = pytest.mark.usefixtures("manual_otp_delivery")


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def _caretaker(
    owner: Actor, client: AsyncClient, db: AsyncSession, property_ids: list[str] | None = None
) -> tuple[Actor, str, str]:
    """A caretaker plus the email and password they sign in with."""
    from app.core.security import generate_url_token, hash_token
    from app.models.session import Invitation

    email = f"caretaker-{uuid.uuid4().hex[:8]}@example.com"
    invited = await owner.post(
        "/api/v1/team/invitations",
        json={
            "full_name": "Test Caretaker",
            "email": email,
            "phone_number": unique_phone(),
            "role": "caretaker",
            "property_ids": property_ids or [],
        },
    )
    assert invited.status_code == 201, invited.text
    invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invited.json()["id"])))
    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()

    password = fresh_password()
    accepted = await client.post("/api/v1/invitations/accept", json={"token": raw, "password": password})
    assert accepted.status_code == 200, accepted.text
    actor = Actor(client, accepted.json()["tokens"], accepted.json()["user"])
    return actor, email, password


async def test_auth_config_reports_the_delivery_mode(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/config")
    assert response.status_code == 200
    assert response.json() == {"otp_delivery": "manual"}


async def test_an_owner_signs_in_without_a_code_in_manual_mode(client: AsyncClient, owner: Actor) -> None:
    # No code could be handed to the owner by anyone above them, so there is no
    # challenge — but a new-device alert still goes out through the usual path.
    response = await _login(client, owner.user["email"], TEST_PASSWORD)
    assert response.status_code == 200, response.text
    assert response.json()["otp_required"] is False
    assert response.json()["tokens"]["access_token"]


async def test_registering_does_not_wait_for_a_phone_code_in_manual_mode(
    client: AsyncClient, owner: Actor, fake_redis
) -> None:
    assert await fake_redis.get(f"otp:phone_verification:{owner.user['id']}") is None


async def test_a_caretaker_is_asked_for_a_code_and_nothing_is_texted(
    client: AsyncClient, owner: Actor, db: AsyncSession, fake_redis
) -> None:
    caretaker, email, password = await _caretaker(owner, client, db)

    challenge = await _login(client, email, password)
    assert challenge.status_code == 200, challenge.text
    body = challenge.json()
    assert body["otp_required"] is True
    assert body["delivery"] == "manual"
    assert "landlord or caretaker" in body["message"]
    # No code was made at login: it would overwrite the one the landlord issued.
    assert await fake_redis.get(f"otp:login:{caretaker.user['id']}") is None

    # Resend has nothing to send and says where the code comes from.
    resend = await client.post(
        "/api/v1/auth/login/resend-otp", json={"challenge_token": body["challenge_token"]}
    )
    assert resend.status_code == 200
    assert "landlord or caretaker" in resend.json()["message"]
    assert await fake_redis.get(f"otp:login:{caretaker.user['id']}") is None


async def test_the_owner_issues_a_code_and_the_caretaker_signs_in_with_it(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    caretaker, email, password = await _caretaker(owner, client, db)
    challenge = await _login(client, email, password)

    issued = await owner.post(f"/api/v1/team/{caretaker.user['id']}/signin-code")
    assert issued.status_code == 200, issued.text
    handover = issued.json()
    assert handover["code"].isdigit()
    assert handover["code"] in handover["message"]
    assert handover["phone_number"].startswith("+254")
    assert handover["expires_in_seconds"] == 900

    verified = await client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge.json()["challenge_token"], "otp_code": handover["code"]},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["access_token"]

    # Single use: the same code is spent.
    again = await client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge.json()["challenge_token"], "otp_code": handover["code"]},
    )
    assert again.status_code == 401


async def test_a_new_code_cancels_the_previous_one(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    caretaker, email, password = await _caretaker(owner, client, db)
    challenge = await _login(client, email, password)
    first = (await owner.post(f"/api/v1/team/{caretaker.user['id']}/signin-code")).json()["code"]
    second = (await owner.post(f"/api/v1/team/{caretaker.user['id']}/signin-code")).json()["code"]
    assert first != second

    stale = await client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge.json()["challenge_token"], "otp_code": first},
    )
    assert stale.status_code == 401


async def test_issuing_a_code_is_limited(
    client: AsyncClient, owner: Actor, other_owner: Actor, db: AsyncSession
) -> None:
    caretaker, _, _ = await _caretaker(owner, client, db)

    # Not to yourself: the code would prove nothing.
    to_self = await owner.post(f"/api/v1/team/{owner.user['id']}/signin-code")
    assert to_self.status_code == 409

    # Not to the owner, who does not use handed-over codes.
    to_owner = await caretaker.post(f"/api/v1/team/{owner.user['id']}/signin-code")
    assert to_owner.status_code == 403  # a caretaker cannot manage users at all

    # Not across organisations, and without revealing the user exists.
    elsewhere = await other_owner.post(f"/api/v1/team/{caretaker.user['id']}/signin-code")
    assert elsewhere.status_code == 404

    unknown = await owner.post(f"/api/v1/team/{uuid.uuid4()}/signin-code")
    assert unknown.status_code == 404


async def test_a_tenant_gets_a_set_up_link_then_a_sign_in_link(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    tenant = await make_tenant(owner, full_name="Wanjiku Mwangi", phone_number=unique_phone())

    setup = await owner.post("/api/v1/portal/handover/link", json={"tenant_id": tenant["id"]})
    assert setup.status_code == 200, setup.text
    assert "/portal/setup?token=" in setup.json()["link"]
    assert setup.json()["link"] in setup.json()["message"]

    # No portal login yet, so there is no password to ask a code for.
    no_login = await owner.post("/api/v1/portal/handover/code", json={"tenant_id": tenant["id"]})
    assert no_login.status_code == 409

    await accept_portal_invite(owner, client, db, tenant["id"])

    signin = await owner.post("/api/v1/portal/handover/link", json={"tenant_id": tenant["id"]})
    assert signin.status_code == 200, signin.text
    assert "/portal/login?token=" in signin.json()["link"]

    code = await owner.post("/api/v1/portal/handover/code", json={"tenant_id": tenant["id"]})
    assert code.status_code == 200, code.text
    portal_user_id = await db.scalar(select(User.id).where(User.phone_number == code.json()["phone_number"]))
    assert portal_user_id is not None
    assert await otp_service.verify_otp("login", str(portal_user_id), code.json()["code"])


async def test_a_caretaker_can_hand_a_tenant_in_their_property_a_link(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner, phone_number=unique_phone())
    await make_tenancy(owner, tenant["id"], unit["id"])
    caretaker, _, _ = await _caretaker(owner, client, db, [prop["id"]])

    response = await caretaker.post("/api/v1/portal/handover/link", json={"tenant_id": tenant["id"]})
    assert response.status_code == 200, response.text

    # A tenant in someone else's property is out of reach, as everywhere else.
    stranger = await make_tenant(owner, phone_number=unique_phone())
    refused = await caretaker.post("/api/v1/portal/handover/link", json={"tenant_id": stranger["id"]})
    assert refused.status_code == 403


async def _signing_request(owner: Actor, db: AsyncSession) -> DigitalSignature:
    organization_id = uuid.UUID(owner.user["organization_id"])
    document_id = await store_bytes(
        db,
        data=b"%PDF-1.4 test document",
        filename="lease.pdf",
        content_type="application/pdf",
        category=FileCategory.LEASE,
        organization_id=organization_id,
    )
    await db.commit()
    sig, _ = await signature_service.create_signing_request(
        db,
        organization_id=organization_id,
        document_id=document_id,
        tenancy_id=None,
        signer_name="Signing Tenant",
        signer_phone=unique_phone(),
        signer_role="tenant",
    )
    return sig


async def test_the_signer_is_told_to_ask_for_the_code_and_nothing_is_texted(
    client: AsyncClient, owner: Actor, db: AsyncSession, fake_redis
) -> None:
    sig = await _signing_request(owner, db)
    link = (await owner.post(f"/api/v1/signatures/{sig.id}/handover/link")).json()["link"]
    token = link.rsplit("/", 1)[1]

    requested = await client.post(f"/api/v1/sign/{token}/send-otp")
    assert requested.status_code == 200
    assert requested.json()["delivery"] == "manual"
    assert await fake_redis.get(f"otp:signing:{sig.id}") is None
    await db.refresh(sig)
    assert sig.otp_sent is False


async def test_a_landlord_hands_over_a_signing_link_and_code_that_sign_the_document(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    sig = await _signing_request(owner, db)

    link_response = await owner.post(f"/api/v1/signatures/{sig.id}/handover/link")
    assert link_response.status_code == 200, link_response.text
    link = link_response.json()["link"]
    token = link.rsplit("/", 1)[1]
    assert link_response.json()["link"] in link_response.json()["message"]

    # The signer can open the page and read the document before signing.
    opened = await client.get(f"/api/v1/sign/{token}")
    assert opened.status_code == 200
    document = await client.get(f"/api/v1/sign/{token}/document")
    assert document.status_code == 200
    assert document.content.startswith(b"%PDF")
    assert document.headers["content-type"] == "application/pdf"

    code_response = await owner.post(f"/api/v1/signatures/{sig.id}/handover/code")
    assert code_response.status_code == 200, code_response.text
    code = code_response.json()["code"]
    assert code in code_response.json()["message"]

    wrong = await client.post(
        f"/api/v1/sign/{token}/sign",
        json={"otp_code": "0" * len(code), "signature_image": "data:image/png;base64,AAAA"},
    )
    assert wrong.status_code == 400

    signed = await client.post(
        f"/api/v1/sign/{token}/sign",
        json={"otp_code": code, "signature_image": "data:image/png;base64,AAAA"},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "signed"

    # Once signed there is nothing left to hand over.
    assert (await owner.post(f"/api/v1/signatures/{sig.id}/handover/code")).status_code == 409
    assert (await owner.post(f"/api/v1/signatures/{sig.id}/handover/link")).status_code == 409


async def test_a_new_signing_link_replaces_the_old_one(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    sig = await _signing_request(owner, db)
    old = (await owner.post(f"/api/v1/signatures/{sig.id}/handover/link")).json()["link"].rsplit("/", 1)[1]
    new = (await owner.post(f"/api/v1/signatures/{sig.id}/handover/link")).json()["link"].rsplit("/", 1)[1]
    assert old != new
    assert (await client.get(f"/api/v1/sign/{old}")).status_code == 404
    assert (await client.get(f"/api/v1/sign/{new}")).status_code == 200


async def test_signing_handover_is_scoped_to_the_organisation(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    sig = await _signing_request(owner, db)
    rival = await register_owner(client, organization_name="Rival Holdings")
    assert (await rival.post(f"/api/v1/signatures/{sig.id}/handover/link")).status_code == 404
    assert (await rival.post(f"/api/v1/signatures/{sig.id}/handover/code")).status_code == 404
