"""Sprint 25 (Phase 5): security, privacy & compliance closeout.

Covers virus scanning on upload (US-105), the tenant data subject access and
erasure workflow (US-106), co-tenant support (US-107), WebAuthn/passkey login
(US-108), and the caretaker visitor log (US-109).

WebAuthn is exercised with a real, from-scratch software authenticator
(`SoftAuthenticator` below) rather than mocked at the verification layer — it
builds a genuine COSE public key, a spec-shaped `authenticatorData` structure,
and a real ECDSA signature over the assertion, so the tests prove the actual
cryptographic round trip works, not just that the code path was called.
"""

import base64
import hashlib
import json
import secrets
import uuid
from datetime import date, timedelta

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.models.billing import Payment
from app.models.file import ScanStatus, StoredFile, UploadStatus
from app.models.privacy import DataRequest, DataRequestType
from app.models.tenant import Tenancy, Tenant
from app.models.webauthn import WebauthnCredential
from app.services import file_service, lease_service, virus_scan_service
from app.services.virus_scan_service import ScanOutcome
from tests.conftest import Actor, fresh_password, unique_phone
from tests.test_operations import upload_photo
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftAuthenticator:
    """A minimal WebAuthn authenticator: one ES256 keypair, attestation format
    "none". Enough to drive a real registration and authentication ceremony
    against `webauthn_service` without a browser."""

    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(32)
        self.sign_count = 0

    def _cose_public_key(self) -> bytes:
        numbers = self.private_key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def create(self, *, challenge_b64url: str, rp_id: str, origin: str) -> dict:
        client_data = json.dumps(
            {"type": "webauthn.create", "challenge": challenge_b64url, "origin": origin}
        ).encode()
        rp_id_hash = hashlib.sha256(rp_id.encode()).digest()
        flags = 0b01000001  # UP + AT
        auth_data = (
            rp_id_hash
            + bytes([flags])
            + self.sign_count.to_bytes(4, "big")
            + b"\x00" * 16  # aaguid
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_public_key()
        )
        attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": _b64url(self.credential_id),
            "rawId": _b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64url(client_data),
                "attestationObject": _b64url(attestation_object),
            },
        }

    def get(self, *, challenge_b64url: str, rp_id: str, origin: str) -> dict:
        self.sign_count += 1
        client_data = json.dumps(
            {"type": "webauthn.get", "challenge": challenge_b64url, "origin": origin}
        ).encode()
        rp_id_hash = hashlib.sha256(rp_id.encode()).digest()
        auth_data = rp_id_hash + bytes([0b00000001]) + self.sign_count.to_bytes(4, "big")
        client_data_hash = hashlib.sha256(client_data).digest()
        signature = self.private_key.sign(auth_data + client_data_hash, ec.ECDSA(hashes.SHA256()))
        return {
            "id": _b64url(self.credential_id),
            "rawId": _b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64url(client_data),
                "authenticatorData": _b64url(auth_data),
                "signature": _b64url(signature),
                "userHandle": None,
            },
        }


# ------------------------------------------------------------------ virus scanning


async def test_upload_is_skipped_without_clamav_configured(owner: Actor, client: AsyncClient, db) -> None:
    """No CLAMAV_HOST in this test environment — uploads still succeed, marked
    SKIPPED rather than blocked (the same degrade-gracefully treatment every
    other optional integration gets)."""
    file_id = await upload_photo(owner, client)
    record = await db.get(StoredFile, uuid.UUID(file_id))
    assert record.status == UploadStatus.UPLOADED
    assert record.scan_status == ScanStatus.SKIPPED


async def test_infected_upload_is_rejected_and_never_confirmed(
    owner: Actor, client: AsyncClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        file_service.virus_scan_service,
        "scan_bytes",
        lambda data: ScanOutcome(status=ScanStatus.INFECTED, detail="Eicar-Test-Signature"),
    )
    ticket = (
        await owner.post(
            "/api/v1/files/upload-url",
            json={
                "filename": "malware.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 128,
                "category": "meter_reading",
            },
        )
    ).json()
    await client.put(ticket["upload_url"], content=b"x" * 128)

    confirmed = await owner.post(f"/api/v1/files/{ticket['file_id']}/confirm", json={})
    assert confirmed.status_code == 422, confirmed.text

    record = await db.get(StoredFile, uuid.UUID(ticket["file_id"]))
    assert record.status == UploadStatus.FAILED
    assert record.scan_status == ScanStatus.INFECTED


