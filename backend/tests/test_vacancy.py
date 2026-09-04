"""Sprint 16: vacancy listings, the lead pipeline, and data export."""

from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.notification import Notification, NotificationType
from app.models.vacancy import Inquiry
from tests.conftest import Actor, unique_phone
from tests.test_portfolio import make_property, make_unit
from tests.test_screening import application_payload
from tests.test_tenancy import make_tenancy, make_tenant


async def listed_unit(owner: Actor, **unit_overrides) -> dict:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"], **unit_overrides)
    listing = await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")
    assert listing.status_code == 200, listing.text
    return {"property": prop, "unit": unit, "listing": listing.json()}


# ---------------------------------------------------------------- listings


async def test_a_vacant_unit_gets_a_shareable_link(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    slug = setup["listing"]["slug"]

    assert setup["listing"]["status"] == "published"
    assert len(slug) == 10

    public = await client.get(f"/api/v1/listings/{slug}")
    assert public.status_code == 200
    body = public.json()
    assert body["unit_number"] == setup["unit"]["unit_number"]
    assert body["property_name"] == setup["property"]["name"]
    # Nothing internal leaks into a page meant for strangers.
    assert "organization_id" not in body


async def test_an_occupied_unit_has_nothing_to_advertise(owner: Actor) -> None:
    prop = await make_property(owner)
    unit = await make_unit(owner, prop["id"])
    tenant = await make_tenant(owner)
    await make_tenancy(owner, tenant["id"], unit["id"])

    response = await owner.get(f"/api/v1/vacancies/units/{unit['id']}/listing")

    assert response.status_code == 409


async def test_letting_the_unit_closes_the_advert(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    slug = setup["listing"]["slug"]

    tenant = await make_tenant(owner)
    await make_tenancy(owner, tenant["id"], setup["unit"]["id"])

    gone = await client.get(f"/api/v1/listings/{slug}")
    assert gone.status_code == 404


async def test_an_over_shared_link_can_be_rotated(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    old_slug = setup["listing"]["slug"]

    rotated = await owner.post(f"/api/v1/vacancies/listings/{setup['listing']['id']}/rotate-link")
    assert rotated.status_code == 200
    new_slug = rotated.json()["slug"]
    assert new_slug != old_slug

    assert (await client.get(f"/api/v1/listings/{old_slug}")).status_code == 404
    assert (await client.get(f"/api/v1/listings/{new_slug}")).status_code == 200


async def test_a_draft_listing_is_not_public(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)

    await owner.patch(f"/api/v1/vacancies/listings/{setup['listing']['id']}", json={"status": "draft"})

    assert (await client.get(f"/api/v1/listings/{setup['listing']['slug']}")).status_code == 404


# -------------------------------------------------------------------- leads


async def test_anyone_can_enquire_without_an_account(owner: Actor, client: AsyncClient, db) -> None:
    setup = await listed_unit(owner)

    response = await client.post(
        f"/api/v1/listings/{setup['listing']['slug']}/inquire",
        json={
            "full_name": "Peter Njoroge",
            "phone_number": unique_phone(),
            "message": "Is it still available?",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "inquired"

    leads = (await owner.get("/api/v1/vacancies/inquiries")).json()
    assert [lead["full_name"] for lead in leads] == ["Peter Njoroge"]

    rows = list(
        await db.scalars(
            select(Notification).where(Notification.notification_type == NotificationType.INQUIRY_RECEIVED)
        )
    )
    assert rows, "both the enquirer and the office should have been messaged"


async def test_asking_twice_is_enthusiasm_not_a_second_lead(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    phone = unique_phone()
    body = {"full_name": "Peter Njoroge", "phone_number": phone}

    await client.post(f"/api/v1/listings/{setup['listing']['slug']}/inquire", json=body)
    await client.post(f"/api/v1/listings/{setup['listing']['slug']}/inquire", json=body)

    leads = (await owner.get("/api/v1/vacancies/inquiries")).json()
    assert len(leads) == 1


async def test_an_application_absorbs_the_lead_it_came_from(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    phone = unique_phone()

    await client.post(
        f"/api/v1/listings/{setup['listing']['slug']}/inquire",
        json={"full_name": "Peter Njoroge", "phone_number": phone},
    )
    await client.post(
        f"/api/v1/apply/{setup['unit']['id']}",
        json=application_payload(setup["unit"]["id"], phone_number=phone),
    )

    leads = (await owner.get("/api/v1/vacancies/inquiries")).json()
    assert len(leads) == 1
    assert leads[0]["stage"] == "applied"
    assert leads[0]["application_id"] is not None


async def test_the_pipeline_follows_the_application(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    phone = unique_phone()

    await client.post(
        f"/api/v1/listings/{setup['listing']['slug']}/inquire",
        json={"full_name": "Peter Njoroge", "phone_number": phone},
    )
    applied = await client.post(
        f"/api/v1/apply/{setup['unit']['id']}",
        json=application_payload(setup["unit"]["id"], phone_number=phone),
    )
    assert applied.status_code == 201

    applications = (await owner.get("/api/v1/applications")).json()
    await owner.post(f"/api/v1/applications/{applications[0]['id']}/review")

    leads = (await owner.get("/api/v1/vacancies/inquiries")).json()
    assert leads[0]["stage"] == "under_review"

    await owner.post(f"/api/v1/applications/{applications[0]['id']}/approve", json={})
    leads = (await owner.get("/api/v1/vacancies/inquiries")).json()
    assert leads[0]["stage"] == "approved"


async def test_a_lead_nobody_touches_goes_stale(owner: Actor, client: AsyncClient, db) -> None:
    from app.services import vacancy_service

    setup = await listed_unit(owner)
    await client.post(
        f"/api/v1/listings/{setup['listing']['slug']}/inquire",
        json={"full_name": "Peter Njoroge", "phone_number": unique_phone()},
    )

    inquiry = await db.scalar(select(Inquiry).where(Inquiry.unit_id == setup["unit"]["id"]))
    inquiry.created_at = datetime.now(UTC) - timedelta(days=5)
    inquiry.last_contacted_at = datetime.now(UTC) - timedelta(days=5)
    await db.commit()

    stale = (
        await owner.get(
            "/api/v1/vacancies/inquiries",
            params={"stale_only": True, "unit_id": setup["unit"]["id"]},
        )
    ).json()
    assert len(stale) == 1
    assert stale[0]["is_stale"] is True

    # The sweep is deliberately cross-organisation, so assert it caught ours and
    # then that it does not chase the same lead twice.
    assert await vacancy_service.chase_stale_leads(db) >= 1
    assert await vacancy_service.chase_stale_leads(db) == 0


async def test_marking_a_lead_contacted_stops_it_being_stale(owner: Actor, client: AsyncClient, db) -> None:
    setup = await listed_unit(owner)
    await client.post(
        f"/api/v1/listings/{setup['listing']['slug']}/inquire",
        json={"full_name": "Peter Njoroge", "phone_number": unique_phone()},
    )

    inquiry = await db.scalar(select(Inquiry).where(Inquiry.unit_id == setup["unit"]["id"]))
    inquiry.created_at = datetime.now(UTC) - timedelta(days=5)
    inquiry.last_contacted_at = datetime.now(UTC) - timedelta(days=5)
    await db.commit()

    updated = await owner.patch(
        f"/api/v1/vacancies/inquiries/{inquiry.id}",
        json={"mark_contacted": True, "notes": "Called, viewing on Saturday"},
    )

    assert updated.status_code == 200
    assert updated.json()["is_stale"] is False


# ------------------------------------------------------------ the vacancy desk


async def test_the_desk_counts_the_cost_of_an_empty_unit(owner: Actor, db) -> None:
    from app.models.vacancy import VacancyListing

    setup = await listed_unit(owner, monthly_rent="30000.00")

    listing = await db.scalar(select(VacancyListing).where(VacancyListing.unit_id == setup["unit"]["id"]))
    listing.vacant_since = date.today() - timedelta(days=30)
    await db.commit()

    report = (await owner.get("/api/v1/vacancies")).json()

    assert report["vacant_units"] == 1
    row = report["units"][0]
    assert row["days_vacant"] == 30
    # Thirty days of a 30,000 rent, spread over a 30-day month.
    assert row["revenue_lost"] == 30000.0
    assert report["monthly_revenue_at_risk"] == 30000.0


async def test_conversion_counts_the_funnel(owner: Actor, client: AsyncClient) -> None:
    setup = await listed_unit(owner)
    phone = unique_phone()

    await client.post(
        f"/api/v1/listings/{setup['listing']['slug']}/inquire",
        json={"full_name": "Peter Njoroge", "phone_number": phone},
    )
    await client.post(
        f"/api/v1/apply/{setup['unit']['id']}",
        json=application_payload(setup["unit"]["id"], phone_number=phone),
    )

    report = (await owner.get("/api/v1/vacancies/conversion")).json()

    assert report["inquiries"] == 1
    assert report["applications"] == 1
    assert report["inquiry_to_application_percent"] == 100.0


async def test_listings_are_not_visible_across_organizations(owner: Actor, other_owner: Actor) -> None:
    setup = await listed_unit(owner)

    response = await other_owner.patch(
        f"/api/v1/vacancies/listings/{setup['listing']['id']}", json={"headline": "Mine now"}
    )

    assert response.status_code == 403


# ------------------------------------------------------------------- export


async def test_tenants_export_as_csv(owner: Actor) -> None:
    await make_tenant(owner, full_name="Grace Wanjiku")

    response = await owner.post("/api/v1/vacancies/exports", json={"kind": "tenants", "export_format": "csv"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.content.decode("utf-8-sig")
    assert "Full name" in body
    assert "Grace Wanjiku" in body


async def test_payments_export_as_excel(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/vacancies/exports", json={"kind": "payments", "export_format": "excel"}
    )

    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    # A real xlsx is a zip, so it starts with the zip magic bytes.
    assert response.content[:2] == b"PK"


async def test_the_monthly_export_runs_for_every_organization(owner: Actor, db) -> None:
    from app.services import export_service

    await make_tenant(owner)

    built = await export_service.run_scheduled_exports(db)

    # At least this organisation got one; the sweep is deliberately global.
    assert built >= 1
    log = (await owner.get("/api/v1/vacancies/exports")).json()
    assert any(row["kind"] == "tenancies" and row["download_url"] for row in log)


async def test_every_export_is_logged(owner: Actor) -> None:
    await make_tenant(owner)
    await owner.post("/api/v1/vacancies/exports", json={"kind": "tenants"})

    log = (await owner.get("/api/v1/vacancies/exports")).json()

    assert len(log) == 1
    assert log[0]["kind"] == "tenants"
    assert log[0]["row_count"] >= 1
    assert log[0]["requested_by_name"] == owner.user["full_name"]
