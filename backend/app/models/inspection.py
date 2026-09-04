"""Inspection models — Phase 2 (US-049, US-050, US-051, US-052).

InspectionReport captures room-by-room condition with photos.
Immutable once submitted — tamper-evident evidence for disputes.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenancy


class InspectionType(str, enum.Enum):
    MOVE_IN = "move_in"
    MOVE_OUT = "move_out"
    ROUTINE = "routine"


class InspectionStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class RoomCondition(str, enum.Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class InspectionReport(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A property condition assessment at a point in time.

    `rooms_data` is a JSON array of room objects:
    [{"name": "Living Room", "condition": "good", "notes": "...", "photo_file_ids": [...]}]

    Immutable once submitted — `submitted_at` is set and the record is never
    mutated again. The comparison engine reads two submitted reports side-by-side.
    """

    __tablename__ = "inspection_reports"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    inspection_type: Mapped[InspectionType] = mapped_column(
        Enum(InspectionType, name="inspection_type"), nullable=False, index=True
    )
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="inspection_status"),
        default=InspectionStatus.DRAFT,
        nullable=False,
    )

    # Room-by-room data stored as JSON for flexibility
    rooms_data: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Inspector details
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    inspector_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gps_latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated PDF report
    report_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    # Comparison PDF (move-out only, references the move-in report)
    comparison_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    move_in_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_reports.id", ondelete="SET NULL"), nullable=True
    )

    # Deposit deduction (move-out only)
    deposit_deduction: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    deduction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tenant acknowledgment
    tenant_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tenant_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenancy: Mapped["Tenancy | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_inspection_ref_per_org"),
    )
