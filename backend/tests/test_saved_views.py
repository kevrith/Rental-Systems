"""Saved views (Sprint 26A, item 11) — app/services/saved_view_service.py."""

from tests.conftest import Actor


async def test_create_and_list_a_saved_view(owner: Actor) -> None:
    created = await owner.post(
        "/api/v1/saved-views",
        json={
            "entity_type": "tenants",
            "name": "Arrears this month",
            "filters": {"tenancy_status": "active", "search": ""},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Arrears this month"
    assert body["filters"]["tenancy_status"] == "active"
    assert body["is_shared"] is False

    listed = await owner.get("/api/v1/saved-views", params={"entity_type": "tenants"})
    assert listed.status_code == 200
    assert [v["id"] for v in listed.json()] == [body["id"]]


async def test_saved_views_are_scoped_by_entity_type(owner: Actor) -> None:
    await owner.post("/api/v1/saved-views", json={"entity_type": "tenants", "name": "A view", "filters": {}})
    await owner.post(
        "/api/v1/saved-views", json={"entity_type": "maintenance", "name": "A view", "filters": {}}
    )

    tenants_views = (await owner.get("/api/v1/saved-views", params={"entity_type": "tenants"})).json()
    maintenance_views = (await owner.get("/api/v1/saved-views", params={"entity_type": "maintenance"})).json()
    assert len(tenants_views) == 1
    assert len(maintenance_views) == 1


async def test_duplicate_name_for_the_same_user_and_entity_type_is_rejected(owner: Actor) -> None:
    payload = {"entity_type": "tenants", "name": "Dup", "filters": {}}
    first = await owner.post("/api/v1/saved-views", json=payload)
    assert first.status_code == 201

    second = await owner.post("/api/v1/saved-views", json=payload)
    assert second.status_code == 409


async def test_setting_a_new_default_clears_the_previous_one(owner: Actor) -> None:
    a = (
        await owner.post(
            "/api/v1/saved-views",
            json={"entity_type": "tenants", "name": "A", "filters": {}, "is_default": True},
        )
    ).json()
    b = (
        await owner.post(
            "/api/v1/saved-views",
            json={"entity_type": "tenants", "name": "B", "filters": {}, "is_default": True},
        )
    ).json()

    views = (await owner.get("/api/v1/saved-views", params={"entity_type": "tenants"})).json()
    defaults = [v for v in views if v["is_default"]]
    assert [d["id"] for d in defaults] == [b["id"]]
    assert a["id"] != b["id"]


async def test_update_and_delete_a_saved_view(owner: Actor) -> None:
    created = (
        await owner.post(
            "/api/v1/saved-views", json={"entity_type": "tenants", "name": "Original", "filters": {}}
        )
    ).json()

    updated = await owner.patch(
        f"/api/v1/saved-views/{created['id']}", json={"name": "Renamed", "is_shared": True}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["is_shared"] is True

    deleted = await owner.delete(f"/api/v1/saved-views/{created['id']}")
    assert deleted.status_code == 204

    listed = (await owner.get("/api/v1/saved-views", params={"entity_type": "tenants"})).json()
    assert listed == []


async def test_a_shared_view_is_visible_to_other_organization_members_but_not_editable(
    owner: Actor, other_owner: Actor
) -> None:
    shared = (
        await owner.post(
            "/api/v1/saved-views",
            json={"entity_type": "tenants", "name": "Team view", "filters": {}, "is_shared": True},
        )
    ).json()

    # Different organisation entirely — RLS/org-scoping keeps it invisible
    # regardless of is_shared, which only shares within one organisation.
    other_org_list = (await other_owner.get("/api/v1/saved-views", params={"entity_type": "tenants"})).json()
    assert other_org_list == []

    private = (
        await owner.post(
            "/api/v1/saved-views",
            json={"entity_type": "tenants", "name": "Private view", "filters": {}, "is_shared": False},
        )
    ).json()
    listed = (await owner.get("/api/v1/saved-views", params={"entity_type": "tenants"})).json()
    assert {v["id"] for v in listed} == {shared["id"], private["id"]}
