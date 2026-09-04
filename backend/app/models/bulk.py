"""Bulk operations: one action, many tenants (US-071, US-072, US-073).

Every bulk action is recorded as a row before it runs. That matters for three
reasons: the preview and the execution have to agree on exactly who is affected,
a half-finished run has to be readable afterwards, and "who put everyone's rent
up by 10% in March" is a question that must have an answer.

Rows are kept whether the run succeeded or failed, and the per-target outcome is
stored alongside so a failure names the tenant it failed on.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BulkOperationKind(str, enum.Enum):
    RENT_INCREASE = "rent_increase"
    PAYMENT_REMINDER = "payment_reminder"
    ANNOUNCEMENT = "announcement"
    GENERATE_INVOICES = "generate_invoices"
    RENEWAL_NOTICES = "renewal_notices"
    DOCUMENT_DISTRIBUTION = "document_distribution"
    TENANT_IMPORT = "tenant_import"


class BulkOperationStatus(str, enum.Enum):
    # Previewed but not yet run — the operator has seen who is affected.
    PREVIEWED = "previewed"
    RUNNING = "running"
    COMPLETED = "completed"
    # Some targets failed; the run still finished and the reasons are recorded.
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BulkOperation(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bulk_operations"

    kind: Mapped[BulkOperationKind] = mapped_column(
        Enum(BulkOperationKind, name="bulk_operation_kind"), nullable=False, index=True
    )
    status: Mapped[BulkOperationStatus] = mapped_column(
        Enum(BulkOperationStatus, name="bulk_operation_status"),
        default=BulkOperationStatus.PREVIEWED,
        nullable=False,
        index=True,
    )

    # What the operator asked for — the percentage, the message text, the file id.
    # Kept verbatim so the run can be explained and, if need be, repeated.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # The preview: exactly which targets this will touch, resolved at preview time
    # so execution cannot quietly widen its blast radius.
    targets: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # One entry per target that did not succeed, with the reason.
    failures: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    @property
    def progress_percent(self) -> int:
        if not self.total:
            return 0
        return round((self.succeeded + self.failed) / self.total * 100)
