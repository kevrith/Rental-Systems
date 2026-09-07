import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.approval import ApprovalActionType, ApprovalRequest, ApprovalRequestStatus, ApprovalRule
from app.schemas.approval import (
    ApprovalActionRead,
    ApprovalActRequest,
    ApprovalRequestDetail,
    ApprovalRequestRead,
    ApprovalRuleCreate,
    ApprovalRuleRead,
    ApprovalRuleUpdate,
)
from app.services import approval_service

router = APIRouter()


@router.get("/rules", response_model=list[ApprovalRuleRead])
async def list_approval_rules(
    context: OrgContext = Depends(require(Permission.APPROVAL_RULE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRule]:
    return await approval_service.list_rules(db, context)


@router.post("/rules", response_model=ApprovalRuleRead, status_code=status.HTTP_201_CREATED)
async def create_approval_rule(
    payload: ApprovalRuleCreate,
    context: OrgContext = Depends(require(Permission.APPROVAL_RULE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRule:
    return await approval_service.create_rule(db, context, payload)


@router.patch("/rules/{rule_id}", response_model=ApprovalRuleRead)
async def update_approval_rule(
    rule_id: uuid.UUID,
    payload: ApprovalRuleUpdate,
    context: OrgContext = Depends(require(Permission.APPROVAL_RULE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRule:
    return await approval_service.update_rule(db, context, rule_id, payload)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_approval_rule(
    rule_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.APPROVAL_RULE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await approval_service.delete_rule(db, context, rule_id)


@router.get("", response_model=list[ApprovalRequestRead])
async def list_approval_requests(
    entity_type: str | None = None,
    request_status: ApprovalRequestStatus | None = Query(default=None, alias="status"),
    context: OrgContext = Depends(require(Permission.APPROVAL_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequest]:
    return await approval_service.list_requests(
        db, context, entity_type=entity_type, approval_status=request_status
    )


@router.get("/{request_id}", response_model=ApprovalRequestDetail)
async def get_approval_request(
    request_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.APPROVAL_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestDetail:
    request, actions = await approval_service.get_request_with_actions(db, context, request_id)
    return ApprovalRequestDetail(
        **ApprovalRequestRead.model_validate(request).model_dump(),
        actions=[ApprovalActionRead.model_validate(action) for action in actions],
    )


@router.post("/{request_id}/approve", response_model=ApprovalRequestRead)
async def approve_request(
    request_id: uuid.UUID,
    payload: ApprovalActRequest,
    context: OrgContext = Depends(require(Permission.APPROVAL_ACT)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    return await approval_service.act(db, context, request_id, ApprovalActionType.APPROVE, payload.note)


@router.post("/{request_id}/reject", response_model=ApprovalRequestRead)
async def reject_request(
    request_id: uuid.UUID,
    payload: ApprovalActRequest,
    context: OrgContext = Depends(require(Permission.APPROVAL_ACT)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    return await approval_service.act(db, context, request_id, ApprovalActionType.REJECT, payload.note)
