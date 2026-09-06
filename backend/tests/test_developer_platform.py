"""Sprint 19: API keys, the public REST API, and outbound webhooks."""

from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import Actor
from tests.test_portfolio import make_property, make_unit
from tests.test_tenancy import make_tenant

# ------------------------------------------------------------------ API keys


async def create_api_key(actor: Actor, *, scopes: list[str], name: str = "Integration") -> dict:
    response = await actor.post("/api/v1/developer/api-keys", json={"name": name, "scopes": scopes})
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_api_key_returns_raw_key_once_and_list_masks_it(owner: Actor) -> None:
    created = await create_api_key(owner, scopes=["properties:read"])
    assert created["api_key"].startswith("rf_live_")
    assert created["key_prefix"] in created["api_key"]

    listed = await owner.get("/api/v1/developer/api-keys")
    assert listed.status_code == 200
    assert "api_key" not in listed.json()[0]


async def test_revoke_api_key_marks_it_revoked(owner: Actor) -> None:
    created = await create_api_key(owner, scopes=["properties:read"])

    revoked = await owner.post(f"/api/v1/developer/api-keys/{created['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None


# ------------------------------------------------------------------ public API


async def test_api_key_grants_scoped_read_access(owner: Actor, client: AsyncClient) -> None:
    prop = await make_property(owner)
    created = await create_api_key(owner, scopes=["properties:read"])

    response = await client.get("/api/v1/external/properties", headers={"X-API-Key": created["api_key"]})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {row["id"] for row in body["data"]} == {prop["id"]}
    assert "next_cursor" in body["meta"]


async def test_api_key_field_selection(owner: Actor, client: AsyncClient) -> None:
    prop = await make_property(owner)
    created = await create_api_key(owner, scopes=["properties:read"])

    response = await client.get(
        "/api/v1/external/properties",
        params={"fields": "id"},
        headers={"X-API-Key": created["api_key"]},
    )
    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row == {"id": prop["id"]}


async def test_api_key_without_required_scope_is_forbidden(owner: Actor, client: AsyncClient) -> None:
    await make_property(owner)
    created = await create_api_key(owner, scopes=["properties:read"])

    response = await client.get("/api/v1/external/units", headers={"X-API-Key": created["api_key"]})
    assert response.status_code == 403
    assert response.json()["status"] == "error"


async def test_missing_api_key_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/v1/external/properties")
    assert response.status_code == 401
    assert response.json()["status"] == "error"


async def test_revoked_api_key_is_rejected(owner: Actor, client: AsyncClient) -> None:
    created = await create_api_key(owner, scopes=["properties:read"])
    await owner.post(f"/api/v1/developer/api-keys/{created['id']}/revoke")

    response = await client.get("/api/v1/external/properties", headers={"X-API-Key": created["api_key"]})
    assert response.status_code == 401


async def test_api_key_cannot_see_another_organizations_data(
    owner: Actor, other_owner: Actor, client: AsyncClient
) -> None:
    await make_property(other_owner)
    mine = await make_property(owner)
    created = await create_api_key(owner, scopes=["properties:read"])

    response = await client.get("/api/v1/external/properties", headers={"X-API-Key": created["api_key"]})
    ids = {row["id"] for row in response.json()["data"]}
    assert ids == {mine["id"]}


async def test_rate_limit_enforced(owner: Actor, client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "API_KEY_DEFAULT_RATE_LIMIT_PER_HOUR", 2)
    created = await create_api_key(owner, scopes=["properties:read"])
    headers = {"X-API-Key": created["api_key"]}

    assert (await client.get("/api/v1/external/properties", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/external/properties", headers=headers)).status_code == 200
    limited = await client.get("/api/v1/external/properties", headers=headers)
    assert limited.status_code == 429
    assert limited.json()["status"] == "error"


async def test_get_unit_by_id_is_scoped_to_organization(
    owner: Actor, other_owner: Actor, client: AsyncClient
) -> None:
    other_prop = await make_property(other_owner)
    other_unit = await make_unit(other_owner, other_prop["id"])
    created = await create_api_key(owner, scopes=["units:read"])

    response = await client.get(
        f"/api/v1/external/units/{other_unit['id']}", headers={"X-API-Key": created["api_key"]}
    )
    assert response.status_code == 404


# -------------------------------------------------------------------- webhooks


async def create_webhook(actor: Actor, *, events: list[str], url: str = "https://example.com/hook") -> dict:
    response = await actor.post("/api/v1/developer/webhooks", json={"url": url, "event_types": events})
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_webhook_returns_secret_once(owner: Actor) -> None:
    created = await create_webhook(owner, events=["tenant.created"])
    assert created["secret"]

    revealed = await owner.get(f"/api/v1/developer/webhooks/{created['id']}/secret")
    assert revealed.status_code == 200
    assert revealed.json()["secret"] == created["secret"]


async def test_webhook_endpoint_cap_enforced(owner: Actor) -> None:
    for index in range(settings.WEBHOOK_MAX_PER_ORG):
        await create_webhook(owner, events=["tenant.created"], url=f"https://example.com/hook-{index}")

    response = await owner.post(
        "/api/v1/developer/webhooks",
        json={"url": "https://example.com/one-too-many", "event_types": ["tenant.created"]},
    )
    assert response.status_code == 400


async def test_webhook_rejects_non_https_url(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/developer/webhooks",
        json={"url": "http://example.com/hook", "event_types": ["tenant.created"]},
    )
    assert response.status_code == 422


async def test_tenant_created_queues_a_webhook_delivery(owner: Actor) -> None:
    endpoint = await create_webhook(owner, events=["tenant.created"])

    await make_tenant(owner)

    deliveries = await owner.get(f"/api/v1/developer/webhooks/{endpoint['id']}/deliveries")
    assert deliveries.status_code == 200
    rows = deliveries.json()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "tenant.created"
    assert rows[0]["status"] == "pending"


async def test_webhook_not_subscribed_to_event_receives_nothing(owner: Actor) -> None:
    endpoint = await create_webhook(owner, events=["payment.received"])

    await make_tenant(owner)

    deliveries = await owner.get(f"/api/v1/developer/webhooks/{endpoint['id']}/deliveries")
    assert deliveries.json() == []


async def test_archived_webhook_endpoint_is_hidden_from_list(owner: Actor) -> None:
    endpoint = await create_webhook(owner, events=["tenant.created"])

    archived = await owner.post(f"/api/v1/developer/webhooks/{endpoint['id']}/archive")
    assert archived.status_code == 200

    listed = await owner.get("/api/v1/developer/webhooks")
    assert listed.json() == []