async def test_clean_upload_records_the_verdict(
    owner: Actor, client: AsyncClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        file_service.virus_scan_service,
        "scan_bytes",
        lambda data: ScanOutcome(status=ScanStatus.CLEAN),
    )
    file_id = await upload_photo(owner, client)
    record = await db.get(StoredFile, uuid.UUID(file_id))
    assert record.status == UploadStatus.UPLOADED
    assert record.scan_status == ScanStatus.CLEAN


async def test_scan_failure_does_not_block_the_upload(
    owner: Actor, client: AsyncClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ClamAV outage is defence-in-depth going dark, not a reason to stop
    every upload in the app."""
    monkeypatch.setattr(
        file_service.virus_scan_service,
        "scan_bytes",
        lambda data: ScanOutcome(status=ScanStatus.FAILED, detail="connection refused"),
    )
    file_id = await upload_photo(owner, client)
    record = await db.get(StoredFile, uuid.UUID(file_id))
    assert record.status == UploadStatus.UPLOADED
    assert record.scan_status == ScanStatus.FAILED


def test_scan_bytes_skips_when_not_configured() -> None:
    assert settings.clamav_configured is False
    outcome = virus_scan_service.scan_bytes(b"anything")
    assert outcome.status == ScanStatus.SKIPPED


# ------------------------------------------------------------------- visitor log


async def test_caretaker_logs_and_checks_out_a_visitor(owner: Actor, db) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])

    logged = await owner.post(
        "/api/v1/visitor-logs",
        json={"unit_id": unit["id"], "visitor_name": "John Kamau", "purpose": "Plumber"},
    )
    assert logged.status_code == 201, logged.text
    entry = logged.json()
    assert entry["visitor_name"] == "John Kamau"
    assert entry["checked_out_at"] is None
    assert entry["unit_number"] == unit["unit_number"]

    listed = await owner.get("/api/v1/visitor-logs", params={"open_only": True})
    assert entry["id"] in {row["id"] for row in listed.json()}

    checked_out = await owner.post(f"/api/v1/visitor-logs/{entry['id']}/check-out")
    assert checked_out.status_code == 200, checked_out.text
    assert checked_out.json()["checked_out_at"] is not None

    duplicate = await owner.post(f"/api/v1/visitor-logs/{entry['id']}/check-out")
    assert duplicate.status_code == 409


async def test_visitor_log_is_scoped_to_the_caretakers_property(
    owner: Actor, client: AsyncClient, db
) -> None:
    import uuid as uuid_module

    from app.core.security import generate_url_token, hash_token
    from app.models.session import Invitation

    mine = await make_property(owner, name="Assigned block")
    theirs = await make_property(owner, name="Other block")
    mine_unit = await make_unit(owner, mine["id"], unit_number="A1")
    theirs_unit = await make_unit(owner, theirs["id"], unit_number="B1")

    await owner.post("/api/v1/visitor-logs", json={"unit_id": mine_unit["id"], "visitor_name": "Visitor A"})
    await owner.post("/api/v1/visitor-logs", json={"unit_id": theirs_unit["id"], "visitor_name": "Visitor B"})

    invited = await owner.post(
        "/api/v1/team/invitations",
        json={
            "full_name": "Scoped Caretaker",
            "phone_number": unique_phone(),
            "role": "caretaker",
            "property_ids": [mine["id"]],
        },
    )
    assert invited.status_code == 201, invited.text
    invitation = await db.scalar(
        select(Invitation).where(Invitation.id == uuid_module.UUID(invited.json()["id"]))
    )
    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()

    accepted = await client.post(
        "/api/v1/invitations/accept", json={"token": raw, "password": fresh_password()}
    )
    assert accepted.status_code == 200, accepted.text
    caretaker = Actor(client, accepted.json()["tokens"], accepted.json()["user"])

    visible = await caretaker.get("/api/v1/visitor-logs")
    assert {row["visitor_name"] for row in visible.json()} == {"Visitor A"}


async def accept_portal_invite(owner: Actor, client: AsyncClient, db, tenant_id: str) -> Actor:
    """Invite a tenant to the portal and accept on their behalf, exactly like
    `tests.test_operations.setup_portal` but against an already-created tenant."""
    from app.core.security import generate_url_token, hash_token
    from app.models.session import TokenPurpose, VerificationToken

    invited = await owner.post("/api/v1/portal/invite", json={"tenant_id": tenant_id})
    assert invited.status_code == 200, invited.text

    token_row = await db.scalar(
        select(VerificationToken)
        .where(VerificationToken.purpose == TokenPurpose.TENANT_PORTAL_INVITE)
        .order_by(VerificationToken.created_at.desc())
        .limit(1)
    )
    raw = generate_url_token()
    token_row.token_hash = hash_token(f"{tenant_id}:{raw}")
    await db.commit()

    accepted = await client.post(
        f"/api/v1/portal/setup?tenant_id={tenant_id}",
        json={"token": raw, "password": fresh_password()},
    )
    assert accepted.status_code == 200, accepted.text
    return Actor(client, accepted.json()["tokens"], {"id": accepted.json()["tenant_id"]})


# --------------------------------------------------------------------- co-tenants


async def test_add_list_and_remove_a_co_tenant(owner: Actor, db) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    primary = await make_tenant(owner, full_name="Primary Tenant", phone_number=unique_phone())
    tenancy = await make_tenancy(owner, primary["id"], unit["id"])
    roommate = await make_tenant(owner, full_name="Roommate Tenant", phone_number=unique_phone())

    # The primary tenant can't be added again as their own co-tenant.
    rejected = await owner.post(
        f"/api/v1/tenancies/{tenancy['id']}/co-tenants", json={"tenant_id": primary["id"]}
    )
    assert rejected.status_code == 400

    added = await owner.post(
        f"/api/v1/tenancies/{tenancy['id']}/co-tenants", json={"tenant_id": roommate["id"]}
    )
    assert added.status_code == 201, added.text
    assert added.json()["tenant_name"] == "Roommate Tenant"

    duplicate = await owner.post(
        f"/api/v1/tenancies/{tenancy['id']}/co-tenants", json={"tenant_id": roommate["id"]}
    )
    assert duplicate.status_code == 409

    listed = await owner.get(f"/api/v1/tenancies/{tenancy['id']}/co-tenants")
    assert [row["tenant_id"] for row in listed.json()] == [roommate["id"]]

    removed = await owner.delete(f"/api/v1/tenancies/{tenancy['id']}/co-tenants/{roommate['id']}")
    assert removed.status_code == 204

    after = await owner.get(f"/api/v1/tenancies/{tenancy['id']}/co-tenants")
    assert after.json() == []

    # Financial shape is untouched — the tenancy still has exactly one tenant_id.
    row = await db.get(Tenancy, uuid.UUID(tenancy["id"]))
    assert str(row.tenant_id) == primary["id"]


async def test_promoting_a_co_tenant_swaps_the_primary_tenant(owner: Actor, db) -> None:
    """The partial-turnover case (US-107): the current primary is moving out,
    a co-tenant is staying and becomes responsible for the tenancy going
    forward. History (past invoices/payments) is untouched either way since
    they key off `tenancy_id`, never `tenant_id`."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    leaving = await make_tenant(owner, full_name="Leaving Tenant", phone_number=unique_phone())
    tenancy = await make_tenancy(owner, leaving["id"], unit["id"])
    staying = await make_tenant(owner, full_name="Staying Tenant", phone_number=unique_phone())
    await owner.post(f"/api/v1/tenancies/{tenancy['id']}/co-tenants", json={"tenant_id": staying["id"]})

    invoice = (await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancy["id"]})).json()

    # Promoting someone who isn't a co-tenant is refused.
    stranger = await make_tenant(owner, full_name="Stranger", phone_number=unique_phone())
    rejected = await owner.post(f"/api/v1/tenancies/{tenancy['id']}/co-tenants/{stranger['id']}/promote")
    assert rejected.status_code == 404

    promoted = await owner.post(f"/api/v1/tenancies/{tenancy['id']}/co-tenants/{staying['id']}/promote")
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["tenant_id"] == staying["id"]

    # The old primary is dropped entirely — not left behind as a co-tenant.
    co_tenants = await owner.get(f"/api/v1/tenancies/{tenancy['id']}/co-tenants")
    assert co_tenants.json() == []

    row = await db.get(Tenancy, uuid.UUID(tenancy["id"]))
    assert str(row.tenant_id) == staying["id"]

    # The invoice raised before the swap still belongs to the same tenancy.
    still_listed = await owner.get("/api/v1/invoices", params={"tenancy_id": tenancy["id"]})
    assert invoice["id"] in {row["id"] for row in still_listed.json()}


