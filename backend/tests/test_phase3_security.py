"""Phase 3 penetration-test checklist, executed as tests (US-084).

A checklist somebody ticks in a spreadsheet rots the week after it is signed.
These are the same checks, run on every commit, aimed specifically at what
Phase 3 added — and what it added is unusual: four routes that anyone on the
internet can reach without an account, and a lot of new tenant-owned tables.

Each test names the attack it is defending against.
"""

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.conftest import Actor, unique_phone
from tests.test_portfolio import make_property, make_unit
from tests.test_screening import application_payload
from tests.test_tenancy import make_tenancy, make_tenant

# ------------------------------------------------- the unauthenticated surface


@pytest.mark.asyncio
async def test_a_guessed_unit_id_does_not_expose_an_occupied_unit(owner: Actor, client: AsyncClient):
    """Enumeration: the public apply route must not confirm that a unit exists
    just because someone guessed its id."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)
    await make_tenancy(owner, tenant["id"], unit["id"])

    response = await client.get(f"/api/v1/apply/{unit['id']}")

    assert response.status_code == 404
    body = response.text
    assert prop["name"] not in body
    assert unit["unit_number"] not in body


@pytest.mark.asyncio
async def test_a_public_application_cannot_be_aimed_at_another_organizations_unit(
    owner: Actor, other_owner: Actor, client: AsyncClient
):
    """Parameter tampering: the unit in the path is authoritative, so a crafted
    body cannot file an application against a different organisation."""
    mine = await make_property(owner)
    my_unit = await make_unit(owner, mine["id"])

    theirs = await make_property(other_owner)
    their_unit = await make_unit(other_owner, theirs["id"])

    payload = application_payload(str(their_unit["id"]))
    response = await client.post(f"/api/v1/apply/{my_unit['id']}", json=payload)

    assert response.status_code == 201
    # It landed on my unit, not theirs.
    mine_list = (await owner.get("/api/v1/applications")).json()
    theirs_list = (await other_owner.get("/api/v1/applications")).json()
    assert len(mine_list) == 1
    assert not theirs_list


@pytest.mark.asyncio
async def test_a_forged_token_gets_nothing(client: AsyncClient):
    """Token guessing: the guarantee, reference and listing links are the whole
    authentication, so a wrong one must be indistinguishable from a missing one."""
    for path in (
        "/api/v1/guarantee/not-a-real-token",
        "/api/v1/reference/not-a-real-token",
        "/api/v1/listings/aaaaaaaaaa",
    ):
        response = await client.get(path)
        assert response.status_code == 404, path
        assert "organization" not in response.text.lower()


@pytest.mark.asyncio
async def test_an_expired_guarantee_link_stops_working(owner: Actor, client: AsyncClient, db):
    """Link lifetime: a token that leaks a year later must be inert."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.application import Guarantor
    from app.services.screening_service import _hash_token
    from tests.test_screening import make_application, vacant_unit

    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        guarantors=[
            {
                "full_name": "A guarantor",
                "relationship_to_applicant": "Father",
                "phone_number": unique_phone(),
            }
        ],
    )

    guarantor = await db.scalar(select(Guarantor).where(Guarantor.application_id == application["id"]))
    raw = "expired-link-token"
    guarantor.token_hash = _hash_token(raw)
    guarantor.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db.commit()

    response = await client.get(f"/api/v1/guarantee/{raw}")

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_a_public_listing_carries_no_internal_identifiers(owner: Actor, client: AsyncClient):
    """Information disclosure: the advert is shared with strangers, so it must
    not carry organisation ids, tenant data or reference codes."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    listing = (await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")).json()

    body = (await client.get(f"/api/v1/listings/{listing['slug']}")).json()

    assert "organization_id" not in body
    assert "reference_code" not in body
    assert unit["reference_code"] not in str(body)


@pytest.mark.asyncio
async def test_a_rotated_listing_link_revokes_the_old_one(owner: Actor, client: AsyncClient):
    """Revocation: an over-shared link has to be killable."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    listing = (await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")).json()
    old = listing["slug"]

    await owner.post(f"/api/v1/vacancies/listings/{listing['id']}/rotate-link")

    assert (await client.get(f"/api/v1/listings/{old}")).status_code == 404


# ---------------------------------------------------- cross-tenant separation


