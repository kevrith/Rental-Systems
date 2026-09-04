"""Sprint 18: vehicle and equipment hire."""

from datetime import date, timedelta
from decimal import Decimal

from tests.conftest import Actor
from tests.test_tenancy import make_tenant

_counter = 0


def unique_suffix() -> int:
    global _counter
    _counter += 1
    return _counter


def in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


async def make_vehicle(owner: Actor, **overrides) -> dict:
    payload = {
        "kind": "vehicle",
        "name": "Toyota Fielder",
        "registration_number": f"KDA {100 + unique_suffix()}X",
        "make": "Toyota",
        "model": "Fielder",
        "year": 2019,
        "daily_rate": "4500.00",
        "weekly_rate": "27000.00",
        "deposit_amount": "20000.00",
        "mileage": 90000,
        "daily_mileage_limit": 150,
        "excess_mileage_rate": "25.00",
        "insurance_expiry": in_days(200),
        "inspection_expiry": in_days(200),
        "road_licence_expiry": in_days(200),
        **overrides,
    }
    response = await owner.post("/api/v1/assets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def make_equipment(owner: Actor, **overrides) -> dict:
    payload = {
        "kind": "equipment",
        "name": "Honda generator 5kVA",
        "serial_number": f"GEN-{unique_suffix()}",
        "category": "Power",
        "daily_rate": "2500.00",
        "deposit_amount": "10000.00",
        "service_interval_days": 90,
        "last_serviced_on": in_days(-10),
        **overrides,
    }
    response = await owner.post("/api/v1/assets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def book(owner: Actor, asset_id: str, tenant_id: str, **overrides) -> dict:
    payload = {
        "asset_id": asset_id,
        "tenant_id": tenant_id,
        "start_date": in_days(1),
        "end_date": in_days(3),
        "rate_basis": "daily",
        **overrides,
    }
    response = await owner.post("/api/v1/rental-agreements", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------- assets


async def test_a_vehicle_needs_its_registration(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/assets",
        json={"kind": "vehicle", "name": "Nameless car", "daily_rate": "3000.00"},
    )

    assert response.status_code == 422


async def test_equipment_needs_a_serial_number(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/assets",
        json={"kind": "equipment", "name": "A generator", "daily_rate": "2000.00"},
    )

    assert response.status_code == 422


async def test_a_registration_cannot_be_added_twice(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)

    duplicate = await owner.post(
        "/api/v1/assets",
        json={
            "kind": "vehicle",
            "name": "Another car",
            "registration_number": vehicle["registration_number"],
            "daily_rate": "3000.00",
        },
    )

    assert duplicate.status_code == 409
    assert "already in your fleet" in duplicate.json()["detail"]


async def test_expiring_paperwork_surfaces_as_a_warning(owner: Actor) -> None:
    vehicle = await make_vehicle(owner, insurance_expiry=in_days(-3))

    assert any("Insurance expired 3 day(s) ago" in w for w in vehicle["compliance_warnings"])

    overview = (await owner.get("/api/v1/assets/overview")).json()
    assert any(row["reference_code"] == vehicle["reference_code"] for row in overview["compliance_warnings"])


async def test_an_overdue_service_is_flagged(owner: Actor) -> None:
    equipment = await make_equipment(owner, service_interval_days=30, last_serviced_on=in_days(-60))

    assert any("Service overdue" in w for w in equipment["compliance_warnings"])
    assert equipment["service_due_on"] is not None


# ------------------------------------------------------------------- booking


async def test_an_asset_cannot_be_in_two_places_at_once(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    first_hirer = await make_tenant(owner)
    second_hirer = await make_tenant(owner)

    await book(owner, vehicle["id"], first_hirer["id"], start_date=in_days(1), end_date=in_days(5))

    clash = await owner.post(
        "/api/v1/rental-agreements",
        json={
            "asset_id": vehicle["id"],
            "tenant_id": second_hirer["id"],
            # Overlaps the tail of the first booking.
            "start_date": in_days(4),
            "end_date": in_days(8),
            "rate_basis": "daily",
        },
    )

    assert clash.status_code == 409
    assert "already booked" in clash.json()["detail"]


async def test_a_later_window_is_free(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    first = await make_tenant(owner)
    second = await make_tenant(owner)

    await book(owner, vehicle["id"], first["id"], start_date=in_days(1), end_date=in_days(3))
    later = await owner.post(
        "/api/v1/rental-agreements",
        json={
            "asset_id": vehicle["id"],
            "tenant_id": second["id"],
            "start_date": in_days(4),
            "end_date": in_days(6),
            "rate_basis": "daily",
        },
    )

    assert later.status_code == 201


async def test_the_daily_quote_counts_both_end_days(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)

    agreement = await book(owner, vehicle["id"], hirer["id"], start_date=in_days(1), end_date=in_days(3))

    # A three-day window is three days at the counter, not two.
    assert agreement["hire_days"] == 3
    assert Decimal(agreement["hire_charge"]) == Decimal("13500.00")


async def test_a_weekly_rate_charges_per_started_week(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)

    agreement = await book(
        owner,
        vehicle["id"],
        hirer["id"],
        start_date=in_days(1),
        end_date=in_days(9),
        rate_basis="weekly",
    )

    # Nine days on a weekly rate is two weeks.
    assert Decimal(agreement["hire_charge"]) == Decimal("54000.00")


async def test_a_hire_cannot_end_before_it_starts(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)

    response = await owner.post(
        "/api/v1/rental-agreements",
        json={
            "asset_id": vehicle["id"],
            "tenant_id": hirer["id"],
            "start_date": in_days(5),
            "end_date": in_days(2),
            "rate_basis": "daily",
        },
    )

    assert response.status_code == 422


# ----------------------------------------------------------- check out and in


async def test_a_vehicle_with_lapsed_insurance_does_not_go_out(owner: Actor) -> None:
    vehicle = await make_vehicle(owner, insurance_expiry=in_days(-1))
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"])

    response = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8},
    )

    assert response.status_code == 409
    assert "cannot go out" in response.json()["detail"]


async def test_an_override_is_possible_but_must_be_explained(owner: Actor) -> None:
    vehicle = await make_vehicle(owner, insurance_expiry=in_days(-1))
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"])

    unexplained = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "override_compliance": True},
    )
    assert unexplained.status_code == 422

    explained = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={
            "mileage": 90000,
            "override_compliance": True,
            "override_reason": "Cover renewed this morning, certificate arriving by email",
        },
    )
    assert explained.status_code == 200
    assert explained.json()["status"] == "out"


