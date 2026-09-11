import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
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
    from app.models.property import Unit
    from app.models.vendor import Vendor

ZERO = Decimal("0.00")


class MeterType(str, enum.Enum):
    WATER = "water"
    ELECTRICITY = "electricity"


class MeterReading(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A monthly utility reading. Consumption and amount are computed at capture
    time so a later rate change never silently rewrites past bills (US-026)."""

    __tablename__ = "meter_readings"

    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meter_type: Mapped[MeterType] = mapped_column(Enum(MeterType, name="meter_type"), nullable=False)

    previous_reading: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    current_reading: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    consumption: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=ZERO, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    reading_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    photo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set once the reading has been rolled into an invoice line item.
    billed_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )

    # --- camera OCR (Module 5) ---
    # What the OCR pass read off `photo_file_id`, and how sure it was. Kept
    # alongside the human figure rather than replacing it: the caretaker always
    # confirms or corrects the number, so `current_reading` is what a person
    # asserted and these two are the evidence of what the machine proposed.
    ocr_reading: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # True when the submitted reading matched the OCR suggestion exactly. Null
    # when no OCR was run at all, which is not the same as a rejected suggestion.
    ocr_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # True when a high-confidence OCR reading overrode the value the caretaker
    # typed. The photo is the authoritative evidence; this flag makes that
    # override auditable without rewriting the caretaker's original input.
    photo_reading_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    unit: Mapped["Unit"] = relationship()

    __table_args__ = (
        UniqueConstraint("unit_id", "meter_type", "reading_date", name="uq_reading_per_unit_per_day"),
    )


class MaintenanceCategory(str, enum.Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    STRUCTURAL = "structural"
    APPLIANCE = "appliance"
    SECURITY = "security"
    OTHER = "other"


class MaintenancePriority(str, enum.Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"


class MaintenanceStatus(str, enum.Enum):
    """The full job lifecycle (US-061).

    `UNDER_REVIEW` replaced the earlier `ACKNOWLEDGED` when approval and vendor
    assignment were introduced — the Sprint 13 migration rewrites existing rows.
    `CLOSED` exists separately from `COMPLETED` so the money side (final cost
    recorded, expense allocated to the owner) has a state of its own.
    """

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


# The state machine. A transition not listed here is refused with a 409 rather
# than silently applied, which is what keeps the audit trail meaningful.
ALLOWED_TRANSITIONS: dict[MaintenanceStatus, tuple[MaintenanceStatus, ...]] = {
    MaintenanceStatus.SUBMITTED: (
        MaintenanceStatus.UNDER_REVIEW,
        MaintenanceStatus.APPROVED,
        MaintenanceStatus.REJECTED,
        MaintenanceStatus.CANCELLED,
    ),
    MaintenanceStatus.UNDER_REVIEW: (
        MaintenanceStatus.APPROVED,
        MaintenanceStatus.REJECTED,
        MaintenanceStatus.CANCELLED,
    ),
    MaintenanceStatus.APPROVED: (
        MaintenanceStatus.ASSIGNED,
        MaintenanceStatus.IN_PROGRESS,
        # An approved job handled in-house by the caretaker never gets a vendor,
        # so it has to be able to finish without passing through `assigned`.
        MaintenanceStatus.COMPLETED,
        MaintenanceStatus.CANCELLED,
    ),
    MaintenanceStatus.ASSIGNED: (
        MaintenanceStatus.IN_PROGRESS,
        MaintenanceStatus.COMPLETED,
        MaintenanceStatus.CANCELLED,
    ),
    MaintenanceStatus.IN_PROGRESS: (
        MaintenanceStatus.COMPLETED,
        MaintenanceStatus.CANCELLED,
    ),
    MaintenanceStatus.COMPLETED: (MaintenanceStatus.CLOSED,),
    # Terminal.
    MaintenanceStatus.REJECTED: (),
    MaintenanceStatus.CLOSED: (),
    MaintenanceStatus.CANCELLED: (),
}

# A completed job's cost is real money whether or not the request has been
# formally closed, so every cost report counts both states.
BILLABLE_STATUSES: tuple[MaintenanceStatus, ...] = (
    MaintenanceStatus.COMPLETED,
    MaintenanceStatus.CLOSED,
)

OPEN_STATUSES: tuple[MaintenanceStatus, ...] = (
    MaintenanceStatus.SUBMITTED,
    MaintenanceStatus.UNDER_REVIEW,
    MaintenanceStatus.APPROVED,
    MaintenanceStatus.ASSIGNED,
    MaintenanceStatus.IN_PROGRESS,
)


class RejectionReason(str, enum.Enum):
    NOT_LANDLORD_RESPONSIBILITY = "not_landlord_responsibility"
    TENANT_CAUSED_DAMAGE = "tenant_caused_damage"
    DUPLICATE_REQUEST = "duplicate_request"
    COST_NOT_JUSTIFIED = "cost_not_justified"
    SCHEDULED_FOR_LATER = "scheduled_for_later"
    OTHER = "other"


class MaintenanceRequest(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_requests"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[MaintenanceCategory] = mapped_column(
        Enum(MaintenanceCategory, name="maintenance_category"),
        default=MaintenanceCategory.OTHER,
        nullable=False,
    )
    priority: Mapped[MaintenancePriority] = mapped_column(
        Enum(MaintenancePriority, name="maintenance_priority"),
        default=MaintenancePriority.ROUTINE,
        nullable=False,
    )
    status: Mapped[MaintenanceStatus] = mapped_column(
        Enum(MaintenanceStatus, name="maintenance_status"),
        default=MaintenanceStatus.SUBMITTED,
        nullable=False,
        index=True,
    )

    photo_file_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    reported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reported_by_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # `cost` is the actual, final cost. It stays nullable until the job is done —
    # `estimated_cost` is what the approver signed off on beforehand.
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # --- approval (US-061) ---
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(
        Enum(RejectionReason, name="maintenance_rejection_reason"), nullable=True
    )
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when the reviewer bounces the request back for more detail; cleared as
    # soon as the reporter answers.
    info_requested: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- vendor assignment (US-060/US-061) ---
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expected_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Flagged by the nightly sweep once `expected_completion_date` passes with the
    # job still open, so the dashboard does not have to recompute it per request.
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    overdue_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- completion and review ---
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    vendor_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vendor_review: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # In agency mode the cost lands on the owner's statement; this marks that the
    # allocation has been accounted for so a re-close cannot double-charge.
    owner_expense_allocated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    unit: Mapped["Unit"] = relationship()
    vendor: Mapped["Vendor | None"] = relationship(lazy="selectin")

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_maintenance_ref_per_org"),
    )

    @property
    def cost_variance(self) -> Decimal | None:
        """Actual minus estimate, once both are known."""
        if self.cost is None or self.estimated_cost is None:
            return None
        return Decimal(self.cost) - Decimal(self.estimated_cost)


class VacateNoticeStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    WITHDRAWN = "withdrawn"
    COMPLETED = "completed"


class VacateNotice(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant's digital notice to vacate (US-033)."""

    __tablename__ = "vacate_notices"

    tenancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    move_out_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notice_days_given: Mapped[int] = mapped_column(Integer, nullable=False)
    meets_notice_period: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    status: Mapped[VacateNoticeStatus] = mapped_column(
        Enum(VacateNoticeStatus, name="vacate_notice_status"),
        default=VacateNoticeStatus.SUBMITTED,
        nullable=False,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    submitted_by_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )


class VisitorLog(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A caretaker's record of a visitor to a unit (Sprint 25, US-109).

    Logged in one step at check-in; check-out is a separate action so a
    caretaker can close out a visitor who is still on site when the entry was
    made. Deliberately a plain record, not a state machine — there is nothing
    here to approve or reject, only a timestamped fact.
    """

    __tablename__ = "visitor_logs"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visitor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    visitor_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)

    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
