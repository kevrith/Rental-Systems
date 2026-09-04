"""Sprint 2: properties, units, bulk creation, status lifecycle, uploads, dashboard."""

from httpx import AsyncClient

from tests.conftest import Actor


async def make_property(actor: Actor, **overrides) -> dict:
    payload = {
        "name": "Kilimani Heights",
        "property_type": "residential",
        "address": "Kilimani Road, Nairobi",
        "county": "Nairobi",
        "amenities": ["parking", "borehole"],
        "water_rate_per_unit": "150.00",
    }
    payload.update(overrides)
    response = await actor.post("/api/v1/properties", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def make_unit(actor: Actor, property_id: str, **overrides) -> dict:
    payload = {
        "property_id": property_id,
        "unit_number": "A1",
        "unit_type": "1 bedroom",
        "bedrooms": 1,
        "bathrooms": 1,
        "monthly_rent": "25000.00",
        "deposit_amount": "25000.00",
    }
    payload.update(overrides)
    response = await actor.post("/api/v1/units", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------- properties


async def test_property_gets_a_reference_code(owner: Actor) -> None:
    record = await make_property(owner)

    assert record["reference_code"].startswith("PRP-")
    assert len(record["reference_code"]) == 10
    assert record["amenities"] == ["parking", "borehole"]


async def test_property_appears_in_the_portfolio_immediately(owner: Actor) -> None:
    await make_property(owner, name="Westlands Court")

    listed = await owner.get("/api/v1/properties")
    assert listed.status_code == 200
    assert [p["name"] for p in listed.json()] == ["Westlands Court"]


async def test_property_search_matches_name_and_address(owner: Actor) -> None:
    await make_property(owner, name="Westlands Court", address="Ring Road")
    await make_property(owner, name="Kilimani Heights", address="Argwings Kodhek")

    found = await owner.get("/api/v1/properties", params={"search": "Ring"})
    assert [p["name"] for p in found.json()] == ["Westlands Court"]


async def test_property_can_be_updated(owner: Actor) -> None:
    record = await make_property(owner)

    response = await owner.patch(
        f"/api/v1/properties/{record['id']}", json={"name": "Renamed", "county": "Kiambu"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["county"] == "Kiambu"


async def test_edits_are_written_to_the_audit_log(owner: Actor) -> None:
    record = await make_property(owner)
    await owner.patch(f"/api/v1/properties/{record['id']}", json={"name": "Renamed"})

    log = await owner.get("/api/v1/activity", params={"entity_type": "property", "entity_id": record["id"]})
    actions = [entry["action"] for entry in log.json()]
    assert "property.created" in actions
    assert "property.updated" in actions


# ------------------------------------------------------------------------ units


async def test_unit_defaults_to_vacant(owner: Actor) -> None:
    record = await make_property(owner)
    unit = await make_unit(owner, record["id"])

    assert unit["status"] == "vacant"
    assert unit["reference_code"].startswith("UNT-")


async def test_duplicate_unit_number_in_the_same_property_is_rejected(owner: Actor) -> None:
    record = await make_property(owner)
    await make_unit(owner, record["id"], unit_number="A1")

    response = await owner.post(
        "/api/v1/units",
        json={"property_id": record["id"], "unit_number": "A1", "monthly_rent": "1000"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_bulk_creation_makes_sequentially_named_units(owner: Actor) -> None:
    """'This property has 24 identical units' (US-008)."""
    record = await make_property(owner)

    response = await owner.post(
        "/api/v1/units/bulk",
        json={
            "property_id": record["id"],
            "count": 24,
            "name_prefix": "A",
            "start_number": 1,
            "number_padding": 2,
            "monthly_rent": "18000.00",
            "bedrooms": 1,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 24

    numbers = [u["unit_number"] for u in body["units"]]
    assert numbers[0] == "A01"
    assert numbers[-1] == "A24"
    assert all(u["status"] == "vacant" for u in body["units"])
    assert len({u["reference_code"] for u in body["units"]}) == 24


async def test_bulk_creation_refuses_to_collide_with_existing_units(owner: Actor) -> None:
    record = await make_property(owner)
    await make_unit(owner, record["id"], unit_number="A01")

    response = await owner.post(
        "/api/v1/units/bulk",
        json={"property_id": record["id"], "count": 3, "name_prefix": "A", "number_padding": 2},
    )
    assert response.status_code == 409
    assert "A01" in response.json()["detail"]


async def test_units_are_listed_under_their_property(owner: Actor) -> None:
    record = await make_property(owner)
    await owner.post("/api/v1/units/bulk", json={"property_id": record["id"], "count": 5, "name_prefix": "B"})

    listed = await owner.get(f"/api/v1/properties/{record['id']}/units")
    assert listed.status_code == 200
    assert len(listed.json()) == 5


# --------------------------------------------------------------- status lifecycle


async def test_status_change_to_vacant_stamps_the_vacancy_date(owner: Actor) -> None:
    record = await make_property(owner)
    unit = await make_unit(owner, record["id"])

    await owner.patch(f"/api/v1/units/{unit['id']}/status", json={"status": "under_maintenance"})
    response = await owner.patch(f"/api/v1/units/{unit['id']}/status", json={"status": "vacant"})

    assert response.status_code == 200
    assert response.json()["status"] == "vacant"
    assert response.json()["vacancy_date"] is not None


async def test_a_unit_cannot_be_marked_occupied_without_a_tenancy(owner: Actor) -> None:
    """Occupancy follows the tenancy, so it can't be asserted by hand (US-010)."""
    record = await make_property(owner)
    unit = await make_unit(owner, record["id"])

    response = await owner.patch(f"/api/v1/units/{unit['id']}/status", json={"status": "occupied"})

    assert response.status_code == 409
    assert "Create a tenancy" in response.json()["detail"]


async def test_vacating_status_requires_an_expected_date(owner: Actor) -> None:
    record = await make_property(owner)
    unit = await make_unit(owner, record["id"])

    response = await owner.patch(f"/api/v1/units/{unit['id']}/status", json={"status": "vacating"})
    assert response.status_code == 422


async def test_status_changes_land_in_the_audit_log(owner: Actor) -> None:
    record = await make_property(owner)
    unit = await make_unit(owner, record["id"])
    await owner.patch(
        f"/api/v1/units/{unit['id']}/status",
        json={"status": "under_maintenance", "note": "Leaking roof"},
    )

    log = await owner.get("/api/v1/activity", params={"entity_type": "unit", "entity_id": unit["id"]})
    entry = next(e for e in log.json() if e["action"] == "unit.status_changed")
    assert "vacant → under_maintenance" in entry["summary"]


# --------------------------------------------------------------------- archiving


async def test_archiving_a_property_hides_it_from_active_views(owner: Actor) -> None:
    record = await make_property(owner)

    archived = await owner.delete(f"/api/v1/properties/{record['id']}")
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    assert (await owner.get("/api/v1/properties")).json() == []

    with_archived = await owner.get("/api/v1/properties", params={"include_archived": True})
    assert len(with_archived.json()) == 1


async def test_archived_property_can_be_restored(owner: Actor) -> None:
    record = await make_property(owner)
    await owner.delete(f"/api/v1/properties/{record['id']}")

    restored = await owner.post(f"/api/v1/properties/{record['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False


# --------------------------------------------------------------------- dashboard


async def test_portfolio_dashboard_totals_units_and_occupancy(owner: Actor) -> None:
    first = await make_property(owner, name="Property One")
    second = await make_property(owner, name="Property Two")
    await owner.post(
        "/api/v1/units/bulk",
        json={"property_id": first["id"], "count": 4, "name_prefix": "A", "monthly_rent": "10000"},
    )
    await owner.post(
        "/api/v1/units/bulk",
        json={"property_id": second["id"], "count": 6, "name_prefix": "B", "monthly_rent": "20000"},
    )

    response = await owner.get("/api/v1/dashboard/portfolio")

    assert response.status_code == 200
    stats = response.json()["stats"]
    assert stats["total_properties"] == 2
    assert stats["total_units"] == 10
    assert stats["vacant_units"] == 10
    assert stats["occupancy_rate"] == 0.0
    assert float(stats["monthly_rent_potential"]) == 4 * 10000 + 6 * 20000
    assert len(response.json()["properties"]) == 2


async def test_property_cards_carry_their_own_breakdown(owner: Actor) -> None:
    record = await make_property(owner)
    await owner.post(
        "/api/v1/units/bulk",
        json={"property_id": record["id"], "count": 3, "name_prefix": "C", "monthly_rent": "5000"},
    )

    card = (await owner.get(f"/api/v1/properties/{record['id']}")).json()
    assert card["total_units"] == 3
    assert card["vacant_units"] == 3
    assert float(card["monthly_rent_potential"]) == 15000


# ------------------------------------------------------------------- file upload


async def test_upload_is_presigned_then_confirmed(owner: Actor, client: AsyncClient) -> None:
    """Bytes go straight to storage; the API only brokers the URL (US-012)."""
    ticket = await owner.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "frontage.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 2048,
            "category": "property_photo",
        },
    )
    assert ticket.status_code == 201, ticket.text
    body = ticket.json()
    assert body["method"] == "PUT"
    assert body["expires_in"] == 3600

    uploaded = await client.put(body["upload_url"], content=b"x" * 2048)
    assert uploaded.status_code == 200

    confirmed = await owner.post(f"/api/v1/files/{body['file_id']}/confirm", json={"size_bytes": 2048})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "uploaded"
    assert confirmed.json()["url"]


async def test_confirming_without_uploading_fails(owner: Actor) -> None:
    ticket = await owner.post(
        "/api/v1/files/upload-url",
        json={"filename": "a.pdf", "content_type": "application/pdf", "size_bytes": 100},
    )
    response = await owner.post(f"/api/v1/files/{ticket.json()['file_id']}/confirm", json={})

    assert response.status_code == 400
    assert "did not complete" in response.json()["detail"]


async def test_unsupported_file_type_is_rejected(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/files/upload-url",
        json={"filename": "virus.exe", "content_type": "application/x-msdownload", "size_bytes": 10},
    )
    assert response.status_code == 415


async def test_oversized_file_is_rejected(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "huge.pdf",
            "content_type": "application/pdf",
            "size_bytes": 11 * 1024 * 1024,
        },
    )
    assert response.status_code == 413
    assert "10MB" in response.json()["detail"]


async def test_batch_upload_enforces_the_total_limit(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/files/upload-url/batch",
        json={
            "files": [
                {"filename": f"p{i}.jpg", "content_type": "image/jpeg", "size_bytes": 9 * 1024 * 1024}
                for i in range(6)
            ]
        },
    )
    assert response.status_code == 413
    assert "50MB" in response.json()["detail"]


async def test_photos_attach_to_a_property(owner: Actor, client: AsyncClient) -> None:
    ticket = (
        await owner.post(
            "/api/v1/files/upload-url",
            json={
                "filename": "front.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 64,
                "category": "property_photo",
            },
        )
    ).json()
    await client.put(ticket["upload_url"], content=b"x" * 64)
    await owner.post(f"/api/v1/files/{ticket['file_id']}/confirm", json={})

    record = await make_property(owner, photo_file_ids=[ticket["file_id"]])

    detail = await owner.get(f"/api/v1/properties/{record['id']}")
    assert len(detail.json()["photos"]) == 1
    assert detail.json()["photos"][0]["filename"] == "front.jpg"


async def test_files_from_another_organization_are_not_readable(owner: Actor, other_owner: Actor) -> None:
    ticket = (
        await owner.post(
            "/api/v1/files/upload-url",
            json={"filename": "x.pdf", "content_type": "application/pdf", "size_bytes": 10},
        )
    ).json()

    response = await other_owner.get(f"/api/v1/files/{ticket['file_id']}")
    assert response.status_code == 403


async def test_units_from_another_organization_are_not_reachable(owner: Actor, other_owner: Actor) -> None:
    record = await make_property(owner)
    unit = await make_unit(owner, record["id"])

    assert (await other_owner.get(f"/api/v1/units/{unit['id']}")).status_code == 403
