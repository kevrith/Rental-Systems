"""Contractors an owner or agency trusts with maintenance work (Sprint 13).

A vendor is deliberately not a `User`: most plumbers and electricians never log
in, they get a WhatsApp with the job and a phone number to call. What the
platform keeps is enough to pick the right one quickly — what they do, what they
charge, and how their last jobs went.

Ratings are stored as a running total plus a count rather than recomputed from
the job table on every read: the maintenance request holds the individual score
for audit, and this pair answers "who is my best plumber" without a join.
"""

import enum
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import ArchivableMixin, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

ZERO = Decimal("0.00")


class VendorSpecialty(str, enum.Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CARPENTRY = "carpentry"
    PAINTING = "painting"
    MASONRY = "masonry"
    ROOFING = "roofing"
    APPLIANCE = "appliance"
    CLEANING = "cleaning"
    PEST_CONTROL = "pest_control"
    SECURITY = "security"
    LANDSCAPING = "landscaping"
    GENERAL = "general"


# Which specialties can sensibly answer a request of each maintenance category.
# Used to rank the vendor picker rather than to restrict it — an owner can always
# send a job to whoever they trust.
CATEGORY_SPECIALTIES: dict[str, tuple[VendorSpecialty, ...]] = {
    "plumbing": (VendorSpecialty.PLUMBING,),
    "electrical": (VendorSpecialty.ELECTRICAL,),
    "structural": (VendorSpecialty.MASONRY, VendorSpecialty.CARPENTRY, VendorSpecialty.ROOFING),
    "appliance": (VendorSpecialty.APPLIANCE, VendorSpecialty.ELECTRICAL),
    "security": (VendorSpecialty.SECURITY,),
    "other": (VendorSpecialty.GENERAL,),
}


class Vendor(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, ArchivableMixin, Base):
    """A contractor on the organisation's approved list (US-060)."""

    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # A list of `VendorSpecialty` values. JSONB rather than a join table because a
    # vendor's specialties are always read whole and never queried across vendors
    # by anything other than containment.
    specialties: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Free text on purpose: quotes in this trade are "KES 1,500 callout then per
    # job" far more often than they are a clean hourly rate.
    rate_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    rating_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_billed: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO, nullable=False)

    __table_args__ = (UniqueConstraint("organization_id", "phone_number", name="uq_vendor_phone_per_org"),)

    @property
    def average_rating(self) -> float | None:
        if not self.rating_count:
            return None
        return round(self.rating_total / self.rating_count, 2)

    @property
    def average_job_cost(self) -> Decimal:
        if not self.jobs_completed:
            return ZERO
        return (Decimal(self.total_billed) / self.jobs_completed).quantize(Decimal("0.01"))
