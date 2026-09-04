"""Phase 3 QA (US-084).

The per-sprint suites check that each feature works. These check the properties
that have to hold *across* Phase 3, and which no single feature test would notice
breaking:

  * every new table is inside the RLS policy set, not just scoped in Python;
  * every new public route is a deliberate, documented decision;
  * every new scheduled task is registered on the beat schedule;
  * the money paths that several sprints now write to still add up;
  * a caretaker scoped to one property cannot see another's Phase 3 data.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.routing import APIRoute

from app.core.rls import ORG_SCOPED_TABLES, PHASE_3_ORG_SCOPED_TABLES
from app.main import app
from app.models.base import Base
from tests.conftest import Actor
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant

# Everything Phase 3 added that holds tenant data.
PHASE_3_TABLES = {
    "vendors",
    "tenant_applications",
    "guarantors",
    "reference_checks",
    "service_charge_schemes",
    "service_charge_budgets",
    "service_charge_expenses",
    "sinking_fund_entries",
    "bulk_operations",
    "vacancy_listings",
    "inquiries",
    "data_exports",
    "compliance_items",
    "parking_bays",
    "parking_allocations",
    "amenities",
    "amenity_bookings",
    "utility_accounts",
    "rental_assets",
    "rental_agreements",
}

# The scheduled work Phase 3 introduced.
PHASE_3_TASKS = {
    "rentflow.flag_overdue_maintenance",
    "rentflow.sweep_stale_references",
    "rentflow.chase_stale_leads",
    "rentflow.monthly_data_export",
    "rentflow.sweep_compliance_expiry",
    "rentflow.sweep_overdue_utilities",
}


def test_every_phase_3_table_is_covered_by_row_level_security():
    """Application-level scoping is the first lock; RLS is the second. A table
    that has only the first is one missed WHERE clause from a leak."""
    declared = set(PHASE_3_ORG_SCOPED_TABLES)
    missing = PHASE_3_TABLES - declared
    assert not missing, f"Phase 3 tables with no RLS policy: {sorted(missing)}"

    # And the aggregate list the migrations drive off must contain them too.
    assert PHASE_3_TABLES <= set(ORG_SCOPED_TABLES)


def test_every_phase_3_table_carries_an_organization_id():
    """RLS compares `organization_id` per row, so a table without one silently
    opts out of the policy it was given."""
    for name in sorted(PHASE_3_TABLES):
        table = Base.metadata.tables.get(name)
        assert table is not None, f"{name} is not in the model metadata"
        assert "organization_id" in table.c, f"{name} has no organization_id"


def test_every_phase_3_scheduled_task_is_actually_scheduled():
    """A Celery task nobody put on the beat schedule never runs, and the feature
    it backs quietly does not exist."""
    from app.tasks.celery_app import celery_app

    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    missing = PHASE_3_TASKS - scheduled
    assert not missing, f"Tasks defined but never scheduled: {sorted(missing)}"


def test_the_public_surface_is_only_what_phase_3_intended():
    """Screening and vacancy marketing deliberately expose four unauthenticated
    prefixes. Anything else appearing there is an accident."""
    from tests.test_regression import PUBLIC_PREFIXES, _is_public

    phase_3_public = {
        path
        for route in app.routes
        if isinstance(route, APIRoute)
        for path in [route.path]
        if _is_public(path)
        and any(
            path.startswith(prefix)
            for prefix in ("/api/v1/apply", "/api/v1/guarantee", "/api/v1/reference", "/api/v1/listings")
        )
    }
    assert phase_3_public, "the Phase 3 public routes have disappeared"

    for prefix in ("/api/v1/apply", "/api/v1/guarantee", "/api/v1/reference", "/api/v1/listings"):
        assert prefix in PUBLIC_PREFIXES, f"{prefix} is public without a stated reason"


@pytest.mark.asyncio
async def test_one_invoice_carries_rent_service_charge_and_parking(owner: Actor):
    """Three Phase 3 sprints now write to the same invoice. They have to add up."""
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"], monthly_rent="30000.00")
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"], monthly_rent="30000.00")

    # Sprint 15: a service charge on the building.
    await owner.put(
        f"/api/v1/service-charges/property/{prop['id']}",
        json={"apportionment": "fixed_per_unit", "fixed_amount": "4000.00"},
    )

    # Sprint 17: a parking bay allocated to this tenancy.
    bay = (
        await owner.post(
            "/api/v1/parking/bays",
            json={"property_id": prop["id"], "bay_number": "P9", "monthly_fee": "3500.00"},
        )
    ).json()
    await owner.post(
        f"/api/v1/parking/bays/{bay['id']}/allocate",
        json={"tenancy_id": tenancy["id"], "start_date": date.today().isoformat()},
    )

    invoice = (await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancy["id"]})).json()

    kinds = {line["kind"] for line in invoice["line_items"]}
    assert {"rent", "service_charge", "other"} <= kinds

    # 30,000 rent + 4,000 service charge + 3,500 parking.
    assert Decimal(invoice["total"]) == Decimal("37500.00")
    assert sum(Decimal(line["amount"]) for line in invoice["line_items"]) == Decimal(invoice["total"])


@pytest.mark.asyncio
async def test_a_caretaker_only_sees_their_own_properties_phase_3_data(owner: Actor, client, db):
    """Property scoping has to hold on the new Phase 3 read paths too, not just
    the ones it was written for."""
    import uuid as uuid_module

    from sqlalchemy import select

    from app.core.security import generate_url_token, hash_token
    from app.models.session import Invitation
    from tests.conftest import Actor as ActorType
    from tests.conftest import fresh_password, unique_phone

    mine = await make_property(owner, name="Assigned block")
    theirs = await make_property(owner, name="Someone else's block")
    await make_unit(owner, mine["id"], unit_number="A1")
    await make_unit(owner, theirs["id"], unit_number="B1")

    for property_record in (mine, theirs):
        created = await owner.post(
            "/api/v1/compliance",
            json={
                "property_id": property_record["id"],
                "compliance_type": "fire_safety",
                "name": f"Fire certificate — {property_record['name']}",
                "expires_on": (date.today() + timedelta(days=100)).isoformat(),
            },
        )
        assert created.status_code == 201, created.text

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

    # The raw token only ever goes out by SMS, so mint one the same way to drive
    # the acceptance flow.
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
    caretaker = ActorType(client, accepted.json()["tokens"], accepted.json()["user"])

    # Compliance: only the assigned block.
    visible = await caretaker.get("/api/v1/compliance")
    assert visible.status_code == 200, visible.text
    assert {item["property_name"] for item in visible.json()} == {"Assigned block"}

    dashboard = (await caretaker.get("/api/v1/compliance/dashboard")).json()
    assert [row["property_name"] for row in dashboard["properties"]] == ["Assigned block"]

    # The vacancy desk is scoped the same way.
    desk = (await caretaker.get("/api/v1/vacancies")).json()
    assert {row["property_name"] for row in desk["units"]} <= {"Assigned block"}

    # And a direct hit on the other property's facilities is refused outright.
    blocked = await caretaker.get(f"/api/v1/parking/property/{theirs['id']}")
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_the_screening_score_never_exceeds_its_own_maximum(owner: Actor):
    """Four weighted components, summed. A change to one weight that broke the
    total would be invisible until an applicant scored 112."""
    from tests.test_screening import make_application, vacant_unit

    setup = await vacant_unit(owner, rent="10000.00")
    application = await make_application(
        owner,
        setup["unit"]["id"],
        monthly_income="500000.00",
        current_landlord_name="Previous landlord",
        current_landlord_phone="+254700111222",
        guarantors=[
            {
                "full_name": "A guarantor",
                "relationship_to_applicant": "Father",
                "phone_number": "+254700333444",
            }
        ],
    )

    breakdown = application["score_breakdown"]
    assert sum(component["max"] for component in breakdown["components"]) == 100
    assert 0 <= breakdown["score"] <= 100
    for component in breakdown["components"]:
        assert 0 <= component["points"] <= component["max"], component["label"]
