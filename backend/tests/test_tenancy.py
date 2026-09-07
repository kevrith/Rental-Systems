"""Sprint 3: caretaker invitations, tenant profiles, tenancies, lease generation."""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.session import Invitation
from tests.conftest import TEST_PASSWORD, Actor, fresh_password, unique_phone
from tests.test_portfolio import make_property, make_unit

PASSWORD = TEST_PASSWORD


async def make_tenant(actor: Actor, **overrides) -> dict:
    payload = {
        "full_name": "Peter Otieno",
        "phone_number": unique_phone(),
        # Unique because accepting a portal invitation turns this into a `users`
        # row, and user emails are unique across the whole platform.
        "email": f"peter-{uuid.uuid4().hex[:8]}@example.com",
        "national_id": f"ID{uuid.uuid4().hex[:8].upper()}",
        "employer_name": "Safaricom",
        "occupation": "Engineer",
        "emergency_contact_name": "Mary Otieno",
        "emergency_contact_phone": unique_phone(),
        "emergency_contact_relationship": "Sister",
    }
    payload.update(overrides)
    response = await actor.post("/api/v1/tenants", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def make_tenancy(actor: Actor, tenant_id: str, unit_id: str, **overrides) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=365)).isoformat(),
        "monthly_rent": "25000.00",
        "deposit_amount": "25000.00",
        "billing_day": 1,
        "payment_method": "mpesa",
    }
    payload.update(overrides)
    response = await actor.post("/api/v1/tenancies", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------------ tenants


async def test_tenant_gets_a_searchable_reference(owner: Actor) -> None:
    tenant = await make_tenant(owner, full_name="Peter Otieno")

    assert tenant["reference_code"].startswith("TNT-")

    found = await owner.get("/api/v1/tenants", params={"search": "Otieno"})
    assert [t["full_name"] for t in found.json()] == ["Peter Otieno"]


async def test_tenant_is_searchable_by_phone_and_id(owner: Actor) -> None:
    tenant = await make_tenant(owner)

    by_phone = await owner.get("/api/v1/tenants", params={"search": tenant["phone_number"][-6:]})
    assert len(by_phone.json()) == 1

    # National ID is encrypted at rest (Sprint 26A) and can only be matched by
    # its plaintext last-4 hint, not a full-value substring search.
    by_id = await owner.get("/api/v1/tenants", params={"search": tenant["national_id"][-4:]})
    assert len(by_id.json()) == 1


async def test_duplicate_phone_raises_a_warning_with_the_existing_tenant(owner: Actor) -> None:
    existing = await make_tenant(owner, full_name="Peter Otieno")

    response = await owner.post(
        "/api/v1/tenants",
        json={"full_name": "Someone Else", "phone_number": existing["phone_number"]},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["duplicates"][0]["field"] == "phone_number"
    assert detail["duplicates"][0]["existing_tenant_name"] == "Peter Otieno"


async def test_duplicate_national_id_can_be_acknowledged(owner: Actor) -> None:
    """Two people can legitimately share a household — an ID clash is a warning,
    a phone clash is not (the phone is the identity key)."""
    existing = await make_tenant(owner)

    response = await owner.post(
        "/api/v1/tenants",
        json={
            "full_name": "Jane Otieno",
            "phone_number": unique_phone(),
            "national_id": existing["national_id"],
            "acknowledge_duplicate": True,
        },
    )
    assert response.status_code == 201


async def test_tenant_export_produces_csv(owner: Actor) -> None:
    await make_tenant(owner, full_name="Peter Otieno")

    response = await owner.get("/api/v1/tenants/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Peter Otieno" in response.text
    assert "Reference,Name,Phone" in response.text


# ---------------------------------------------------------------------- tenancies


async def test_creating_a_tenancy_occupies_the_unit(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)

    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])

    assert tenancy["reference_code"].startswith("TCY-")
    assert tenancy["status"] == "active"

    refreshed = await owner.get(f"/api/v1/units/{unit['id']}")
    assert refreshed.json()["status"] == "occupied"
    assert refreshed.json()["current_tenant_name"] == "Peter Otieno"


async def test_an_occupied_unit_cannot_be_double_let(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    first = await make_tenant(owner)
    second = await make_tenant(owner, full_name="Second Tenant")
    await make_tenancy(owner, first["id"], unit["id"])

    response = await owner.post(
        "/api/v1/tenancies",
        json={
            "tenant_id": second["id"],
            "unit_id": unit["id"],
            "start_date": date.today().isoformat(),
            "is_open_ended": True,
            "monthly_rent": "20000",
        },
    )

    assert response.status_code == 409
    assert "already has a live tenancy" in response.json()["detail"]


async def test_a_tenancy_needs_an_end_date_or_open_ended_flag(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)

    response = await owner.post(
        "/api/v1/tenancies",
        json={
            "tenant_id": tenant["id"],
            "unit_id": unit["id"],
            "start_date": date.today().isoformat(),
            "monthly_rent": "20000",
        },
    )
    assert response.status_code == 422


async def test_a_lease_expiring_within_60_days_is_marked_expiring_soon(owner: Actor) -> None:
    """Lifecycle status is derived from dates, never set by hand (US-018)."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)

    tenancy = await make_tenancy(
        owner,
        tenant["id"],
        unit["id"],
        start_date=(date.today() - timedelta(days=300)).isoformat(),
        end_date=(date.today() + timedelta(days=30)).isoformat(),
    )

    assert tenancy["status"] == "expiring_soon"
    assert tenancy["days_to_expiry"] == 30


async def test_a_past_end_date_is_expired(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)

    tenancy = await make_tenancy(
        owner,
        tenant["id"],
        unit["id"],
        start_date=(date.today() - timedelta(days=400)).isoformat(),
        end_date=(date.today() - timedelta(days=1)).isoformat(),
    )
    assert tenancy["status"] == "expired"


async def test_open_ended_tenancies_stay_active(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)

    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], end_date=None, is_open_ended=True)
    assert tenancy["status"] == "active"


async def test_vacating_releases_the_unit_and_preserves_history(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    first = await make_tenant(owner)
    tenancy = await make_tenancy(owner, first["id"], unit["id"])

    vacated = await owner.post(
        f"/api/v1/tenancies/{tenancy['id']}/vacate",
        json={"move_out_date": date.today().isoformat(), "notes": "Relocated"},
    )
    assert vacated.status_code == 200
    assert vacated.json()["status"] == "vacated"

    refreshed = await owner.get(f"/api/v1/units/{unit['id']}")
    assert refreshed.json()["status"] == "vacant"

    # The unit can be re-let, and the old tenancy is still on record.
    second = await make_tenant(owner, full_name="New Tenant")
    await make_tenancy(owner, second["id"], unit["id"])

    history = await owner.get("/api/v1/tenancies", params={"unit_id": unit["id"]})
    assert len(history.json()) == 2


async def test_expiring_filter_finds_leases_ending_soon(owner: Actor) -> None:
    prop = await make_property(owner)
    soon = await make_unit(owner, prop["id"], unit_number="SOON")
    later = await make_unit(owner, prop["id"], unit_number="LATER")
    tenant_a = await make_tenant(owner)
    tenant_b = await make_tenant(owner, full_name="Other Tenant")

    await make_tenancy(
        owner, tenant_a["id"], soon["id"], end_date=(date.today() + timedelta(days=20)).isoformat()
    )
    await make_tenancy(
        owner, tenant_b["id"], later["id"], end_date=(date.today() + timedelta(days=300)).isoformat()
    )

    response = await owner.get("/api/v1/tenancies", params={"expiring_within_days": 60})
    assert len(response.json()) == 1
    assert response.json()[0]["unit_number"] == "SOON"


# --------------------------------------------------------------- lease generation


async def test_lease_pdf_is_generated_on_tenancy_creation(owner: Actor, db) -> None:
    """US-016: the PDF exists in the tenant's vault the moment the tenancy does."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)

    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])

    assert tenancy["lease_document_id"] is not None
    assert tenancy["lease_url"]

    documents = await owner.get(f"/api/v1/tenants/{tenant['id']}/documents")
    leases = [d for d in documents.json() if d["category"] == "lease"]
    assert len(leases) == 1
    assert leases[0]["filename"] == f"Lease-{tenancy['reference_code']}.pdf"


