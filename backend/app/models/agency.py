"""Agency mode models — Phase 2 (US-034, US-035, US-036, US-038).

OwnerProfile represents a landlord client managed by an agency.
Disbursement records net payments from agency to owner.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.property import Property

ZERO = Decimal("0.00")


class DisbursementStatus(str, enum.Enum):
    """Lifecycle of one payout.

    A disbursement is calculated (PENDING), reviewed by an agency admin who
    either APPROVED or REJECTED it, and only an approved one can be paid.
    PROCESSING means the money has left via M-Pesa B2C and Safaricom has not yet
    told us how it went.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OwnerProfile(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A landlord client within an agency account.

    In owner-mode the account holder IS the implicit owner profile; this model
    only exists in agency accounts where one agency manages multiple landlords.
    """

    __tablename__ = "owner_profiles"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kra_pin: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Banking details for disbursements
    bank_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mpesa_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Management agreement terms
    management_fee_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("8.00"), nullable=False
    )
    disbursement_day: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Maintenance spending authority thresholds (KES)
    maintenance_auto_approve_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("5000.00"), nullable=False
    )
    maintenance_notify_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("20000.00"), nullable=False
    )

    # Portal access — set when agency invites owner to Mode 3 portal
    portal_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    portal_invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    properties: Mapped[list["Property"]] = relationship(back_populates="owner_profile")
    disbursements: Mapped[list["Disbursement"]] = relationship(back_populates="owner_profile")

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_owner_profile_ref_per_org"),
    )


class Disbursement(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Net payment from agency to a landlord client for a billing period."""

    __tablename__ = "disbursements"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owner_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    gross_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    management_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    maintenance_costs: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    status: Mapped[DisbursementStatus] = mapped_column(
        Enum(DisbursementStatus, name="disbursement_status"),
        default=DisbursementStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Payment details
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Statement PDF
    statement_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    # Approval workflow (US-041) — nobody pays an owner off an unreviewed number.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # M-Pesa B2C payout correlation. Daraja answers the request with a pair of
    # conversation ids and reports the outcome later on the result callback, which
    # carries only those ids back.
    payout_conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payout_originator_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payout_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    owner_profile: Mapped["OwnerProfile"] = relationship(back_populates="disbursements")

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_disbursement_ref_per_org"),
    )
