"""Compliance, parking, amenities and utility accounts (Sprint 17).

Four things that share a shape: they are all *obligations attached to a building*
rather than to a tenancy. A fire certificate expires whether or not anyone is
living there; a parking bay exists whether or not it is allocated; the KPLC
account has to be paid even when the block is empty.

The compliance calendar is the one that earns its keep. An expired lift
certificate is not a paperwork problem — it is the day the insurer refuses a
claim — so expiry is a first-class date with its own reminder ladder.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

ZERO = Decimal("0.00")

# The reminder ladder. Ninety days is enough to book an inspection; thirty is the
# point at which it becomes urgent.
REMINDER_DAYS = (90, 60, 30, 7)

# Anything expiring inside this window is amber on the dashboard.
AMBER_WINDOW_DAYS = 60


class ComplianceType(str, enum.Enum):
    FIRE_SAFETY = "fire_safety"
    HEALTH_INSPECTION = "health_inspection"
    NEMA = "nema"
    LIFT_INSPECTION = "lift_inspection"
    ELECTRICAL_INSPECTION = "electrical_inspection"
    WATER_SAFETY = "water_safety"
    INSURANCE = "insurance"
    BUSINESS_PERMIT = "business_permit"
    STRUCTURAL_SURVEY = "structural_survey"
    OTHER = "other"


class ComplianceStatus(str, enum.Enum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    # Recorded as required but never obtained — an honest state, and the one an
    # auditor most wants to see rather than have hidden.
    MISSING = "missing"


class ComplianceItem(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One certificate or policy on one property (US-078)."""

    __tablename__ = "compliance_items"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compliance_type: Mapped[ComplianceType] = mapped_column(
        Enum(ComplianceType, name="compliance_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(128), nullable=True)

    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    issuing_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    # Insurance-specific, kept here rather than in a second table: a policy is a
    # compliance item with a premium, and splitting them would double the UI.
    insurer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insurer_contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coverage_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    premium_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    premium_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The largest reminder threshold already sent, so the ladder never repeats a rung.
    last_reminder_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def status(self) -> ComplianceStatus:
        if self.expires_on is None:
            return ComplianceStatus.MISSING
        days = (self.expires_on - date.today()).days
        if days < 0:
            return ComplianceStatus.EXPIRED
        if days <= AMBER_WINDOW_DAYS:
            return ComplianceStatus.EXPIRING_SOON
        return ComplianceStatus.VALID

    @property
    def days_until_expiry(self) -> int | None:
        if self.expires_on is None:
            return None
        return (self.expires_on - date.today()).days


class BayType(str, enum.Enum):
    COVERED = "covered"
    OPEN = "open"
    RESERVED = "reserved"
    VISITOR = "visitor"
    DISABLED = "disabled"


class ParkingBay(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One parking bay in one property (US-079)."""

    __tablename__ = "parking_bays"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bay_number: Mapped[str] = mapped_column(String(32), nullable=False)
    bay_type: Mapped[BayType] = mapped_column(
        Enum(BayType, name="bay_type"), default=BayType.OPEN, nullable=False
    )
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("property_id", "bay_number", name="uq_bay_number_per_property"),)


class ParkingAllocation(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Who has a bay, and until when.

    A visitor allocation is the same row with a guest name and a short window —
    the alternative was a second table that duplicated every conflict check.
    """

    __tablename__ = "parking_allocations"

    bay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parking_bays.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vehicle_registration: Mapped[str | None] = mapped_column(String(32), nullable=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    # Off for a visitor bay or a bay thrown in with the rent.
    bill_monthly: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_current(self) -> bool:
        if self.released_at is not None:
            return False
        today = date.today()
        if self.start_date > today:
            return False
        return self.end_date is None or self.end_date >= today


class AmenityKind(str, enum.Enum):
    GYM = "gym"
    MEETING_ROOM = "meeting_room"
    ROOFTOP = "rooftop"
    POOL = "pool"
    CLUBHOUSE = "clubhouse"
    PLAYGROUND = "playground"
    LAUNDRY = "laundry"
    OTHER = "other"


class Amenity(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A shared facility tenants can book (US-080)."""

    __tablename__ = "amenities"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[AmenityKind] = mapped_column(
        Enum(AmenityKind, name="amenity_kind"), default=AmenityKind.OTHER, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Booking rules. Kept on the amenity rather than a settings blob so each one
    # can have its own — a gym slot is an hour, the rooftop is an evening.
    max_hours_per_booking: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    min_notice_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_bookings_per_week: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    opens_at_hour: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    closes_at_hour: Mapped[int] = mapped_column(Integer, default=22, nullable=False)

    is_bookable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    booking_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    __table_args__ = (UniqueConstraint("property_id", "name", name="uq_amenity_name_per_property"),)


class BookingStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    # The manager took the amenity out of service for that window.
    BLOCKED = "blocked"


class AmenityBooking(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One reservation of one amenity for one window.

    Maintenance blocks are bookings too, with `status = BLOCKED` and no tenant.
    That way the conflict check is one query rather than two that can disagree.
    """

    __tablename__ = "amenity_bookings"

    amenity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amenities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), default=BookingStatus.CONFIRMED, nullable=False
    )
    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class UtilityAccountType(str, enum.Enum):
    KPLC = "kplc"
    WATER = "water"
    INTERNET = "internet"
    GARBAGE = "garbage"
    OTHER = "other"


class UtilityPaymentStatus(str, enum.Enum):
    PAID = "paid"
    UNPAID = "unpaid"
    # Nobody has checked, which is the truth far more often than either of the above.
    UNKNOWN = "unknown"


class UtilityAccount(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The building's own utility accounts (US-081) — not the tenants' meters."""

    __tablename__ = "utility_accounts"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_type: Mapped[UtilityAccountType] = mapped_column(
        Enum(UtilityAccountType, name="utility_account_type"), nullable=False
    )
    account_number: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)

    payment_status: Mapped[UtilityPaymentStatus] = mapped_column(
        Enum(UtilityPaymentStatus, name="utility_payment_status"),
        default=UtilityPaymentStatus.UNKNOWN,
        nullable=False,
    )
    last_paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    next_due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "property_id", "account_type", "account_number", name="uq_utility_account_per_property"
        ),
    )

    @property
    def is_overdue(self) -> bool:
        return (
            self.payment_status != UtilityPaymentStatus.PAID
            and self.next_due_on is not None
            and self.next_due_on < date.today()
        )
