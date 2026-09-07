import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.approval import ApprovalActionType, ApprovalRequestStatus


class ApprovalRuleCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    threshold: Decimal | None = Field(default=None, ge=0)
    required_approver_roles: list[str] = Field(default_factory=list)
    required_approvals: int = Field(default=1, ge=1, le=10)
    is_active: bool = True


class ApprovalRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    threshold: Decimal | None = None
    required_approver_roles: list[str] | None = None
    required_approvals: int | None = Field(default=None, ge=1, le=10)
    is_active: bool | None = None


class ApprovalRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    name: str
    threshold: Decimal | None
    required_approver_roles: list[str]
    required_approvals: int
    is_active: bool
    created_at: datetime


class ApprovalActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_name: str | None
    action: ApprovalActionType
    note: str | None
    created_at: datetime


class ApprovalRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    requested_by_name: str | None
    trigger_value: Decimal | None
    note: str | None
    required_approvals: int
    required_approver_roles: list[str]
    status: ApprovalRequestStatus
    resolved_at: datetime | None
    context: dict[str, Any] | None
    created_at: datetime


class ApprovalRequestDetail(ApprovalRequestRead):
    actions: list[ApprovalActionRead] = Field(default_factory=list)


class ApprovalActRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
