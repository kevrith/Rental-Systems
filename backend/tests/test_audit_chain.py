"""Hash-chained audit log (Sprint 26A) — app/services/audit_chain_service.py."""

import uuid

from httpx import AsyncClient

from app.services import audit_chain_service
from tests.conftest import Actor, unique_phone


async def _make_tenant(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/tenants",
        json={"full_name": "Chain Test Tenant", "phone_number": unique_phone()},
    )
    assert response.status_code == 201, response.text


async def test_chain_new_entries_hashes_rows_in_order_and_is_idempotent(owner: Actor, db) -> None:
    await _make_tenant(owner)
    await _make_tenant(owner)
    org_id = uuid.UUID(owner.user["organization_id"])

    chained = await audit_chain_service.chain_new_entries(db, org_id)
    assert chained >= 2

    result = await audit_chain_service.verify_chain(db, org_id)
    assert result.intact is True
    assert result.unchained == 0
    assert result.verified == result.total

    # A second run has nothing new to do.
    again = await audit_chain_service.chain_new_entries(db, org_id)
    assert again == 0


async def test_first_entry_chains_onto_the_genesis_hash(owner: Actor, db) -> None:
    await _make_tenant(owner)
    org_id = uuid.UUID(owner.user["organization_id"])

    await audit_chain_service.chain_new_entries(db, org_id)

    from sqlalchemy import select

    from app.models.audit import AuditLog

    first = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == org_id, AuditLog.entry_hash.isnot(None))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .limit(1)
        )
    ).first()
    assert first.prev_hash == audit_chain_service.GENESIS_HASH


async def test_verify_chain_detects_a_tampered_row(owner: Actor, db) -> None:
    await _make_tenant(owner)
    org_id = uuid.UUID(owner.user["organization_id"])
    await audit_chain_service.chain_new_entries(db, org_id)

    from sqlalchemy import select

    from app.models.audit import AuditLog

    entry = (
        await db.scalars(
            select(AuditLog).where(AuditLog.organization_id == org_id).order_by(AuditLog.created_at.asc())
        )
    ).first()
    entry.summary = "This was not what actually happened"
    await db.commit()

    result = await audit_chain_service.verify_chain(db, org_id)
    assert result.intact is False
    assert result.broken_at_id == entry.id


async def test_new_rows_after_a_chain_run_extend_it_rather_than_break_it(owner: Actor, db) -> None:
    await _make_tenant(owner)
    org_id = uuid.UUID(owner.user["organization_id"])
    await audit_chain_service.chain_new_entries(db, org_id)

    await _make_tenant(owner)
    await audit_chain_service.chain_new_entries(db, org_id)

    result = await audit_chain_service.verify_chain(db, org_id)
    assert result.intact is True
    assert result.total >= 2


async def test_verify_endpoint_reports_an_intact_chain(owner: Actor, client: AsyncClient, db) -> None:
    await _make_tenant(owner)
    org_id = uuid.UUID(owner.user["organization_id"])
    await audit_chain_service.chain_new_entries(db, org_id)

    response = await owner.get("/api/v1/security/audit-log/verify")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intact"] is True
    assert body["unchained"] == 0
    assert body["total"] >= 1


async def test_chains_are_independent_per_organization(owner: Actor, other_owner: Actor, db) -> None:
    await _make_tenant(owner)
    await _make_tenant(other_owner)

    org_id = uuid.UUID(owner.user["organization_id"])
    other_org_id = uuid.UUID(other_owner.user["organization_id"])

    await audit_chain_service.chain_new_entries(db, org_id)
    await audit_chain_service.chain_new_entries(db, other_org_id)

    result = await audit_chain_service.verify_chain(db, org_id)
    other_result = await audit_chain_service.verify_chain(db, other_org_id)

    assert result.intact is True
    assert other_result.intact is True
    # Each organisation's chain accounts only for its own rows — tampering
    # with one organisation's understanding of "how many rows exist" is
    # exactly the cross-tenant leak this scoping has to rule out.
    assert result.total == result.verified
    assert other_result.total == other_result.verified