@pytest.mark.asyncio
async def test_no_phase_3_resource_is_readable_across_organizations(owner: Actor, other_owner: Actor):
    """Horizontal privilege escalation, checked once per Phase 3 resource."""
    prop = await make_property(owner)
    await make_unit(owner, prop["id"])
    hirer = await make_tenant(owner)

    vendor = (
        await owner.post(
            "/api/v1/vendors",
            json={
                "name": "A vendor",
                "specialties": ["plumbing"],
                "phone_number": unique_phone(),
            },
        )
    ).json()
    compliance = (
        await owner.post(
            "/api/v1/compliance",
            json={
                "property_id": prop["id"],
                "compliance_type": "nema",
                "name": "NEMA licence",
                "expires_on": (date.today() + timedelta(days=90)).isoformat(),
            },
        )
    ).json()
    scheme = (
        await owner.put(
            f"/api/v1/service-charges/property/{prop['id']}",
            json={"apportionment": "fixed_per_unit", "fixed_amount": "1000.00"},
        )
    ).json()
    asset = (
        await owner.post(
            "/api/v1/assets",
            json={
                "kind": "vehicle",
                "name": "A car",
                "registration_number": f"KZZ {uuid.uuid4().hex[:3]}",
                "daily_rate": "3000.00",
            },
        )
    ).json()
    agreement = (
        await owner.post(
            "/api/v1/rental-agreements",
            json={
                "asset_id": asset["id"],
                "tenant_id": hirer["id"],
                "start_date": date.today().isoformat(),
                "end_date": (date.today() + timedelta(days=2)).isoformat(),
                "rate_basis": "daily",
            },
        )
    ).json()

    # Every one of these is another organisation's row.
    for path in (
        f"/api/v1/vendors/{vendor['id']}",
        f"/api/v1/service-charges/{scheme['id']}/sinking-fund",
        f"/api/v1/parking/property/{prop['id']}",
        f"/api/v1/assets/{asset['id']}",
        f"/api/v1/rental-agreements/{agreement['id']}",
    ):
        response = await other_owner.get(path)
        assert response.status_code == 403, f"{path} -> {response.status_code}"

    # And a write is refused just as firmly as a read.
    blocked = await other_owner.patch(f"/api/v1/compliance/{compliance['id']}", json={"name": "Mine now"})
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_row_level_security_blocks_a_phase_3_read_with_no_org_context(db):
    """Defence in depth: with the application's scoping bypassed entirely, the
    database itself must still refuse another tenant's rows."""
    from app.core.rls import PHASE_3_ORG_SCOPED_TABLES

    # The test role owns the tables, which bypasses RLS by design, so this
    # asserts the policies exist and are enabled rather than re-testing enforcement
    # (which `test_rls.py` does against the restricted role).
    for table in PHASE_3_ORG_SCOPED_TABLES:
        enabled = await db.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :name"),
            {"name": table},
        )
        assert enabled is True, f"{table} does not have row level security enabled"

        policies = await db.scalar(
            text("SELECT count(*) FROM pg_policies WHERE tablename = :name"),
            {"name": table},
        )
        assert policies and policies >= 1, f"{table} has RLS on but no policy"


# --------------------------------------------------------------- input safety


@pytest.mark.asyncio
async def test_an_injection_attempt_in_a_public_field_is_stored_as_text(owner: Actor, client: AsyncClient):
    """SQL injection: the ORM parameterises everything, but the public form is
    the one place a stranger controls the input, so it is checked explicitly."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])

    hostile = "Robert'); DROP TABLE tenant_applications;--"
    response = await client.post(
        f"/api/v1/apply/{unit['id']}",
        json=application_payload(str(unit["id"]), full_name=hostile),
    )

    assert response.status_code == 201
    listed = (await owner.get("/api/v1/applications")).json()
    assert listed[0]["full_name"] == hostile

    # The table is still there, which is the actual assertion.
    still_working = await owner.get("/api/v1/applications/summary")
    assert still_working.status_code == 200


@pytest.mark.asyncio
async def test_an_oversized_public_submission_is_refused(owner: Actor, client: AsyncClient):
    """Resource exhaustion: every public field has a length ceiling."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])

    response = await client.post(
        f"/api/v1/apply/{unit['id']}",
        json=application_payload(str(unit["id"]), notes="x" * 50_000),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_bulk_action_cannot_reach_beyond_its_preview(owner: Actor):
    """Blast radius: execution runs over the stored target list, so a property
    added between preview and execute is not silently swept in."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"], unit_number="A1")
    tenant = await make_tenant(owner)
    await make_tenancy(owner, tenant["id"], unit["id"])

    preview = (
        await owner.post(
            "/api/v1/bulk/announcement/preview",
            json={
                "property_id": prop["id"],
                "subject": "Notice",
                "message": "The water will be off on Saturday morning.",
            },
        )
    ).json()
    assert preview["total"] == 1

    # A second tenancy appears after the preview was taken.
    second_unit = await make_unit(owner, prop["id"], unit_number="A2")
    second_tenant = await make_tenant(owner)
    await make_tenancy(owner, second_tenant["id"], second_unit["id"])

    executed = (await owner.post(f"/api/v1/bulk/{preview['id']}/execute")).json()

    assert executed["total"] == 1
    assert executed["succeeded"] == 1


@pytest.mark.asyncio
async def test_no_phase_3_response_leaks_a_stored_token(owner: Actor):
    """A serialiser that forgets to exclude a token hash is a slow-motion breach."""
    from tests.test_screening import make_application, vacant_unit

    setup = await vacant_unit(owner)
    application = await make_application(
        owner,
        setup["unit"]["id"],
        current_landlord_name="Previous landlord",
        current_landlord_phone=unique_phone(),
        guarantors=[
            {
                "full_name": "A guarantor",
                "relationship_to_applicant": "Father",
                "phone_number": unique_phone(),
            }
        ],
    )
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    listing = (await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")).json()

    for body in (str(application), str(listing)):
        assert "token_hash" not in body
        assert "expires_at" not in body or "token" not in body
