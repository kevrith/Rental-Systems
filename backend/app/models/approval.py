"""Configurable approval chains (Sprint 26A, item 13).

Generalises the maker-checker pattern this codebase already has two one-off
copies of — cash payment dual approval (`payment_service.py`,
`cash_dual_approval_threshold`) and maintenance cost sign-off
(`operations.py`) — into a reusable framework any future threshold-gated
action can plug into, instead of writing its own approval fields and its own
copy of "the approver cannot be the requester." The two existing flows are
deliberately not migrated onto this in the same pass: both are tested,
working, and load-bearing for real money, and a big-bang rewrite of either is
its own separate, carefully-reviewed change, not a side effect of adding a
new, unrelated capability.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ApprovalRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalActionType(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalRule(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """When `entity_type` needs sign-off, and by whom.

    `entity_type` is a free string the calling feature defines
    (`"cash_payment"`, `"maintenance_expense"`, ...) — this table has no
    opinion on what kinds of things get approved, only on the mechanics of
    approving them. `threshold` is compared against whatever numeric value
    the caller passes to `approval_service.evaluate` — null means "always
    requires approval," not "no threshold configured." At most one active
    rule per `(organization_id, entity_type)` is enforced in the service
    layer, not a database constraint, since deactivating one rule before
    activating its replacement is a normal two-step edit.
    """

    __tablename__ = "approval_rules"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Role values (`UserRole`), stored as plain strings — an eligible
    # approver holds one of these roles. Empty means "any operator role."
    required_approver_roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApprovalRequest(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One pending-or-resolved approval on one entity.

    `required_approvals` and `required_approver_roles` are copied from the
    rule at creation time rather than read live off it, so editing a rule
    later never silently changes what an in-flight request needs.
    """

    __tablename__ = "approval_requests"

    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_rules.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trigger_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False)
    required_approver_roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        Enum(ApprovalRequestStatus, name="approval_request_status"),
        default=ApprovalRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class ApprovalAction(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One approve/reject by one person on one request."""

    __tablename__ = "approval_actions"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[ApprovalActionType] = mapped_column(
        Enum(ApprovalActionType, name="approval_action_type"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