async def test_co_tenant_sees_the_shared_tenancy_in_their_portal(
    owner: Actor, client: AsyncClient, db
) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    primary = await make_tenant(owner, full_name="Primary Tenant", phone_number=unique_phone())
    tenancy = await make_tenancy(owner, primary["id"], unit["id"])
    roommate = await make_tenant(owner, full_name="Roommate Tenant", phone_number=unique_phone())
    await owner.post(f"/api/v1/tenancies/{tenancy['id']}/co-tenants", json={"tenant_id": roommate["id"]})

    roommate_actor = await accept_portal_invite(owner, client, db, roommate["id"])

    home = await roommate_actor.get("/api/v1/portal/home")
    assert home.status_code == 200, home.text
    assert home.json()["tenancy_id"] == tenancy["id"]


def test_lease_variables_include_co_tenant_names_when_present() -> None:
    from app.models.organization import Organization
    from app.models.property import Property, Unit
    from app.models.tenant import Tenancy as TenancyModel

    org = Organization(name="Acacia", slug="acacia")
    tenant = Tenant(full_name="Amina Njeri", phone_number="+254711111111", reference_code="TNT-1")
    tenancy = TenancyModel(
        reference_code="TCY-1",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        monthly_rent=25000,
        deposit_amount=25000,
        billing_day=1,
        notice_period_days=30,
    )
    unit = Unit(unit_number="A1")
    property_record = Property(name="Riverside", address="Nairobi")

    without = lease_service.build_variables(
        organization=org, tenant=tenant, tenancy=tenancy, unit=unit, property_record=property_record
    )
    assert without["co_tenant_names"] == ""

    with_co_tenants = lease_service.build_variables(
        organization=org,
        tenant=tenant,
        tenancy=tenancy,
        unit=unit,
        property_record=property_record,
        co_tenant_names="John Doe, Jane Smith",
    )
    assert with_co_tenants["co_tenant_names"] == "John Doe, Jane Smith"
    rendered = lease_service.pdf_service.substitute(lease_service.STARTER_TEMPLATE_HTML, with_co_tenants)
    assert "John Doe, Jane Smith" in rendered