async def test_lease_preview_renders_a_pdf(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], generate_lease=False)

    response = await owner.get(f"/api/v1/tenancies/{tenancy['id']}/lease/preview")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


async def test_a_custom_template_is_used_when_marked_default(owner: Actor) -> None:
    starter = (await owner.get("/api/v1/lease-templates/starter")).json()
    assert "{{ tenant_name }}" in starter["body_html"]

    created = await owner.post(
        "/api/v1/lease-templates",
        json={
            "name": "Acacia standard lease",
            "body_html": "<h2>Special terms</h2><p>Tenant: {{ tenant_name }}. Rent {{ rent_amount }}.</p>",
            "is_default": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["version"] == 1

    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])

    preview = await owner.get(f"/api/v1/tenancies/{tenancy['id']}/lease/preview")
    assert preview.status_code == 200
    assert preview.content.startswith(b"%PDF")


async def test_editing_a_template_bumps_its_version(owner: Actor) -> None:
    created = (
        await owner.post(
            "/api/v1/lease-templates",
            json={"name": "V1", "body_html": "<p>First wording</p>"},
        )
    ).json()

    updated = await owner.patch(
        f"/api/v1/lease-templates/{created['id']}", json={"body_html": "<p>Second wording</p>"}
    )

    assert updated.status_code == 200
    assert updated.json()["version"] == 2


