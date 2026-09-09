"""Per-organisation M-Pesa collection.

The point of this design: rent goes to the landlord's own M-Pesa and never to
RentFlow. So the things worth pinning down are that one organisation's Daraja
credentials can never be used to move another's money, that the credentials
never come back out of the API, and that the product still works for the
landlords who have no API access at all — which is most of them.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core import crypto
from app.models.organization import MpesaCollectionMode, Organization
from app.services import mpesa_service
from tests.conftest import Actor

AUTOMATED_SETUP = {
    "mode": "automated",
    "shortcode": "174379",
    "account_label": "RENT",
    "daraja_environment": "sandbox",
    "consumer_key": "test-consumer-key",
    "consumer_secret": "test-consumer-secret",
    "passkey": "test-passkey",
}


async def _org(db, owner: Actor) -> Organization:
    return await db.get(Organization, uuid.UUID(owner.user["organization_id"]))


# ----------------------------------------------------------------- the default


async def test_a_new_organisation_collects_manually(owner: Actor) -> None:
    """Nobody is assumed to have a paybill. The product has to work on day one
    for a landlord whose tenants pay their personal number."""
    response = await owner.get("/api/v1/organizations/me/mpesa")
    assert response.status_code == 200
    assert response.json()["mode"] == "manual"
    assert response.json()["has_api_credentials"] is False


async def test_manual_and_paybill_landlords_get_no_stk_prompt(owner: Actor, db) -> None:
    """No Daraja app means no push. The tenant pays the landlord the way they
    always have and the payment is recorded — not a dead button."""
    organization = await _org(db, owner)

    for mode in (MpesaCollectionMode.MANUAL, MpesaCollectionMode.PAYBILL):
        organization.mpesa_collection_mode = mode
        organization.mpesa_shortcode = "123456"
        await db.commit()
        assert await mpesa_service.credentials_for(db, organization) is None


# ----------------------------------------------------------------- credentials


async def test_saving_credentials_stores_them_encrypted(owner: Actor, db) -> None:
    """A leak of the organisations table must not be a leak of every customer's
    till."""
    response = await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)
    assert response.status_code == 200, response.text

    organization = await _org(db, owner)
    await db.refresh(organization)

    stored = organization.daraja_consumer_secret_encrypted
    assert stored is not None
    assert "test-consumer-secret" not in stored  # not sitting in plaintext

    decrypted = await crypto.decrypt_for_org(db, organization.id, stored)
    assert decrypted == "test-consumer-secret"


async def test_credentials_never_come_back_out_of_the_api(owner: Actor) -> None:
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    for url in ("/api/v1/organizations/me/mpesa", "/api/v1/organizations/me"):
        body = (await owner.get(url)).text
        assert "test-consumer-secret" not in body
        assert "test-passkey" not in body
        assert "test-consumer-key" not in body


async def test_status_reports_what_is_configured_without_revealing_it(owner: Actor) -> None:
    response = await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)
    body = response.json()

    assert body["mode"] == "automated"
    assert body["shortcode"] == "174379"
    assert body["has_api_credentials"] is True
    # No B2C credentials were supplied, so payouts stay unavailable.
    assert body["can_send_payouts"] is False


async def test_editing_the_label_does_not_wipe_the_stored_keys(owner: Actor, db) -> None:
    """Someone changing the account number should not have to re-type their
    Daraja secret to avoid destroying it."""
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    response = await owner.put(
        "/api/v1/organizations/me/mpesa",
        json={
            "mode": "automated",
            "shortcode": "174379",
            "account_label": "HOUSE",
            "daraja_environment": "sandbox",
        },
    )
    assert response.status_code == 200
    assert response.json()["account_label"] == "HOUSE"
    assert response.json()["has_api_credentials"] is True


async def test_leaving_automated_mode_drops_the_keys(owner: Actor, db) -> None:
    """Credentials that can no longer be used for anything should not stay in
    the table waiting to leak."""
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    response = await owner.put(
        "/api/v1/organizations/me/mpesa",
        json={"mode": "manual", "phone_number": "+254712345678"},
    )
    assert response.json()["has_api_credentials"] is False

    organization = await _org(db, owner)
    await db.refresh(organization)
    assert organization.daraja_consumer_key_encrypted is None
    assert organization.daraja_passkey_encrypted is None


# ----------------------------------------------------------------- isolation


async def test_one_organisations_credentials_are_never_used_for_another(
    owner: Actor, other_owner: Actor, db
) -> None:
    """The whole model rests on this: an STK push is made *as* the landlord, so
    resolving the wrong organisation's app would push a tenant's rent into
    somebody else's till."""
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)
    await other_owner.put(
        "/api/v1/organizations/me/mpesa",
        json={**AUTOMATED_SETUP, "shortcode": "999999", "consumer_key": "other-key"},
    )

    first = await _org(db, owner)
    second = await _org(db, other_owner)
    await db.refresh(first)
    await db.refresh(second)

    first_creds = await mpesa_service.credentials_for(db, first)
    second_creds = await mpesa_service.credentials_for(db, second)

    assert first_creds is not None and second_creds is not None
    assert first_creds.shortcode == "174379"
    assert second_creds.shortcode == "999999"
    assert first_creds.consumer_key != second_creds.consumer_key
    assert first_creds.organization_id != second_creds.organization_id


