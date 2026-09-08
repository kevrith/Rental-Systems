"""Document vault storage limit — app/services/file_service.py."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.models.organization import Organization, SubscriptionPlan
from tests.conftest import Actor
from tests.test_customer_success import make_platform_staff


async def _request_upload(actor: Actor, size_bytes: int, filename: str = "doc.pdf"):
    return await actor.post(
        "/api/v1/files/upload-url",
        json={
            "filename": filename,
            "content_type": "application/pdf",
            "size_bytes": size_bytes,
            "category": "other",
        },
    )


async def _upload_and_confirm(actor: Actor, client: AsyncClient, size_bytes: int, filename: str = "doc.pdf"):
    """The quota only counts confirmed uploads (`UploadStatus.UPLOADED`) — a
    PENDING row from `request_upload` alone is an abandoned-upload shape the
    rest of the codebase already ignores everywhere, so the test has to go
    through the real three-step flow to actually move the needle on usage."""
    response = await _request_upload(actor, size_bytes, filename)
    if response.status_code != 201:
        return response
    ticket = response.json()
    await client.put(ticket["upload_url"], content=b"x" * size_bytes)
    return await actor.post(f"/api/v1/files/{ticket['file_id']}/confirm", json={})


async def test_a_trial_organization_gets_the_starter_default_limit(owner: Actor) -> None:
    response = await owner.get("/api/v1/vault/usage")
    assert response.status_code == 200, response.text
    assert response.json()["limit_bytes"] == 5 * 1024 * 1024 * 1024


async def test_upload_is_rejected_once_it_would_exceed_the_limit(
    owner: Actor, client: AsyncClient, db
) -> None:
    organization = await db.get(Organization, uuid.UUID(owner.user["organization_id"]))
    organization.storage_limit_bytes = 1000
    await db.commit()

    within_limit = await _upload_and_confirm(owner, client, 400, "small.pdf")
    assert within_limit.status_code == 200, within_limit.text

    over_limit = await _request_upload(owner, 700, "too-big.pdf")
    assert over_limit.status_code == 413, over_limit.text
    assert "storage" in over_limit.json()["detail"].lower()


async def test_existing_files_are_not_touched_when_the_limit_is_hit(
    owner: Actor, client: AsyncClient, db
) -> None:
    organization = await db.get(Organization, uuid.UUID(owner.user["organization_id"]))
    organization.storage_limit_bytes = 500
    await db.commit()

    first = await _upload_and_confirm(owner, client, 400, "keep-me.pdf")
    assert first.status_code == 200, first.text

    rejected = await _request_upload(owner, 400, "rejected.pdf")
    assert rejected.status_code == 413

    usage = await owner.get("/api/v1/vault/usage")
    assert usage.json()["total_bytes"] == 400


async def test_platform_staff_can_set_and_clear_the_enterprise_override(owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    org_id = owner.user["organization_id"]

    set_response = await owner.patch(
        f"/api/v1/internal/organizations/{org_id}/plan",
        json={"plan": "enterprise", "storage_limit_bytes": 999_000_000_000},
    )
    assert set_response.status_code == 200, set_response.text

    organization = await db.get(Organization, uuid.UUID(org_id))
    await db.refresh(organization)
    assert organization.subscription_plan == SubscriptionPlan.ENTERPRISE
    assert organization.storage_limit_bytes == 999_000_000_000

    usage = await owner.get("/api/v1/vault/usage")
    assert usage.json()["limit_bytes"] == 999_000_000_000

    cleared = await owner.patch(
        f"/api/v1/internal/organizations/{org_id}/plan",
        json={"plan": "enterprise", "storage_limit_bytes": None},
    )
    assert cleared.status_code == 200
    await db.refresh(organization)
    assert organization.storage_limit_bytes is None

    # Enterprise with no override is unlimited.
    usage_after_clear = await owner.get("/api/v1/vault/usage")
    assert usage_after_clear.json()["limit_bytes"] is None


async def test_omitting_storage_limit_bytes_leaves_the_existing_value_alone(owner: Actor, db) -> None:
    await make_platform_staff(db, owner)
    org_id = owner.user["organization_id"]

    await owner.patch(
        f"/api/v1/internal/organizations/{org_id}/plan",
        json={"plan": "enterprise", "storage_limit_bytes": 42_000},
    )

    unrelated_update = await owner.patch(
        f"/api/v1/internal/organizations/{org_id}/plan", json={"plan": "enterprise"}
    )
    assert unrelated_update.status_code == 200

    organization = await db.scalar(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    assert organization.storage_limit_bytes == 42_000