# -------------------------------------------------------------- caretaker invites


async def test_caretaker_invitation_scopes_them_to_assigned_properties(
    owner: Actor, client: AsyncClient, db
) -> None:
    """US-013: a caretaker sees only the properties they were assigned."""
    assigned = await make_property(owner, name="Assigned Property")
    unassigned = await make_property(owner, name="Not Theirs")

    invited = await owner.post(
        "/api/v1/team/invitations",
        json={
            "full_name": "John Kamau",
            "phone_number": unique_phone(),
            "role": "caretaker",
            "property_ids": [assigned["id"]],
            "cash_limit": 20000,
        },
    )
    assert invited.status_code == 201

    invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invited.json()["id"])))
    # The raw token only ever goes out by SMS, so mint the link the same way the
    # service does to drive the acceptance flow here.
    from app.core.security import generate_url_token, hash_token

    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()

    preview = await client.get("/api/v1/invitations/preview", params={"token": raw})
    assert preview.status_code == 200
    assert preview.json()["full_name"] == "John Kamau"

    accepted = await client.post(
        "/api/v1/invitations/accept", json={"token": raw, "password": fresh_password()}
    )
    assert accepted.status_code == 200
    caretaker = Actor(client, accepted.json()["tokens"], accepted.json()["user"])

    visible = await caretaker.get("/api/v1/properties")
    assert [p["name"] for p in visible.json()] == ["Assigned Property"]

    blocked = await caretaker.get(f"/api/v1/properties/{unassigned['id']}")
    assert blocked.status_code == 403
    assert "not assigned" in blocked.json()["detail"]


async def test_caretaker_cannot_manage_properties(owner: Actor, client: AsyncClient, db) -> None:
    prop = await make_property(owner)
    invited = await owner.post(
        "/api/v1/team/invitations",
        json={
            "full_name": "John Kamau",
            "phone_number": unique_phone(),
            "role": "caretaker",
            "property_ids": [prop["id"]],
        },
    )
    invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invited.json()["id"])))
    from app.core.security import generate_url_token, hash_token

    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    await db.commit()

    accepted = await client.post(
        "/api/v1/invitations/accept", json={"token": raw, "password": fresh_password()}
    )
    caretaker = Actor(client, accepted.json()["tokens"], accepted.json()["user"])

    response = await caretaker.post("/api/v1/properties", json={"name": "Sneaky", "address": "Nowhere"})
    assert response.status_code == 403
    assert "property:manage" in response.json()["detail"]


async def test_an_expired_invitation_is_refused(owner: Actor, client: AsyncClient, db) -> None:
    from datetime import UTC, datetime

    from app.core.security import generate_url_token, hash_token

    invited = await owner.post(
        "/api/v1/team/invitations",
        json={"full_name": "Late Joiner", "phone_number": unique_phone(), "role": "caretaker"},
    )
    invitation = await db.scalar(select(Invitation).where(Invitation.id == uuid.UUID(invited.json()["id"])))
    raw = generate_url_token()
    invitation.token_hash = hash_token(raw)
    invitation.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()

    response = await client.get("/api/v1/invitations/preview", params={"token": raw})
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


async def test_tenants_from_another_organization_are_invisible(owner: Actor, other_owner: Actor) -> None:
    tenant = await make_tenant(owner)

    assert (await other_owner.get(f"/api/v1/tenants/{tenant['id']}")).status_code == 403
    assert (await other_owner.get("/api/v1/tenants")).json() == []