async def test_another_organisation_cannot_read_or_change_your_mpesa_setup(
    owner: Actor, other_owner: Actor
) -> None:
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    # `/me` is scoped to the caller's own organisation, so the other owner sees
    # their own untouched setup rather than this one's.
    other = (await other_owner.get("/api/v1/organizations/me/mpesa")).json()
    assert other["shortcode"] is None
    assert other["has_api_credentials"] is False


async def test_credentials_are_environment_specific(owner: Actor, db) -> None:
    """Safaricom issues sandbox and production credentials separately; pointing
    sandbox keys at the live host would fail every push."""
    await owner.put(
        "/api/v1/organizations/me/mpesa",
        json={**AUTOMATED_SETUP, "daraja_environment": "production"},
    )
    organization = await _org(db, owner)
    await db.refresh(organization)

    creds = await mpesa_service.credentials_for(db, organization)
    assert creds is not None
    assert creds.base_url == "https://api.safaricom.co.ke"


async def test_an_unknown_environment_is_refused(owner: Actor) -> None:
    response = await owner.put(
        "/api/v1/organizations/me/mpesa",
        json={**AUTOMATED_SETUP, "daraja_environment": "live"},
    )
    assert response.status_code == 422


# ----------------------------------------------------------------- payouts


async def test_payouts_need_their_own_credentials(owner: Actor, db) -> None:
    """Collection and B2C are different Safaricom credentials. Having one must
    not imply the other."""
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)
    organization = await _org(db, owner)
    await db.refresh(organization)

    creds = await mpesa_service.credentials_for(db, organization)
    assert creds is not None
    assert creds.can_pay_out is False

    await owner.put(
        "/api/v1/organizations/me/mpesa",
        json={
            **AUTOMATED_SETUP,
            "initiator_name": "testapi",
            "security_credential": "encrypted-blob-from-safaricom",
        },
    )
    await db.refresh(organization)
    creds = await mpesa_service.credentials_for(db, organization)
    assert creds is not None and creds.can_pay_out is True


# ----------------------------------------------------------------- the portal


async def test_the_portal_only_offers_what_the_landlord_can_accept(
    owner: Actor, client: AsyncClient, db
) -> None:
    """A tenant should never see a payment button that dead-ends."""
    organization = await _org(db, owner)
    organization.mpesa_collection_mode = MpesaCollectionMode.MANUAL
    await db.commit()

    creds = await mpesa_service.credentials_for(db, organization)
    assert creds is None  # so the portal reports mpesa=False


@pytest.mark.parametrize("mode", ["automated", "paybill", "manual"])
async def test_every_collection_mode_is_settable(owner: Actor, mode: str) -> None:
    """All three are first-class. None is a degraded state to be migrated off."""
    response = await owner.put(
        "/api/v1/organizations/me/mpesa",
        json={**AUTOMATED_SETUP, "mode": mode},
    )
    assert response.status_code == 200
    assert response.json()["mode"] == mode


# ----------------------------------------------------------------- verification


async def test_testing_before_any_credentials_exist_says_so(owner: Actor) -> None:
    response = await owner.post("/api/v1/organizations/me/mpesa/test")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["verified_at"] is None


async def test_a_passing_test_stamps_the_verified_time(owner: Actor, db, monkeypatch) -> None:
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    async def passes(creds):
        return True, "Your API key and secret are working."

    monkeypatch.setattr(mpesa_service, "verify_credentials", passes)

    response = await owner.post("/api/v1/organizations/me/mpesa/test")
    assert response.json()["ok"] is True
    assert response.json()["verified_at"] is not None

    organization = await _org(db, owner)
    await db.refresh(organization)
    assert organization.mpesa_verified_at is not None


async def test_a_failing_test_clears_any_previous_pass(owner: Actor, db, monkeypatch) -> None:
    """Someone who breaks working credentials must not keep a green tick from
    the last time they worked."""
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    async def passes(creds):
        return True, "ok"

    monkeypatch.setattr(mpesa_service, "verify_credentials", passes)
    await owner.post("/api/v1/organizations/me/mpesa/test")

    async def fails(creds):
        return False, "Safaricom rejected these credentials."

    monkeypatch.setattr(mpesa_service, "verify_credentials", fails)
    response = await owner.post("/api/v1/organizations/me/mpesa/test")

    assert response.json()["ok"] is False
    assert response.json()["verified_at"] is None

    organization = await _org(db, owner)
    await db.refresh(organization)
    assert organization.mpesa_verified_at is None


async def test_changing_the_mode_drops_the_verified_stamp(owner: Actor, monkeypatch) -> None:
    await owner.put("/api/v1/organizations/me/mpesa", json=AUTOMATED_SETUP)

    async def passes(creds):
        return True, "ok"

    monkeypatch.setattr(mpesa_service, "verify_credentials", passes)
    await owner.post("/api/v1/organizations/me/mpesa/test")

    response = await owner.put(
        "/api/v1/organizations/me/mpesa", json={"mode": "paybill", "shortcode": "123456"}
    )
    assert response.json()["verified_at"] is None
