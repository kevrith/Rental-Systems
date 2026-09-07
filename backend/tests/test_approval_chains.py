"""Configurable approval chains (Sprint 26A, item 13) — app/services/approval_service.py."""

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.deps import OrgContext
from app.models.approval import ApprovalActionType, ApprovalRequestStatus
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services import approval_service
from tests.conftest import Actor, unique_phone


async def _second_operator(owner: Actor, db, role: UserRole = UserRole.PROPERTY_MANAGER) -> User:
    user = User(
        organization_id=uuid.UUID(owner.user["organization_id"]),
        full_name="Second Operator",
        email=f"operator-{uuid.uuid4().hex[:8]}@example.com",
        phone_number=unique_phone(),
        password_hash="not-a-real-hash",
        role=role,
        is_active=True,
        is_email_verified=True,
        is_phone_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _context_for(db, user: User) -> OrgContext:
    org = await db.get(Organization, user.organization_id)
    return OrgContext(user=user, organization=org)


async def test_create_and_list_rules(owner: Actor) -> None:
    created = await owner.post(
        "/api/v1/approvals/rules",
        json={
            "entity_type": "large_expense",
            "name": "Large expense sign-off",
            "threshold": "50000.00",
            "required_approver_roles": ["owner"],
            "required_approvals": 1,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["entity_type"] == "large_expense"
    assert Decimal(body["threshold"]) == Decimal("50000.00")

    listed = await owner.get("/api/v1/approvals/rules")
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [body["id"]]


async def test_evaluate_returns_none_below_threshold(owner: Actor, db) -> None:
    await _second_operator(owner, db)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))

    rule_response = await owner.post(
        "/api/v1/approvals/rules",
        json={"entity_type": "large_expense", "name": "Rule", "threshold": "1000.00"},
    )
    assert rule_response.status_code == 201

    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("500.00")
    )
    assert request is None


async def test_evaluate_creates_a_request_above_threshold(owner: Actor, db) -> None:
    await _second_operator(owner, db)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))

    await owner.post(
        "/api/v1/approvals/rules",
        json={"entity_type": "large_expense", "name": "Rule", "threshold": "1000.00"},
    )

    entity_id = uuid.uuid4()
    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=entity_id, trigger_value=Decimal("5000.00")
    )
    assert request is not None
    assert request.status == ApprovalRequestStatus.PENDING
    assert request.entity_id == entity_id
    assert request.required_approvals == 1


async def test_evaluate_skips_when_no_other_approver_exists(owner: Actor, db) -> None:
    """A solo landlord who configures a rule is not locked out of their own action."""
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))

    await owner.post(
        "/api/v1/approvals/rules",
        json={"entity_type": "large_expense", "name": "Rule", "threshold": "1000.00"},
    )

    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("5000.00")
    )
    assert request is None


async def test_requester_cannot_approve_their_own_request(owner: Actor, db) -> None:
    await _second_operator(owner, db)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))
    await owner.post(
        "/api/v1/approvals/rules", json={"entity_type": "large_expense", "name": "Rule", "threshold": "0"}
    )
    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("5000.00")
    )
    assert request is not None
    await db.commit()

    response = await owner.post(f"/api/v1/approvals/{request.id}/approve", json={})
    assert response.status_code == 403


async def test_second_operator_can_approve_and_it_resolves_the_request(owner: Actor, db) -> None:
    operator = await _second_operator(owner, db)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))
    await owner.post(
        "/api/v1/approvals/rules", json={"entity_type": "large_expense", "name": "Rule", "threshold": "0"}
    )
    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("5000.00")
    )
    assert request is not None

    resolved = await approval_service.act(
        db, await _context_for(db, operator), request.id, ApprovalActionType.APPROVE, "Looks fine"
    )
    assert resolved.status == ApprovalRequestStatus.APPROVED
    assert resolved.resolved_at is not None


async def test_a_rejection_resolves_the_request_as_rejected(owner: Actor, db) -> None:
    operator = await _second_operator(owner, db)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))
    await owner.post(
        "/api/v1/approvals/rules", json={"entity_type": "large_expense", "name": "Rule", "threshold": "0"}
    )
    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("5000.00")
    )
    assert request is not None

    operator_context = await _context_for(db, operator)
    resolved = await approval_service.act(
        db, operator_context, request.id, ApprovalActionType.REJECT, "Not justified"
    )
    assert resolved.status == ApprovalRequestStatus.REJECTED


async def test_multi_approver_requests_need_all_required_approvals(owner: Actor, db) -> None:
    first = await _second_operator(owner, db)
    second = await _second_operator(owner, db, role=UserRole.ACCOUNTANT)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))

    await owner.post(
        "/api/v1/approvals/rules",
        json={"entity_type": "large_expense", "name": "Rule", "threshold": "0", "required_approvals": 2},
    )
    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("5000.00")
    )
    assert request is not None
    assert request.required_approvals == 2

    after_first = await approval_service.act(
        db, await _context_for(db, first), request.id, ApprovalActionType.APPROVE, None
    )
    assert after_first.status == ApprovalRequestStatus.PENDING

    after_second = await approval_service.act(
        db, await _context_for(db, second), request.id, ApprovalActionType.APPROVE, None
    )
    assert after_second.status == ApprovalRequestStatus.APPROVED


async def test_the_same_actor_cannot_approve_twice(owner: Actor, db) -> None:
    first = await _second_operator(owner, db)
    context = await _context_for(db, await db.get(User, uuid.UUID(owner.user["id"])))
    await owner.post(
        "/api/v1/approvals/rules",
        json={"entity_type": "large_expense", "name": "Rule", "threshold": "0", "required_approvals": 2},
    )
    request = await approval_service.evaluate(
        db, context, entity_type="large_expense", entity_id=uuid.uuid4(), trigger_value=Decimal("5000.00")
    )
    assert request is not None

    first_context = await _context_for(db, first)
    await approval_service.act(db, first_context, request.id, ApprovalActionType.APPROVE, None)

    with pytest.raises(HTTPException) as exc_info:
        await approval_service.act(db, first_context, request.id, ApprovalActionType.APPROVE, None)
    assert exc_info.value.status_code == 409
