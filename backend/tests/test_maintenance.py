"""Sprint 13: the vendor registry and the full maintenance lifecycle."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.notification import Notification, NotificationType
from tests.conftest import Actor, unique_phone
from tests.test_operations import occupied_unit


async def make_vendor(owner: Actor, **overrides) -> dict:
    payload = {
        "name": "John Mwangi",
        "specialties": ["plumbing"],
        "phone_number": unique_phone(),
        "rate_notes": "KES 1,500 callout",
        **overrides,
    }
    response = await owner.post("/api/v1/vendors", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def make_request(owner: Actor, setup: dict, **overrides) -> dict:
    payload = {
        "unit_id": setup["unit"]["id"],
        "title": "Kitchen tap leaking",
        "description": "Constant drip under the sink",
        "category": "plumbing",
        **overrides,
    }
    response = await owner.post("/api/v1/maintenance", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------- registry


async def test_vendor_phone_is_unique_within_the_organization(owner: Actor) -> None:
    vendor = await make_vendor(owner)

    duplicate = await owner.post(
        "/api/v1/vendors",
        json={"name": "Someone else", "specialties": ["electrical"], "phone_number": vendor["phone_number"]},
    )

    assert duplicate.status_code == 409
    assert "already on your list" in duplicate.json()["detail"]


async def test_vendors_filter_by_the_category_they_can_answer(owner: Actor) -> None:
    plumber = await make_vendor(owner, name="Plumber", specialties=["plumbing"])
    await make_vendor(owner, name="Painter", specialties=["painting"])

    response = await owner.get("/api/v1/vendors", params={"category": "plumbing"})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [plumber["id"]]


async def test_a_vendor_with_work_in_progress_cannot_be_deactivated(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    vendor = await make_vendor(owner)
    request = await make_request(owner, setup)

    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={"vendor_id": vendor["id"]})

    response = await owner.post(f"/api/v1/vendors/{vendor['id']}/deactivate")

    assert response.status_code == 409
    assert "Reassign them first" in response.json()["detail"]


async def test_vendors_are_not_visible_across_organizations(owner: Actor, other_owner: Actor) -> None:
    vendor = await make_vendor(owner)

    response = await other_owner.get(f"/api/v1/vendors/{vendor['id']}")

    assert response.status_code == 403


# ------------------------------------------------------------------ lifecycle


async def test_full_lifecycle_from_submission_to_close(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    vendor = await make_vendor(owner)
    request = await make_request(owner, setup)
    assert request["status"] == "submitted"

    approved = (
        await owner.post(
            f"/api/v1/maintenance/{request['id']}/approve",
            json={
                "estimated_cost": "3000.00",
                "expected_completion_date": (date.today() + timedelta(days=3)).isoformat(),
                "vendor_id": vendor["id"],
            },
        )
    ).json()
    # Approving with a vendor lands directly on assigned — one action, one WhatsApp.
    assert approved["status"] == "assigned"
    assert approved["vendor"]["id"] == vendor["id"]
    assert Decimal(approved["estimated_cost"]) == Decimal("3000.00")

    started = (await owner.post(f"/api/v1/maintenance/{request['id']}/start")).json()
    assert started["status"] == "in_progress"

    completed = (
        await owner.post(
            f"/api/v1/maintenance/{request['id']}/complete",
            json={"actual_cost": "3500.00", "resolution_notes": "New washer", "vendor_rating": 5},
        )
    ).json()
    assert completed["status"] == "completed"
    assert Decimal(completed["cost_variance"]) == Decimal("500.00")

    closed = (await owner.post(f"/api/v1/maintenance/{request['id']}/close")).json()
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None

    # The vendor's counters moved with the job.
    detail = (await owner.get(f"/api/v1/vendors/{vendor['id']}")).json()
    assert detail["jobs_completed"] == 1
    assert detail["average_rating"] == 5.0
    assert Decimal(detail["total_billed"]) == Decimal("3500.00")


async def test_an_invalid_transition_is_refused(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)

    response = await owner.post(
        f"/api/v1/maintenance/{request['id']}/complete", json={"actual_cost": "100.00"}
    )

    assert response.status_code == 409
    assert "cannot become" in response.json()["detail"]


async def test_a_closed_job_is_terminal(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)

    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})
    await owner.post(f"/api/v1/maintenance/{request['id']}/start")
    await owner.post(f"/api/v1/maintenance/{request['id']}/complete", json={"actual_cost": "100.00"})
    await owner.post(f"/api/v1/maintenance/{request['id']}/close")

    response = await owner.post(f"/api/v1/maintenance/{request['id']}/start")

    assert response.status_code == 409
    assert "closed" in response.json()["detail"]


async def test_a_job_cannot_be_closed_before_its_cost_is_known(owner: Actor, db) -> None:
    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)

    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})
    await owner.post(f"/api/v1/maintenance/{request['id']}/start")

    response = await owner.post(f"/api/v1/maintenance/{request['id']}/close")

    assert response.status_code == 409
    assert "actual cost" in response.json()["detail"]


async def test_rejection_requires_a_note_when_the_reason_is_other(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)

    response = await owner.post(f"/api/v1/maintenance/{request['id']}/reject", json={"reason": "other"})

    assert response.status_code == 422


async def test_rejection_records_the_reason(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)

    rejected = (
        await owner.post(
            f"/api/v1/maintenance/{request['id']}/reject",
            json={"reason": "tenant_caused_damage", "note": "Door forced open"},
        )
    ).json()

    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "tenant_caused_damage"
    assert rejected["rejection_note"] == "Door forced open"


async def test_assigning_a_vendor_sends_them_the_job(owner: Actor, db) -> None:
    setup = await occupied_unit(owner)
    vendor = await make_vendor(owner)
    request = await make_request(owner, setup)

    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})
    await owner.post(f"/api/v1/maintenance/{request['id']}/assign", json={"vendor_id": vendor["id"]})

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.VENDOR_ASSIGNED)
        )
    )
    assert rows, "the vendor should have been messaged"
    assert any(vendor["phone_number"] in (row.recipient or "") for row in rows)
    assert any(request["title"] in row.body for row in rows)


async def test_the_timeline_records_every_decision(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)

    await owner.post(f"/api/v1/maintenance/{request['id']}/review")
    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})

    detail = (await owner.get(f"/api/v1/maintenance/{request['id']}")).json()
    actions = [entry["action"] for entry in detail["timeline"]]

    assert "maintenance.submitted" in actions
    assert "maintenance.review_started" in actions
    assert "maintenance.approved" in actions


# ------------------------------------------------------------------- overdue


async def test_the_sweep_flags_jobs_past_their_due_date(owner: Actor, db) -> None:
    from app.models.operations import MaintenanceRequest
    from app.services import maintenance_service

    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)
    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})

    record = await db.get(MaintenanceRequest, request["id"])
    record.expected_completion_date = date.today() - timedelta(days=2)
    await db.commit()

    flagged = await maintenance_service.flag_overdue_jobs(db, notify=False)
    assert flagged == 1

    detail = (await owner.get(f"/api/v1/maintenance/{request['id']}")).json()
    assert detail["is_overdue"] is True

    # A second sweep must not re-flag the same job.
    assert await maintenance_service.flag_overdue_jobs(db, notify=False) == 0


async def test_completing_a_job_clears_the_overdue_flag(owner: Actor, db) -> None:
    from app.models.operations import MaintenanceRequest
    from app.services import maintenance_service

    setup = await occupied_unit(owner)
    request = await make_request(owner, setup)
    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})

    record = await db.get(MaintenanceRequest, request["id"])
    record.expected_completion_date = date.today() - timedelta(days=1)
    await db.commit()
    await maintenance_service.flag_overdue_jobs(db, notify=False)

    await owner.post(f"/api/v1/maintenance/{request['id']}/start")
    completed = (
        await owner.post(f"/api/v1/maintenance/{request['id']}/complete", json={"actual_cost": "900.00"})
    ).json()

    assert completed["is_overdue"] is False


# ------------------------------------------------------------------ analytics


async def test_analytics_reports_cost_by_property_and_category(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    vendor = await make_vendor(owner)

    for title, cost in (("Tap", "1000.00"), ("Pipe", "2000.00")):
        request = await make_request(owner, setup, title=title)
        await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={"vendor_id": vendor["id"]})
        await owner.post(
            f"/api/v1/maintenance/{request['id']}/complete",
            json={"actual_cost": cost, "vendor_rating": 4},
        )

    body = (await owner.get("/api/v1/maintenance/analytics")).json()

    assert body["this_month_cost"] == 3000.0
    assert body["by_property"][0]["property_name"] == setup["property"]["name"]
    assert body["by_property"][0]["total_cost"] == 3000.0

    plumbing = next(row for row in body["by_category"] if row["category"] == "plumbing")
    assert plumbing["jobs"] == 2

    top = body["top_vendors"][0]
    assert top["jobs_completed"] == 2
    assert top["average_cost"] == 1500.0
    assert top["average_rating"] == 4.0


async def test_budget_variance_is_reported_against_the_property_allowance(owner: Actor) -> None:
    setup = await occupied_unit(owner)
    await owner.patch(
        f"/api/v1/properties/{setup['property']['id']}",
        json={"maintenance_budget_monthly": "5000.00"},
    )

    request = await make_request(owner, setup)
    approved = await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    # No vendor: the caretaker handled it in-house, straight from approved to done.
    completed = await owner.post(
        f"/api/v1/maintenance/{request['id']}/complete", json={"actual_cost": "6000.00"}
    )
    assert completed.status_code == 200, completed.text

    body = (await owner.get("/api/v1/maintenance/analytics")).json()
    row = body["by_property"][0]

    assert row["monthly_budget"] == 5000.0
    assert row["budget_variance"] == -1000.0
    assert row["over_budget"] is True


async def test_expensive_units_are_ranked_against_their_rent(owner: Actor) -> None:
    setup = await occupied_unit(owner)

    request = await make_request(owner, setup)
    await owner.post(f"/api/v1/maintenance/{request['id']}/approve", json={})
    completed = await owner.post(
        f"/api/v1/maintenance/{request['id']}/complete", json={"actual_cost": "12000.00"}
    )
    assert completed.status_code == 200, completed.text

    body = (await owner.get("/api/v1/maintenance/analytics", params={"months": 12})).json()
    unit_row = body["expensive_units"][0]

    assert unit_row["unit_number"] == setup["unit"]["unit_number"]
    assert unit_row["total_cost"] == 12000.0
    assert unit_row["cost_to_rent_percent"] is not None
