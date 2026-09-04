"""Sprint 17: compliance calendar, parking bays, amenity booking, utility accounts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.notification import Notification, NotificationType
from tests.conftest import Actor
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenancy, make_tenant


def in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


async def occupied(owner: Actor) -> dict:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)
    tenancy = await make_tenancy(owner, tenant["id"], unit["id"])
    return {"property": prop, "unit": unit, "tenant": tenant, "tenancy": tenancy}


async def make_compliance(owner: Actor, property_id: str, **overrides) -> dict:
    payload = {
        "property_id": property_id,
        "compliance_type": "fire_safety",
        "name": "Fire safety certificate",
        "expires_on": in_days(200),
        "responsible_party": "Nairobi Fire Services",
        **overrides,
    }
    response = await owner.post("/api/v1/compliance", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ----------------------------------------------------------------- compliance


async def test_the_traffic_light_reflects_the_expiry_date(owner: Actor) -> None:
    prop = await make_property(owner)

    valid = await make_compliance(owner, prop["id"], expires_on=in_days(200))
    amber = await make_compliance(
        owner, prop["id"], compliance_type="nema", name="NEMA licence", expires_on=in_days(30)
    )
    red = await make_compliance(
        owner,
        prop["id"],
        compliance_type="lift_inspection",
        name="Lift inspection",
        expires_on=in_days(-5),
    )

    assert valid["status"] == "valid"
    assert amber["status"] == "expiring_soon"
    assert amber["days_until_expiry"] == 30
    assert red["status"] == "expired"


async def test_a_certificate_with_no_expiry_is_missing_not_valid(owner: Actor) -> None:
    prop = await make_property(owner)

    item = await make_compliance(owner, prop["id"], expires_on=None)

    # Silence is not compliance: an item with no date is flagged, not assumed fine.
    assert item["status"] == "missing"


async def test_a_certificate_cannot_expire_before_it_was_issued(owner: Actor) -> None:
    prop = await make_property(owner)

    response = await owner.post(
        "/api/v1/compliance",
        json={
            "property_id": prop["id"],
            "compliance_type": "nema",
            "name": "NEMA licence",
            "issued_on": in_days(0),
            "expires_on": in_days(-10),
        },
    )

    assert response.status_code == 422


async def test_the_dashboard_shows_the_worst_item_per_property(owner: Actor) -> None:
    prop = await make_property(owner)
    await make_compliance(owner, prop["id"], expires_on=in_days(300))
    await make_compliance(owner, prop["id"], compliance_type="nema", name="NEMA", expires_on=in_days(-1))

    dashboard = (await owner.get("/api/v1/compliance/dashboard")).json()

    row = next(item for item in dashboard["properties"] if item["property_name"] == prop["name"])
    assert row["worst"] == "expired"
    assert dashboard["needs_attention"] >= 1


async def test_the_reminder_ladder_fires_each_rung_once(owner: Actor, db) -> None:
    from app.services import facilities_service

    prop = await make_property(owner)
    await make_compliance(owner, prop["id"], expires_on=in_days(25))

    first = await facilities_service.sweep_compliance_expiry(db)
    assert first >= 1

    # Same day, same rung — nothing more to say.
    assert await facilities_service.sweep_compliance_expiry(db) == 0

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.COMPLIANCE_EXPIRY)
        )
    )
    assert any("expires in 25 day(s)" in row.body for row in rows)


async def test_renewing_a_certificate_restarts_the_ladder(owner: Actor, db) -> None:
    from app.models.facilities import ComplianceItem
    from app.services import facilities_service

    prop = await make_property(owner)
    item = await make_compliance(owner, prop["id"], expires_on=in_days(25))
    await facilities_service.sweep_compliance_expiry(db)

    renewed = await owner.patch(f"/api/v1/compliance/{item['id']}", json={"expires_on": in_days(365)})
    assert renewed.status_code == 200

    row = await db.get(ComplianceItem, item["id"])
    await db.refresh(row)
    assert row.last_reminder_days is None


async def test_the_compliance_report_renders(owner: Actor) -> None:
    prop = await make_property(owner)
    await make_compliance(owner, prop["id"])

    response = await owner.get("/api/v1/compliance/report")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


# -------------------------------------------------------------------- parking


async def test_a_bay_can_only_be_held_by_one_person(owner: Actor) -> None:
    setup = await occupied(owner)
    bay = (
        await owner.post(
            "/api/v1/parking/bays",
            json={
                "property_id": setup["property"]["id"],
                "bay_number": "P1",
                "bay_type": "covered",
                "monthly_fee": "3000.00",
            },
        )
    ).json()

    first = await owner.post(
        f"/api/v1/parking/bays/{bay['id']}/allocate",
        json={"tenancy_id": setup["tenancy"]["id"], "start_date": date.today().isoformat()},
    )
    assert first.status_code == 201, first.text

    second = await owner.post(
        f"/api/v1/parking/bays/{bay['id']}/allocate",
        json={
            "guest_name": "A visitor",
            "start_date": date.today().isoformat(),
            "end_date": in_days(1),
        },
    )
    assert second.status_code == 409
    assert "already allocated" in second.json()["detail"]


async def test_releasing_a_bay_frees_it(owner: Actor) -> None:
    setup = await occupied(owner)
    bay = (
        await owner.post(
            "/api/v1/parking/bays",
            json={"property_id": setup["property"]["id"], "bay_number": "P2"},
        )
    ).json()
    allocation = (
        await owner.post(
            f"/api/v1/parking/bays/{bay['id']}/allocate",
            json={"tenancy_id": setup["tenancy"]["id"], "start_date": date.today().isoformat()},
        )
    ).json()

    released = await owner.post(f"/api/v1/parking/allocations/{allocation['id']}/release")
    assert released.status_code == 200

    again = await owner.post(
        f"/api/v1/parking/bays/{bay['id']}/allocate",
        json={"tenancy_id": setup["tenancy"]["id"], "start_date": date.today().isoformat()},
    )
    assert again.status_code == 201


async def test_a_visitor_allocation_needs_an_end_date(owner: Actor) -> None:
    setup = await occupied(owner)
    bay = (
        await owner.post(
            "/api/v1/parking/bays",
            json={"property_id": setup["property"]["id"], "bay_number": "P3"},
        )
    ).json()

    response = await owner.post(
        f"/api/v1/parking/bays/{bay['id']}/allocate",
        json={"guest_name": "Passing visitor", "start_date": date.today().isoformat()},
    )

    assert response.status_code == 422


async def test_the_parking_fee_lands_on_the_rent_invoice(owner: Actor) -> None:
    setup = await occupied(owner)
    bay = (
        await owner.post(
            "/api/v1/parking/bays",
            json={
                "property_id": setup["property"]["id"],
                "bay_number": "P4",
                "monthly_fee": "4000.00",
            },
        )
    ).json()
    await owner.post(
        f"/api/v1/parking/bays/{bay['id']}/allocate",
        json={"tenancy_id": setup["tenancy"]["id"], "start_date": date.today().isoformat()},
    )

    invoice = (
        await owner.post("/api/v1/invoices/generate", json={"tenancy_id": setup["tenancy"]["id"]})
    ).json()

    parking = [line for line in invoice["line_items"] if "Parking bay P4" in line["description"]]
    assert len(parking) == 1
    assert Decimal(parking[0]["amount"]) == Decimal("4000.00")


async def test_the_parking_overview_counts_income_and_availability(owner: Actor) -> None:
    setup = await occupied(owner)
    for number in ("A", "B", "C"):
        await owner.post(
            "/api/v1/parking/bays",
            json={
                "property_id": setup["property"]["id"],
                "bay_number": number,
                "monthly_fee": "2500.00",
            },
        )

    bays = (await owner.get(f"/api/v1/parking/property/{setup['property']['id']}")).json()
    first_bay = bays["bays"][0]
    await owner.post(
        f"/api/v1/parking/bays/{first_bay['bay_id']}/allocate",
        json={"tenancy_id": setup["tenancy"]["id"], "start_date": date.today().isoformat()},
    )

    overview = (await owner.get(f"/api/v1/parking/property/{setup['property']['id']}")).json()

    assert overview["total_bays"] == 3
    assert overview["allocated"] == 1
    assert overview["available"] == 2
    assert overview["monthly_parking_income"] == 2500.0


# ------------------------------------------------------------------ amenities


async def make_amenity(owner: Actor, property_id: str, **overrides) -> dict:
    payload = {
        "property_id": property_id,
        "name": "Rooftop",
        "kind": "rooftop",
        "max_hours_per_booking": 4,
        "min_notice_hours": 2,
        "max_bookings_per_week": 2,
        "opens_at_hour": 8,
        "closes_at_hour": 22,
        **overrides,
    }
    response = await owner.post("/api/v1/amenities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def slot(days_ahead: int, hour: int, length: int = 2) -> dict:
    start = (datetime.now(UTC) + timedelta(days=days_ahead)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return {
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=length)).isoformat(),
    }


async def test_a_booking_blocks_the_slot_for_everyone_else(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"])

    first = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(2, 14), "tenancy_id": setup["tenancy"]["id"], "purpose": "Birthday"},
    )
    assert first.status_code == 201, first.text

    # An overlapping window, not an identical one.
    clash = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(2, 15), "tenancy_id": setup["tenancy"]["id"]},
    )
    assert clash.status_code == 409
    assert "already taken" in clash.json()["detail"]


async def test_a_booking_cannot_exceed_the_maximum_duration(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"], max_hours_per_booking=2)

    response = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(2, 10, length=5), "tenancy_id": setup["tenancy"]["id"]},
    )

    assert response.status_code == 409
    assert "at most 2 hour(s)" in response.json()["detail"]


async def test_a_booking_needs_the_required_notice(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"], min_notice_hours=24)

    start = datetime.now(UTC) + timedelta(hours=1)
    response = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=1)).isoformat(),
            "tenancy_id": setup["tenancy"]["id"],
        },
    )

    assert response.status_code == 409
    assert "24 hour(s) notice" in response.json()["detail"]


async def test_a_tenant_cannot_exceed_their_weekly_allowance(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"], max_bookings_per_week=1)

    first = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(1, 10), "tenancy_id": setup["tenancy"]["id"]},
    )
    assert first.status_code == 201, first.text

    second = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(1, 14), "tenancy_id": setup["tenancy"]["id"]},
    )

    assert second.status_code == 409
    assert "which is the limit" in second.json()["detail"]


async def test_a_maintenance_block_stops_bookings(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"])

    blocked = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/block",
        json={**slot(3, 9, length=8), "reason": "Deep clean"},
    )
    assert blocked.status_code == 201
    assert blocked.json()["status"] == "blocked"

    response = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(3, 12), "tenancy_id": setup["tenancy"]["id"]},
    )
    assert response.status_code == 409


async def test_cancelling_frees_the_slot(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"])

    booking = (
        await owner.post(
            f"/api/v1/amenities/{amenity['id']}/bookings",
            json={**slot(4, 10), "tenancy_id": setup["tenancy"]["id"]},
        )
    ).json()
    await owner.post(f"/api/v1/amenities/bookings/{booking['id']}/cancel")

    again = await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(4, 10), "tenancy_id": setup["tenancy"]["id"]},
    )
    assert again.status_code == 201


async def test_the_tenant_is_told_their_booking_is_confirmed(owner: Actor, db) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"])

    await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(5, 16), "tenancy_id": setup["tenancy"]["id"], "purpose": "Family lunch"},
    )

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.AMENITY_BOOKING)
        )
    )
    assert any("Rooftop" in row.body for row in rows)


async def test_usage_counts_hours_booked(owner: Actor) -> None:
    setup = await occupied(owner)
    amenity = await make_amenity(owner, setup["property"]["id"], max_bookings_per_week=10)

    await owner.post(
        f"/api/v1/amenities/{amenity['id']}/bookings",
        json={**slot(6, 10, length=3), "tenancy_id": setup["tenancy"]["id"]},
    )

    usage = (await owner.get(f"/api/v1/amenities/usage/{setup['property']['id']}")).json()

    row = next(item for item in usage if item["amenity_id"] == amenity["id"])
    assert row["bookings"] == 1
    assert row["hours_booked"] == 3.0
    assert row["distinct_tenants"] == 1


# ------------------------------------------------------------ utility accounts


async def test_a_utility_account_starts_as_unknown(owner: Actor) -> None:
    prop = await make_property(owner)

    account = (
        await owner.put(
            "/api/v1/utilities",
            json={
                "property_id": prop["id"],
                "account_type": "kplc",
                "account_number": "0123456789",
                "provider": "Kenya Power",
            },
        )
    ).json()

    # Nobody has checked, and saying so is more honest than assuming.
    assert account["payment_status"] == "unknown"
    assert account["is_overdue"] is False


async def test_an_overdue_bill_is_flagged_and_the_nag_backs_off(owner: Actor, db) -> None:
    from app.services import facilities_service

    prop = await make_property(owner)
    account = (
        await owner.put(
            "/api/v1/utilities",
            json={
                "property_id": prop["id"],
                "account_type": "water",
                "account_number": "W-999",
                "next_due_on": in_days(-3),
            },
        )
    ).json()

    fetched = (await owner.get("/api/v1/utilities", params={"property_id": prop["id"]})).json()
    assert fetched[0]["is_overdue"] is True

    alerted = await facilities_service.sweep_overdue_utilities(db)
    assert alerted >= 1

    # The due date is pushed a week, so this nags weekly rather than nightly.
    after = (await owner.get("/api/v1/utilities", params={"property_id": prop["id"]})).json()
    assert after[0]["is_overdue"] is False

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.UTILITY_OVERDUE)
        )
    )
    assert any("W-999" in row.body for row in rows)
    assert account["account_number"] == "W-999"


async def test_marking_it_paid_records_who_and_when(owner: Actor) -> None:
    prop = await make_property(owner)
    account = (
        await owner.put(
            "/api/v1/utilities",
            json={"property_id": prop["id"], "account_type": "kplc", "account_number": "K-1"},
        )
    ).json()

    updated = await owner.post(
        f"/api/v1/utilities/{account['id']}/status",
        json={
            "payment_status": "paid",
            "last_paid_on": date.today().isoformat(),
            "last_amount": "12500.00",
            "next_due_on": in_days(30),
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["payment_status"] == "paid"
    assert body["status_updated_at"] is not None
    assert Decimal(body["last_amount"]) == Decimal("12500.00")


async def test_facilities_are_not_visible_across_organizations(owner: Actor, other_owner: Actor) -> None:
    prop = await make_property(owner)
    item = await make_compliance(owner, prop["id"])

    response = await other_owner.patch(f"/api/v1/compliance/{item['id']}", json={"name": "Mine now"})

    assert response.status_code == 403
