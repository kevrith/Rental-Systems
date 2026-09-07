"""Data subject access & erasure requests (Sprint 25, US-106).

Scoped to tenants — the subjects the Kenya Data Protection Act section of the
masterplan is actually about, and the vast majority of people whose data a
RentFlow organisation holds. A staff user's own equivalent rights already have
a working path: `/auth/me/delete` (US-004, Sprint 1) for erasure, and a
dedicated self-export endpoint added alongside this model for the export half.
Duplicating a second `DataRequest` row for that would just be bookkeeping
without a workflow behind it.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DataRequestType(str, enum.Enum):
    EXPORT = "export"
    ERASURE = "erasure"


class DataRequestStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class DataRequest(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One subject access or erasure request against a tenant's record.

    Processed synchronously — export is a read, and erasure only ever redacts
    the tenant's own PII (financial and audit records the law requires be kept
    are untouched), so there is nothing here that needs a review queue. The row
    exists for the audit trail an enterprise buyer's compliance team expects:
    who asked, when, and what was done about it.
    """

    __tablename__ = "data_requests"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_type: Mapped[DataRequestType] = mapped_column(
        Enum(DataRequestType, name="data_request_type"), nullable=False
    )
    status: Mapped[DataRequestStatus] = mapped_column(
        Enum(DataRequestStatus, name="data_request_status"),
        default=DataRequestStatus.COMPLETED,
        nullable=False,
    )
    # Null when the tenant raised this themselves from the portal.
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    export_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
