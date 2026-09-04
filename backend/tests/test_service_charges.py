"""Sprint 15: commercial units, service charges, sinking fund and bulk operations."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.notification import Notification, NotificationType
from tests.conftest import Actor
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant


async def building(owner: Actor, unit_specs: list[dict]) -> dict:
    """A property with several units, some occupied."""
    prop = await make_property(owner)
    units = []
    for spec in unit_specs:
        unit = await make_unit(
            owner,
            prop["id"],
            unit_number=spec["unit_number"],
            monthly_rent=spec.get("rent", "30000.00"),
            size_sqm=spec.get("size_sqm"),
        )
        if spec.get("occupied"):
            tenant = await make_tenant(owner)
            await make_tenancy(
                owner,
                tenant["id"],
                unit["id"],
                monthly_rent=spec.get("rent", "30000.00"),
            )
        units.append(unit)
    return {"property": prop, "units": units}


async def set_scheme(owner: Actor, property_id: str, **overrides):
    payload = {
        "name": "Service charge",
        "apportionment": "fixed_per_unit",
        "fixed_amount": "2000.00",
        "monthly_pool": "0.00",
        "sinking_fund_percent": "0.00",
        **overrides,
    }
    response = await owner.put(f"/api/v1/service-charges/property/{property_id}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------ commercial units


async def test_a_unit_can_be_commercial(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])

    updated = await owner.patch(
        f"/api/v1/units/{unit['id']}",
        json={"use_class": "retail", "car_bays": 3, "size_sqm": 120.5},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["use_class"] == "retail"
    assert updated.json()["car_bays"] == 3


# -------------------------------------------------------------- apportionment


async def test_a_fixed_charge_is_the_same_for_every_unit(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1"}, {"unit_number": "A2"}])

    scheme = await set_scheme(owner, setup["property"]["id"], fixed_amount="2500.00")

    assert scheme["monthly_total"] == 5000.0
    assert {row["monthly_charge"] for row in scheme["units"]} == {2500.0}


async def test_a_floor_area_charge_splits_the_pool_by_size(owner: Actor) -> None:
    setup = await building(
        owner,
        [
            {"unit_number": "A1", "size_sqm": 100},
            {"unit_number": "A2", "size_sqm": 300},
        ],
    )

    scheme = await set_scheme(
        owner,
        setup["property"]["id"],
        apportionment="by_floor_area",
        fixed_amount="0.00",
        monthly_pool="40000.00",
    )

    charges = {row["unit_number"]: row["monthly_charge"] for row in scheme["units"]}
    assert charges == {"A1": 10000.0, "A2": 30000.0}
    assert scheme["monthly_total"] == 40000.0


async def test_the_rounding_remainder_is_not_lost(owner: Actor) -> None:
    setup = await building(
        owner,
        [
            {"unit_number": "A1", "size_sqm": 1},
            {"unit_number": "A2", "size_sqm": 1},
            {"unit_number": "A3", "size_sqm": 1},
        ],
    )

    scheme = await set_scheme(
        owner,
        setup["property"]["id"],
        apportionment="by_floor_area",
        fixed_amount="0.00",
        monthly_pool="100.00",
    )

    # 100 / 3 does not divide evenly; the pool must still come to exactly 100.
    assert scheme["monthly_total"] == 100.0


async def test_a_vacancy_costs_the_landlord_not_the_neighbours(owner: Actor) -> None:
    setup = await building(
        owner,
        [
            {"unit_number": "A1", "occupied": True},
            {"unit_number": "A2", "occupied": True},
            {"unit_number": "A3"},
        ],
    )

    scheme = await set_scheme(
        owner,
        setup["property"]["id"],
        apportionment="by_occupied_unit",
        fixed_amount="0.00",
        monthly_pool="30000.00",
    )

    charges = {row["unit_number"]: row["monthly_charge"] for row in scheme["units"]}
    assert charges["A1"] == 15000.0
    assert charges["A2"] == 15000.0
    # The empty unit is charged nothing, and the shortfall is the landlord's.
    assert charges["A3"] == 0.0


async def test_a_proportional_scheme_needs_a_pool(owner: Actor) -> None:
    prop = await make_property(owner)

    response = await owner.put(
        f"/api/v1/service-charges/property/{prop['id']}",
        json={"apportionment": "by_floor_area", "fixed_amount": "0.00", "monthly_pool": "0.00"},
    )

    assert response.status_code == 422


# ------------------------------------------------------------------- billing


async def test_the_service_charge_lands_on_the_rent_invoice(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])
    await set_scheme(owner, setup["property"]["id"], fixed_amount="3000.00")

    tenancies = (await owner.get("/api/v1/tenancies")).json()
    generated = await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancies[0]["id"]})
    assert generated.status_code in (200, 201), generated.text

    invoice = generated.json()
    charge_lines = [line for line in invoice["line_items"] if line["kind"] == "service_charge"]
    assert len(charge_lines) == 1
    assert Decimal(charge_lines[0]["amount"]) == Decimal("3000.00")


async def test_the_sinking_fund_takes_its_slice_as_the_charge_is_billed(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])
    scheme = await set_scheme(
        owner, setup["property"]["id"], fixed_amount="10000.00", sinking_fund_percent="10.00"
    )

    tenancies = (await owner.get("/api/v1/tenancies")).json()
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancies[0]["id"]})

    entries = (await owner.get(f"/api/v1/service-charges/{scheme['id']}/sinking-fund")).json()
    assert len(entries) == 1
    assert Decimal(entries[0]["amount"]) == Decimal("1000.00")
    assert entries[0]["movement"] == "contribution"


async def test_the_reserve_cannot_be_overdrawn(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1"}])
    scheme = await set_scheme(owner, setup["property"]["id"])

    response = await owner.post(
        f"/api/v1/service-charges/{scheme['id']}/sinking-fund",
        json={
            "movement": "withdrawal",
            "amount": "50000.00",
            "entry_date": date.today().isoformat(),
            "description": "New roof",
        },
    )

    assert response.status_code == 409
    assert "only holds" in response.json()["detail"]


# ------------------------------------------------------------ reconciliation


async def test_reconciliation_compares_budget_charged_and_spent(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])
    scheme = await set_scheme(
        owner,
        setup["property"]["id"],
        fixed_amount="5000.00",
        budgets=[
            {"category": "security", "monthly_budget": "3000.00"},
            {"category": "cleaning", "monthly_budget": "1500.00"},
        ],
    )

    tenancies = (await owner.get("/api/v1/tenancies")).json()
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancies[0]["id"]})

    await owner.post(
        f"/api/v1/service-charges/{scheme['id']}/expenses",
        json={
            "category": "security",
            "amount": "3500.00",
            "incurred_on": date.today().isoformat(),
            "description": "Guards for the month",
        },
    )

    first = date.today().replace(day=1)
    report = (
        await owner.get(
            f"/api/v1/service-charges/{scheme['id']}/reconciliation",
            params={"period_start": first.isoformat(), "period_end": date.today().isoformat()},
        )
    ).json()

    security = next(line for line in report["lines"] if line["category"] == "security")
    assert security["budgeted"] == 3000.0
    assert security["spent"] == 3500.0
    assert security["over_budget"] is True
    assert report["total_charged"] == 5000.0
    assert report["total_spent"] == 3500.0
    assert report["surplus_or_deficit"] == 1500.0


async def test_an_expense_cannot_be_dated_in_the_future(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1"}])
    scheme = await set_scheme(owner, setup["property"]["id"])

    response = await owner.post(
        f"/api/v1/service-charges/{scheme['id']}/expenses",
        json={
            "category": "cleaning",
            "amount": "100.00",
            "incurred_on": (date.today() + timedelta(days=1)).isoformat(),
            "description": "Next month's cleaning",
        },
    )

    assert response.status_code == 422


async def test_schemes_are_not_visible_across_organizations(owner: Actor, other_owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1"}])
    scheme = await set_scheme(owner, setup["property"]["id"])

    response = await other_owner.get(f"/api/v1/service-charges/{scheme['id']}/sinking-fund")

    assert response.status_code == 403


# --------------------------------------------------------------- bulk actions


async def test_a_rent_increase_previews_before_it_commits(owner: Actor) -> None:
    setup = await building(
        owner,
        [
            {"unit_number": "A1", "occupied": True, "rent": "20000.00"},
            {"unit_number": "A2", "occupied": True, "rent": "30000.00"},
        ],
    )

    preview = await owner.post(
        "/api/v1/bulk/rent-increase/preview",
        json={
            "property_id": setup["property"]["id"],
            "increase_type": "percent",
            "value": "10",
            "effective_date": (date.today() + timedelta(days=60)).isoformat(),
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["status"] == "previewed"
    assert body["total"] == 2
    new_rents = sorted(target["new_rent"] for target in body["targets"])
    assert new_rents == [22000.0, 33000.0]

    # Nothing has actually changed yet.
    tenancies = (await owner.get("/api/v1/tenancies")).json()
    assert sorted(Decimal(t["monthly_rent"]) for t in tenancies) == [
        Decimal("20000.00"),
        Decimal("30000.00"),
    ]


async def test_executing_the_increase_moves_the_rent_and_notifies_everyone(owner: Actor, db) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True, "rent": "20000.00"}])
    effective = date.today() + timedelta(days=60)

    preview = (
        await owner.post(
            "/api/v1/bulk/rent-increase/preview",
            json={
                "property_id": setup["property"]["id"],
                "increase_type": "fixed",
                "value": "2500",
                "effective_date": effective.isoformat(),
            },
        )
    ).json()

    executed = await owner.post(f"/api/v1/bulk/{preview['id']}/execute")
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "completed"
    assert executed.json()["succeeded"] == 1

    tenancies = (await owner.get("/api/v1/tenancies")).json()
    assert Decimal(tenancies[0]["monthly_rent"]) == Decimal("22500.00")

    # The unit's advertised rent moves with it, or the next vacancy is mispriced.
    unit = (await owner.get(f"/api/v1/units/{setup['units'][0]['id']}")).json()
    assert Decimal(unit["monthly_rent"]) == Decimal("22500.00")

    notices = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.RENT_INCREASE)
        )
    )
    assert notices
    assert any(effective.strftime("%d %B %Y") in row.body for row in notices)


async def test_the_increase_produces_a_written_notice(owner: Actor, db) -> None:
    from app.models.file import FileCategory, StoredFile

    setup = await building(owner, [{"unit_number": "A1", "occupied": True, "rent": "20000.00"}])
    preview = (
        await owner.post(
            "/api/v1/bulk/rent-increase/preview",
            json={
                "property_id": setup["property"]["id"],
                "increase_type": "percent",
                "value": "8",
                "effective_date": (date.today() + timedelta(days=45)).isoformat(),
            },
        )
    ).json()

    await owner.post(f"/api/v1/bulk/{preview['id']}/execute")

    notices = list(await db.scalars(select(StoredFile).where(StoredFile.category == FileCategory.NOTICE)))
    assert any(row.filename.startswith("Rent-review-A1") for row in notices)


async def test_a_commercial_unit_gets_the_commercial_lease_clauses(owner: Actor, db) -> None:
    from app.models.property import Unit
    from app.models.service_charge import UseClass
    from app.services import lease_service

    prop = await make_property(owner)
    created = await make_unit(owner, prop["id"])
    await owner.patch(f"/api/v1/units/{created['id']}", json={"use_class": "office"})

    unit = await db.get(Unit, created["id"])
    await db.refresh(unit)
    commercial = lease_service.clauses_for(unit)

    unit.use_class = None
    residential = lease_service.clauses_for(unit)

    # The covenants that matter differ: a shop needs a permitted use and a service
    # charge clause; a home needs quiet enjoyment.
    assert any(clause["title"] == "Permitted use" for clause in commercial)
    assert any(clause["title"] == "Rent and service charge" for clause in commercial)
    assert any(clause["title"] == "Use of premises" for clause in residential)
    assert UseClass.OFFICE.value == "office"


async def test_an_increase_must_take_effect_in_the_future(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])

    response = await owner.post(
        "/api/v1/bulk/rent-increase/preview",
        json={
            "property_id": setup["property"]["id"],
            "increase_type": "percent",
            "value": "5",
            "effective_date": date.today().isoformat(),
        },
    )

    assert response.status_code == 422


async def test_an_absurd_percentage_is_refused(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])

    response = await owner.post(
        "/api/v1/bulk/rent-increase/preview",
        json={
            "property_id": setup["property"]["id"],
            "increase_type": "percent",
            "value": "1000",
            "effective_date": (date.today() + timedelta(days=60)).isoformat(),
        },
    )

    assert response.status_code == 422


async def test_an_operation_cannot_be_executed_twice(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])
    preview = (
        await owner.post(
            "/api/v1/bulk/announcement/preview",
            json={
                "property_id": setup["property"]["id"],
                "subject": "Water shutdown",
                "message": "Water will be off on Saturday from 8am to 2pm.",
            },
        )
    ).json()

    await owner.post(f"/api/v1/bulk/{preview['id']}/execute")
    again = await owner.post(f"/api/v1/bulk/{preview['id']}/execute")

    assert again.status_code == 409


async def test_an_announcement_reaches_every_tenant_in_scope(owner: Actor, db) -> None:
    setup = await building(
        owner,
        [
            {"unit_number": "A1", "occupied": True},
            {"unit_number": "A2", "occupied": True},
            {"unit_number": "A3"},
        ],
    )

    preview = (
        await owner.post(
            "/api/v1/bulk/announcement/preview",
            json={
                "property_id": setup["property"]["id"],
                "subject": "Water shutdown",
                "message": "Water will be off on Saturday from 8am to 2pm.",
            },
        )
    ).json()
    # Only the two occupied units have anyone to tell.
    assert preview["total"] == 2

    executed = (await owner.post(f"/api/v1/bulk/{preview['id']}/execute")).json()
    assert executed["succeeded"] == 2

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.ANNOUNCEMENT)
        )
    )
    assert any("Water will be off" in row.body for row in rows)


async def test_reminders_only_go_to_tenants_who_actually_owe(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])

    preview = (
        await owner.post("/api/v1/bulk/reminders/preview", json={"property_id": setup["property"]["id"]})
    ).json()
    # Nothing has been invoiced, so nobody is in arrears.
    assert preview["total"] == 0

    tenancies = (await owner.get("/api/v1/tenancies")).json()
    await owner.post("/api/v1/invoices/generate", json={"tenancy_id": tenancies[0]["id"]})

    after = (
        await owner.post("/api/v1/bulk/reminders/preview", json={"property_id": setup["property"]["id"]})
    ).json()
    assert after["total"] == 1


async def test_a_cancelled_operation_cannot_be_run(owner: Actor) -> None:
    setup = await building(owner, [{"unit_number": "A1", "occupied": True}])
    preview = (
        await owner.post("/api/v1/bulk/invoices/preview", json={"property_id": setup["property"]["id"]})
    ).json()

    cancelled = await owner.post(f"/api/v1/bulk/{preview['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    response = await owner.post(f"/api/v1/bulk/{preview['id']}/execute")
    assert response.status_code == 409
