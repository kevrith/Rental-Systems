"""Tenant screening — applications, guarantors and reference checks (Sprint 14).

The point of this module is that a tenancy should never be the first record of a
person. Before anyone gets keys there is an application: what they earn, who
vouches for them, what their last landlord says. All of it stays attached after
approval, so a dispute two years later can be answered from the file rather than
from memory.

An application is deliberately not a `Tenant`. Most applications are rejected,
and filling the tenant book with people who never moved in would poison every
duplicate check and every count in the product. The `Tenant` row is created only
at approval, from the application's own data.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
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

ZERO = Decimal("0.00")

# Kenyan rental practice, and the ratio the score is built around: rent above a
# third of stated income is the point at which arrears become likely.
INCOME_RATIO_THRESHOLD = Decimal("30")


class ApplicationStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    APPROVED = "approved"
    REJECTED = "rejected"
    # The applicant pulled out, or took another unit.
    WITHDRAWN = "withdrawn"


APPLICATION_TRANSITIONS: dict[ApplicationStatus, tuple[ApplicationStatus, ...]] = {
    ApplicationStatus.SUBMITTED: (
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.INTERVIEW_SCHEDULED,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ),
    ApplicationStatus.UNDER_REVIEW: (
        ApplicationStatus.INTERVIEW_SCHEDULED,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ),
    ApplicationStatus.INTERVIEW_SCHEDULED: (
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ),
    ApplicationStatus.APPROVED: (),
    ApplicationStatus.REJECTED: (),
    ApplicationStatus.WITHDRAWN: (),
}

OPEN_APPLICATION_STATUSES: tuple[ApplicationStatus, ...] = (
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.INTERVIEW_SCHEDULED,
)


class EmploymentStatus(str, enum.Enum):
    EMPLOYED = "employed"
    SELF_EMPLOYED = "self_employed"
    BUSINESS_OWNER = "business_owner"
    STUDENT = "student"
    RETIRED = "retired"
    UNEMPLOYED = "unemployed"


class ApplicationRejectionReason(str, enum.Enum):
    INSUFFICIENT_INCOME = "insufficient_income"
    FAILED_REFERENCE_CHECK = "failed_reference_check"
    INCOMPLETE_APPLICATION = "incomplete_application"
    NO_GUARANTOR = "no_guarantor"
    UNIT_TAKEN = "unit_taken"
    OTHER = "other"


class TenantApplication(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One person's application for one vacant unit (US-064)."""

    __tablename__ = "tenant_applications"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # --- the applicant ---
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- where they live now ---
    current_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    current_landlord_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_landlord_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    years_at_current_address: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    reason_for_moving: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- how they will pay ---
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus, name="employment_status"),
        default=EmploymentStatus.EMPLOYED,
        nullable=False,
    )
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    months_in_employment: Mapped[int | None] = mapped_column(Integer, nullable=True)

    occupants: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    intended_move_in: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- documents (stored_files ids) ---
    id_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    passport_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    payslip_file_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    # --- assessment (US-066) ---
    # Recomputed on every material change, and stored so the list view can rank
    # a waiting list without recalculating a score per row.
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # --- decision (US-067) ---
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.SUBMITTED,
        nullable=False,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejection_reason: Mapped[ApplicationRejectionReason | None] = mapped_column(
        Enum(ApplicationRejectionReason, name="application_rejection_reason"), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set on approval — the tenant and tenancy this application turned into.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="SET NULL"), nullable=True
    )

    # True when the application came in through the public form rather than
    # being keyed in by staff — worth knowing when judging data quality.
    submitted_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    guarantors: Mapped[list["Guarantor"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="selectin"
    )
    references: Mapped[list["ReferenceCheck"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_application_ref_per_org"),
    )

    @property
    def income_ratio(self) -> Decimal | None:
        """Rent as a percentage of stated monthly income.

        Needs the unit's rent, so the service sets `_rent` before reading this;
        kept as a property rather than a column because the rent can change.
        """
        rent = getattr(self, "_rent", None)
        if not self.monthly_income or not rent:
            return None
        return (Decimal(rent) / Decimal(self.monthly_income) * 100).quantize(Decimal("0.01"))


class GuarantorStatus(str, enum.Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    DECLINED = "declined"
    # The link ran out before they answered.
    EXPIRED = "expired"


class Guarantor(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone who accepts liability if the tenant defaults (US-065).

    A guarantor is only worth anything if they knew they were one, so the row
    carries its own acknowledgement: a WhatsApp link they open and confirm, and
    then a signed guarantee agreement through the same signing flow as a lease.
    """

    __tablename__ = "guarantors"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_to_applicant: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    status: Mapped[GuarantorStatus] = mapped_column(
        Enum(GuarantorStatus, name="guarantor_status"),
        default=GuarantorStatus.PENDING,
        nullable=False,
    )
    # Hash only: the raw token lives in the WhatsApp message and nowhere else.
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The signed guarantee agreement, once they have been through the signing flow.
    agreement_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    signature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("digital_signatures.id", ondelete="SET NULL"), nullable=True
    )

    application: Mapped["TenantApplication"] = relationship(back_populates="guarantors")


class ReferenceStatus(str, enum.Enum):
    SENT = "sent"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    # Asked, never answered — which is itself a signal, so it has a state.
    NO_RESPONSE = "no_response"


class ReferenceCheck(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A previous landlord's verdict, collected over WhatsApp (US-068)."""

    __tablename__ = "reference_checks"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    landlord_name: Mapped[str] = mapped_column(String(255), nullable=False)
    landlord_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    property_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[ReferenceStatus] = mapped_column(
        Enum(ReferenceStatus, name="reference_status"), default=ReferenceStatus.SENT, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_on_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    would_rent_again: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["TenantApplication"] = relationship(back_populates="references")
