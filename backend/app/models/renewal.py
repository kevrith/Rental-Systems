"""Lease renewal — Phase 2 (US-057).

A tenancy that reaches its end date with nobody having done anything is the
default failure mode of small-landlord property management. This model turns
"the lease expires in 30 days" into a thing with a state: an offer was made, on
these terms, and the tenant has accepted, declined, or not answered yet.

The renewal never mutates the tenancy it comes from. Accepting one creates the
new term on the existing tenancy and keeps this row as the record of what was
agreed and when.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RenewalStatus(str, enum.Enum):
    # Offered to the tenant, awaiting their answer.
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    # The tenant never answered and the lease has run out.
    LAPSED = "lapsed"


class LeaseRenewal(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One renewal offer on one tenancy."""

    __tablename__ = "lease_renewals"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The terms being offered. `current_rent` is kept alongside so the offer
    # remains readable after the tenancy has moved on.
    current_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    proposed_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rent_increase_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    new_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    new_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, default=12, server_default="12", nullable=False)

    status: Mapped[RenewalStatus] = mapped_column(
        Enum(RenewalStatus, name="renewal_status"),
        default=RenewalStatus.OFFERED,
        nullable=False,
        index=True,
    )
    # The tenant has this long to answer before the offer is chased.
    respond_by: Mapped[date] = mapped_column(Date, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Single-use token for the public accept/decline links sent over WhatsApp.
    # Only the hash is stored, exactly as for a signing link.
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The generated renewal agreement, and the signature request raised on it.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    signature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("digital_signatures.id", ondelete="SET NULL"), nullable=True
    )

    # Set when the 14-day mark passes with no answer, so the owner is told once.
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_renewal_ref_per_org"),)
