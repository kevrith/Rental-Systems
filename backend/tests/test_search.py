"""Cross-entity search (Sprint 26A, item 10) — app/services/search_service.py."""

import uuid

from app.api.deps import OrgContext
from app.models.organization import Organization
from app.models.property import CaretakerAssignment
from app.models.user import User, UserRole
from app.services import search_service
from tests.conftest import Actor, unique_phone
from tests.test_operations import occupied_unit
from tests.test_portfolio import make_property, make_unit


async def test_search_finds_a_tenant_by_partial_name(owner: Actor) -> None:
    setup = await occupied_unit(owner)

    response = await owner.get("/api/v1/search", params={"q": setup["tenant"]["full_name"][:5]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(r["type"] == "tenant" and r["id"] == setup["tenant"]["id"] for r in body)


async def test_search_finds_a_property_and_a_unit(owner: Actor) -> None:
    setup = await occupied_unit(owner)

    by_property = (await owner.get("/api/v1/search", params={"q": setup["property"]["name"][:5]})).json()
    assert any(r["type"] == "property" and r["id"] == setup["property"]["id"] for r in by_property)

    by_unit = (await owner.get("/api/v1/search", params={"q": setup["unit"]["unit_number"]})).json()
    assert any(r["type"] == "unit" and r["id"] == setup["unit"]["id"] for r in by_unit)


async def test_search_finds_an_invoice_by_reference(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    invoice = (
        await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    ).json()
    reference = invoice["reference_code"]

    response = await owner.get("/api/v1/search", params={"q": reference})
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(r["type"] == "invoice" and r["title"] == reference for r in body)


async def test_search_ignores_a_too_short_query(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    response = await owner.get("/api/v1/search", params={"q": setup["tenant"]["full_name"][0]})
    assert response.status_code == 200
    assert response.json() == []


async def test_search_is_scoped_to_the_caller_organization(owner: Actor, other_owner: Actor) -> None:
    setup = await occupied_unit(owner)

    response = await other_owner.get("/api/v1/search", params={"q": setup["tenant"]["full_name"][:5]})
    assert response.status_code == 200
    assert response.json() == []


async def test_search_scopes_a_caretaker_to_their_assigned_properties(owner: Actor, db) -> None:
    """A caretaker assigned to one property does not see a search result from another."""
    assigned = await occupied_unit(owner)
    other_property = await make_property(owner)
    other_unit = await make_unit(owner, other_property["id"])

    caretaker_user = User(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        full_name="Field Caretaker",
        email=f"caretaker-{uuid.uuid4().hex[:8]}@example.com",
        phone_number=unique_phone(),
        password_hash="not-a-real-hash",
        role=UserRole.CARETAKER,
        is_active=True,
        is_email_verified=True,
        is_phone_verified=True,
    )
    db.add(caretaker_user)
    await db.flush()
    db.add(
        CaretakerAssignment(
            organization_id=caretaker_user.organization_id,
            user_id=caretaker_user.id,
            property_id=uuid.UUID(assigned["property"]["id"]),
        )
    )
    await db.commit()

    org_row = await db.get(Organization, caretaker_user.organization_id)
    context = OrgContext(user=caretaker_user, organization=org_row)

    assigned_results = await search_service.search(db, context, assigned["unit"]["unit_number"])
    assert any(r.id == uuid.UUID(assigned["unit"]["id"]) for r in assigned_results)

    other_results = await search_service.search(db, context, other_unit["unit_number"])
    assert not any(r.id == uuid.UUID(other_unit["id"]) for r in other_results)