async def test_the_full_hire_cycle_prices_the_extras(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"], start_date=in_days(1), end_date=in_days(3))

    out = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8, "condition_notes": "Clean, no marks"},
    )
    assert out.status_code == 200, out.text
    assert out.json()["status"] == "out"

    asset = (await owner.get(f"/api/v1/assets/{vehicle['id']}")).json()
    assert asset["status"] == "on_hire"
    assert asset["current_hire"] == agreement["reference_code"]

    back = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-in",
        json={
            # 600 km against a 450 km allowance (150/day x 3 days) = 150 over.
            "mileage": 90600,
            # Returned at half a tank on a full-to-full policy = 4 eighths short.
            "fuel_eighths": 4,
            "condition_notes": "Scratch on the rear bumper",
            "damage_charge": "5000.00",
            "returned_on": in_days(3),
        },
    )
    assert back.status_code == 200, back.text
    body = back.json()

    assert body["status"] == "returned"
    assert body["mileage_covered"] == 600
    assert Decimal(body["excess_mileage_charge"]) == Decimal("3750.00")
    assert Decimal(body["fuel_charge"]) == Decimal("3600.00")
    assert Decimal(body["damage_charge"]) == Decimal("5000.00")
    assert Decimal(body["late_charge"]) == Decimal("0.00")
    # 13,500 hire + 3,750 + 3,600 + 5,000
    assert Decimal(body["total_charge"]) == Decimal("25850.00")
    # 20,000 deposit less 12,350 of extras.
    assert Decimal(body["deposit_refunded"]) == Decimal("7650.00")

    freed = (await owner.get(f"/api/v1/assets/{vehicle['id']}")).json()
    assert freed["status"] == "available"
    assert freed["mileage"] == 90600


async def test_a_late_return_is_charged_at_the_daily_rate(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"], start_date=in_days(-5), end_date=in_days(-2))

    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8},
    )
    back = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-in",
        json={"mileage": 90100, "fuel_eighths": 8, "returned_on": date.today().isoformat()},
    )

    # Two days late at 4,500 a day.
    assert Decimal(back.json()["late_charge"]) == Decimal("9000.00")


async def test_the_deposit_refund_never_goes_negative(owner: Actor) -> None:
    vehicle = await make_vehicle(owner, deposit_amount="5000.00")
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"])

    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8},
    )
    back = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-in",
        json={"mileage": 90050, "fuel_eighths": 8, "damage_charge": "50000.00"},
    )

    assert Decimal(back.json()["deposit_refunded"]) == Decimal("0.00")


