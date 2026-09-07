"""Configurable approval chains (Sprint 26A, item 13) — see app/models/approval.py.

`evaluate` is what a feature calls at the point where it would otherwise
gate an action behind its own bespoke threshold check: it returns the
`ApprovalRequest` if one was created, or `None` if no active rule applies, the
trigger value is under threshold, or — matching the reasoning
`payment_service._needs_dual_approval` already established — no other
eligible approver exists in the organisation, in which case blocking the
action would only lock out a solo operator, not add safety.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, assert_in_org
from app.models.approval import (
    ApprovalAction,
    ApprovalActionType,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRule,
)
from app.models.user import User
from app.schemas.approval import ApprovalRuleCreate, ApprovalRuleUpdate


async def get_active_rule(
    db: AsyncSession, organization_id: uuid.UUID, entity_type: str
) -> ApprovalRule | None:
    return await db.scalar(
        select(ApprovalRule).where(
            ApprovalRule.organization_id == organization_id,
            ApprovalRule.entity_type == entity_type,
            ApprovalRule.is_active.is_(True),
        )
    )


async def _other_eligible_approver_exists(
    db: AsyncSession, context: OrgContext, required_roles: list[str]
) -> bool:
    query = select(User.id).where(
        User.organization_id == context.organization_id,
        User.id != context.user.id,
        User.is_active.is_(True),
        User.deleted_at.is_(None),
    )
    if required_roles:
        query = query.where(User.role.in_(required_roles))
    return await db.scalar(query.limit(1)) is not None


async def evaluate(
    db: AsyncSession,
    context: OrgContext,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    trigger_value: Decimal | None,
    note: str | None = None,
    context_data: dict[str, Any] | None = None,
) -> ApprovalRequest | None:
    rule = await get_active_rule(db, context.organization_id, entity_type)
    if rule is None:
        return None
    if rule.threshold is not None and (trigger_value is None or trigger_value <= rule.threshold):
        return None
    if not await _other_eligible_approver_exists(db, context, rule.required_approver_roles):
        return None

    request = ApprovalRequest(
        organization_id=context.organization_id,
        rule_id=rule.id,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_by_id=context.user.id,
        requested_by_name=context.user.full_name,
        trigger_value=trigger_value,
        note=note,
        required_approvals=rule.required_approvals,
        required_approver_roles=rule.required_approver_roles,
        context=context_data,
    )
    db.add(request)
    await db.flush()
    return request


async def act(
    db: AsyncSession,
    context: OrgContext,
    request_id: uuid.UUID,
    action: ApprovalActionType,
    note: str | None,
) -> ApprovalRequest:
    request = assert_in_org(await db.get(ApprovalRequest, request_id), context, label="approval request")

    if request.status != ApprovalRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This request has already been resolved"
        )
    if request.requested_by_id == context.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You cannot act on a request you made yourself"
        )
    if request.required_approver_roles and context.role.value not in request.required_approver_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Your role cannot act on this request"
        )
    already_acted = await db.scalar(
        select(ApprovalAction.id).where(
            ApprovalAction.request_id == request.id, ApprovalAction.actor_id == context.user.id
        )
    )
    if already_acted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You have already acted on this request"
        )

    db.add(
        ApprovalAction(
            organization_id=context.organization_id,
            request_id=request.id,
            actor_id=context.user.id,
            actor_name=context.user.full_name,
            action=action,
            note=note,
        )
    )
    await db.flush()

    if action == ApprovalActionType.REJECT:
        request.status = ApprovalRequestStatus.REJECTED
        request.resolved_at = datetime.now(UTC)
    else:
        approvals = await db.scalar(
            select(func.count(ApprovalAction.id)).where(
                ApprovalAction.request_id == request.id,
                ApprovalAction.action == ApprovalActionType.APPROVE,
            )
        )
        if (approvals or 0) >= request.required_approvals:
            request.status = ApprovalRequestStatus.APPROVED
            request.resolved_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(request)
    return request


async def list_requests(
    db: AsyncSession,
    context: OrgContext,
    *,
    entity_type: str | None = None,
    approval_status: ApprovalRequestStatus | None = None,
) -> list[ApprovalRequest]:
    query = select(ApprovalRequest).where(ApprovalRequest.organization_id == context.organization_id)
    if entity_type:
        query = query.where(ApprovalRequest.entity_type == entity_type)
    if approval_status:
        query = query.where(ApprovalRequest.status == approval_status)
    return list(await db.scalars(query.order_by(ApprovalRequest.created_at.desc())))


async def get_request_with_actions(
    db: AsyncSession, context: OrgContext, request_id: uuid.UUID
) -> tuple[ApprovalRequest, list[ApprovalAction]]:
    request = assert_in_org(await db.get(ApprovalRequest, request_id), context, label="approval request")
    actions = list(
        await db.scalars(
            select(ApprovalAction)
            .where(ApprovalAction.request_id == request.id)
            .order_by(ApprovalAction.created_at)
        )
    )
    return request, actions


# ------------------------------------------------------------------------- rules


async def list_rules(db: AsyncSession, context: OrgContext) -> list[ApprovalRule]:
    query = select(ApprovalRule).where(ApprovalRule.organization_id == context.organization_id)
    return list(await db.scalars(query.order_by(ApprovalRule.entity_type, ApprovalRule.name)))


async def create_rule(db: AsyncSession, context: OrgContext, payload: ApprovalRuleCreate) -> ApprovalRule:
    rule = ApprovalRule(organization_id=context.organization_id, **payload.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(
    db: AsyncSession, context: OrgContext, rule_id: uuid.UUID, payload: ApprovalRuleUpdate
) -> ApprovalRule:
    rule = assert_in_org(await db.get(ApprovalRule, rule_id), context, label="approval rule")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, context: OrgContext, rule_id: uuid.UUID) -> None:
    rule = assert_in_org(await db.get(ApprovalRule, rule_id), context, label="approval rule")
    await db.delete(rule)
    await db.commit()