async def accept_caretaker_invite(owner: Actor, client: AsyncClient, db, property_ids: list[str]) -> Actor:
    import uuid as uuid_module

    from app.core.security import generate_url_token, hash_token
    from app.models.session import Invitation

    invited = await owner.post(
        "/api/v1/team/invitations",
        json={
            "full_name": "Test Caretaker",
            "phone_number": unique_phone(),
            "role": "caretaker",
            "property_ids": property_ids,
        },
    )
    assert invited.status_code == 201, invited.text
    invitation = await db.scalar(
        select(Invitation).where(Invitation.id == uuid_module.UUID(invited.json()["id"]))
    )
    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()

    accepted = await client.post(
        "/api/v1/invitations/accept", json={"token": raw, "password": fresh_password()}
    )
    assert accepted.status_code == 200, accepted.text
    return Actor(client, accepted.json()["tokens"], accepted.json()["user"])


async def test_caretaker_is_denied_data_privacy_and_co_tenant_management(
    owner: Actor, client: AsyncClient, db
) -> None:
    """A caretaker records field operations — they don't get to erase a
    tenant's data or restructure who's on a tenancy."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner, full_name="Protected Tenant", phone_number=unique_phone())
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])
    other = await make_tenant(owner, full_name="Other Tenant", phone_number=unique_phone())

    caretaker = await accept_caretaker_invite(owner, client, db, [prop["id"]])

    export_denied = await caretaker.post(f"/api/v1/privacy/tenants/{tenant['id']}/export")
    assert export_denied.status_code == 403

    erase_denied = await caretaker.post(f"/api/v1/privacy/tenants/{tenant['id']}/erase")
    assert erase_denied.status_code == 403

    add_co_tenant_denied = await caretaker.post(
        f"/api/v1/tenancies/{tenancy['id']}/co-tenants", json={"tenant_id": other["id"]}
    )
    assert add_co_tenant_denied.status_code == 403


# ------------------------------------------------------------------------- DSAR


async def test_operator_export_generates_a_downloadable_bundle(owner: Actor, db) -> None:
    from app.models.file import StoredFile
    from app.services import storage_service

    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner, full_name="Export Me", phone_number=unique_phone())
    # `generate_lease=True` by default, so a lease PDF is already filed against
    # this tenancy — the export bundle should list it (US-106's "documents").
    await make_tenancy(owner, tenant["id"], unit["id"])

    response = await owner.post(f"/api/v1/privacy/tenants/{tenant['id']}/export")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_type"] == "export"
    assert body["status"] == "completed"
    assert body["export_url"]

    stored = await db.scalar(select(DataRequest).where(DataRequest.tenant_id == uuid.UUID(tenant["id"])))
    assert stored.request_type == DataRequestType.EXPORT
    assert stored.export_file_id is not None

    export_file = await db.get(StoredFile, stored.export_file_id)
    bundle = json.loads(storage_service.get_storage().read(export_file.storage_key))
    assert bundle["tenancies"][0]["reference_code"]
    assert any(doc["category"] == "lease" for doc in bundle["documents"])


async def test_erasure_redacts_pii_but_keeps_financial_records(owner: Actor, client: AsyncClient, db) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner, full_name="Erase Me", phone_number=unique_phone())
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], monthly_rent="5000.00")
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancy["id"]})

    paid = await owner.post(
        "/api/v1/payments",
        json={
            "tenancy_id": tenancy["id"],
            "amount": "5000.00",
            "payment_date": date.today().isoformat(),
            "method": "cash",
        },
    )
    assert paid.status_code == 201, paid.text

    erased = await owner.post(f"/api/v1/privacy/tenants/{tenant['id']}/erase")
    assert erased.status_code == 200, erased.text
    assert erased.json()["request_type"] == "erasure"

    row = await db.get(Tenant, uuid.UUID(tenant["id"]))
    assert row.full_name == "Erased tenant"
    assert row.national_id is None
    assert row.erased_at is not None
    assert row.is_archived is True

    # Financial records are untouched.
    tenancy_row = await db.get(Tenancy, uuid.UUID(tenancy["id"]))
    assert tenancy_row is not None
    assert str(tenancy_row.tenant_id) == tenant["id"]
    payments = list(await db.scalars(select(Payment).where(Payment.tenancy_id == uuid.UUID(tenancy["id"]))))
    assert len(payments) == 1

    # Erasing twice is refused rather than silently re-processed.
    again = await owner.post(f"/api/v1/privacy/tenants/{tenant['id']}/erase")
    assert again.status_code == 409


async def test_tenant_self_service_export_and_erasure(owner: Actor, client: AsyncClient, db) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner, full_name="Self Service", phone_number=unique_phone())
    await make_tenancy(owner, tenant["id"], unit["id"])

    tenant_actor = await accept_portal_invite(owner, client, db, tenant["id"])

    exported = await tenant_actor.post("/api/v1/portal/data-requests/export")
    assert exported.status_code == 200, exported.text
    assert exported.json()["download_url"]

    erased = await tenant_actor.post("/api/v1/portal/data-requests/erase")
    assert erased.status_code == 200, erased.text


async def test_staff_can_export_their_own_data(owner: Actor) -> None:
    response = await owner.post("/api/v1/auth/me/data-export")
    assert response.status_code == 200, response.text
    assert response.json()["download_url"]


# ----------------------------------------------------------------------- webauthn


async def test_login_offers_no_passkey_option_with_none_registered(client: AsyncClient) -> None:
    from tests.conftest import TEST_PASSWORD, register_owner

    owner = await register_owner(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": owner.user["email"], "password": TEST_PASSWORD},
    )
    assert login.status_code == 200, login.text
    assert login.json()["webauthn_options"] is None


async def test_full_passkey_registration_and_login_ceremony(owner: Actor, client: AsyncClient) -> None:
    from tests.conftest import TEST_PASSWORD

    authenticator = SoftAuthenticator()

    options_response = await owner.post("/api/v1/auth/webauthn/register/options")
    assert options_response.status_code == 200, options_response.text
    options = json.loads(options_response.json()["options"])

    credential = authenticator.create(
        challenge_b64url=options["challenge"],
        rp_id=settings.WEBAUTHN_RP_ID,
        origin=settings.WEBAUTHN_ORIGIN,
    )
    verified = await owner.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"credential": credential, "device_name": "Test phone"},
    )
    assert verified.status_code == 200, verified.text
    credential_id = verified.json()["id"]

    listed = await owner.get("/api/v1/auth/webauthn/credentials")
    assert [row["id"] for row in listed.json()] == [credential_id]

    # Registering with a garbage credential is rejected cleanly.
    bad_options = await owner.post("/api/v1/auth/webauthn/register/options")
    bad = await owner.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"credential": {"id": "nope", "rawId": "nope", "type": "public-key", "response": {}}},
    )
    assert bad.status_code == 400
    del bad_options

    # Step 1 of login now offers a passkey.
    login = await client.post(
        "/api/v1/auth/login", json={"email": owner.user["email"], "password": TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text
    challenge = login.json()
    assert challenge["webauthn_options"] is not None
    login_options = json.loads(challenge["webauthn_options"])

    assertion = authenticator.get(
        challenge_b64url=login_options["challenge"],
        rp_id=settings.WEBAUTHN_RP_ID,
        origin=settings.WEBAUTHN_ORIGIN,
    )
    verified_login = await client.post(
        "/api/v1/auth/login/verify-webauthn",
        json={"challenge_token": challenge["challenge_token"], "credential": assertion},
    )
    assert verified_login.status_code == 200, verified_login.text
    assert "access_token" in verified_login.json()

    # The same challenge cannot be replayed a second time.
    replayed = await client.post(
        "/api/v1/auth/login/verify-webauthn",
        json={"challenge_token": challenge["challenge_token"], "credential": assertion},
    )
    assert replayed.status_code == 401

    # Removing it clears the option from the next login.
    removed = await owner.delete(f"/api/v1/auth/webauthn/credentials/{credential_id}")
    assert removed.status_code == 200, removed.text
    login_after = await client.post(
        "/api/v1/auth/login", json={"email": owner.user["email"], "password": TEST_PASSWORD}
    )
    assert login_after.json()["webauthn_options"] is None


async def test_login_webauthn_rejects_a_garbage_assertion(owner: Actor, client: AsyncClient, db) -> None:
    from tests.conftest import TEST_PASSWORD

    # Seed a credential directly — the registration ceremony itself is covered
    # by the full end-to-end test above.
    db.add(
        WebauthnCredential(
            organization_id=uuid.UUID(owner.user["organization_id"]),
            user_id=uuid.UUID(owner.user["id"]),
            credential_id=_b64url(secrets.token_bytes(32)),
            public_key=_b64url(b"not-a-real-key"),
            device_name="Seeded",
        )
    )
    await db.commit()

    login = await client.post(
        "/api/v1/auth/login", json={"email": owner.user["email"], "password": TEST_PASSWORD}
    )
    challenge = login.json()
    assert challenge["webauthn_options"] is not None

    rejected = await client.post(
        "/api/v1/auth/login/verify-webauthn",
        json={
            "challenge_token": challenge["challenge_token"],
            "credential": {"id": "unknown-credential", "rawId": "x", "type": "public-key", "response": {}},
        },
    )
    assert rejected.status_code == 401