async def test_the_odometer_cannot_go_backwards(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"])

    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8},
    )
    response = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-in",
        json={"mileage": 89000, "fuel_eighths": 8},
    )

    assert response.status_code == 422
    assert "less than at check-out" in response.json()["detail"]


async def test_an_asset_cannot_be_checked_out_twice(owner: Actor) -> None:
    equipment = await make_equipment(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, equipment["id"], hirer["id"])

    await owner.post(f"/api/v1/rental-agreements/{agreement['id']}/check-out", json={})
    again = await owner.post(f"/api/v1/rental-agreements/{agreement['id']}/check-out", json={})

    assert again.status_code == 409


async def test_equipment_hire_needs_no_mileage(owner: Actor) -> None:
    equipment = await make_equipment(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, equipment["id"], hirer["id"], start_date=in_days(1), end_date=in_days(2))

    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"condition_notes": "Starts first pull, full oil"},
    )
    back = await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-in",
        json={"condition_notes": "Returned clean", "returned_on": in_days(2)},
    )

    assert back.status_code == 200
    # Two days at 2,500, and none of the vehicle-only charges apply.
    assert Decimal(back.json()["total_charge"]) == Decimal("5000.00")
    assert Decimal(back.json()["fuel_charge"]) == Decimal("0.00")


# ----------------------------------------------------------- the fleet screen


async def test_the_availability_calendar_shows_booked_windows(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"], start_date=in_days(2), end_date=in_days(4))

    calendar = (await owner.get(f"/api/v1/assets/{vehicle['id']}/availability")).json()

    assert len(calendar) == 1
    assert calendar[0]["reference_code"] == agreement["reference_code"]
    assert calendar[0]["hirer"] == hirer["full_name"]


async def test_searching_for_a_free_asset_excludes_booked_ones(owner: Actor) -> None:
    booked = await make_vehicle(owner, name="Booked car")
    free = await make_vehicle(owner, name="Free car")
    hirer = await make_tenant(owner)
    await book(owner, booked["id"], hirer["id"], start_date=in_days(1), end_date=in_days(5))

    available = (
        await owner.get(
            "/api/v1/assets",
            params={"available_from": in_days(2), "available_to": in_days(3), "kind": "vehicle"},
        )
    ).json()

    names = [asset["name"] for asset in available]
    assert "Free car" in names
    assert "Booked car" not in names
    assert free["id"] in [asset["id"] for asset in available]


async def test_the_overview_counts_the_fleet(owner: Actor) -> None:
    await make_vehicle(owner, name="Car one")
    await make_equipment(owner, name="Generator one")
    hirer = await make_tenant(owner)
    vehicle = await make_vehicle(owner, name="Car two")
    agreement = await book(owner, vehicle["id"], hirer["id"])
    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8},
    )

    overview = (await owner.get("/api/v1/assets/overview")).json()

    assert overview["vehicles"] == 2
    assert overview["equipment"] == 1
    assert overview["on_hire"] == 1
    assert overview["available"] == 2


async def test_an_overdue_return_is_visible(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    hirer = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], hirer["id"], start_date=in_days(-10), end_date=in_days(-1))
    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/check-out",
        json={"mileage": 90000, "fuel_eighths": 8},
    )

    overdue = (await owner.get("/api/v1/rental-agreements", params={"overdue_only": True})).json()

    assert any(row["reference_code"] == agreement["reference_code"] for row in overdue)
    assert overdue[0]["is_overdue"] is True


async def test_cancelling_a_booking_frees_the_window(owner: Actor) -> None:
    vehicle = await make_vehicle(owner)
    first = await make_tenant(owner)
    second = await make_tenant(owner)
    agreement = await book(owner, vehicle["id"], first["id"], start_date=in_days(1), end_date=in_days(5))

    await owner.post(
        f"/api/v1/rental-agreements/{agreement['id']}/cancel",
        json={"reason": "Hirer changed their mind"},
    )

    rebooked = await owner.post(
        "/api/v1/rental-agreements",
        json={
            "asset_id": vehicle["id"],
            "tenant_id": second["id"],
            "start_date": in_days(1),
            "end_date": in_days(5),
            "rate_basis": "daily",
        },
    )

    assert rebooked.status_code == 201


async def test_assets_are_not_visible_across_organizations(owner: Actor, other_owner: Actor) -> None:
    vehicle = await make_vehicle(owner)

    response = await other_owner.get(f"/api/v1/assets/{vehicle['id']}")

    assert response.status_code == 403
