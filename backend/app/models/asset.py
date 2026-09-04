"""Vehicle and equipment rentals (US-082, US-083).

A car and a generator are the same business: an asset that goes out on hire,
comes back, and is worth less if it comes back in worse condition than it left.
So both live in one `RentalAsset` table with a `kind` discriminator and the
fields each needs, and one `RentalAgreement` covers the hire.

The condition snapshot is the point of the whole module. Mileage, fuel and photos
at check-out and again at check-in are what turn "you scratched it" from an
argument into a comparison, which is exactly the dispute a deposit exists for.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import ArchivableMixin, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

ZERO = Decimal("0.00")


class AssetKind(str, enum.Enum):
    VEHICLE = "vehicle"
    EQUIPMENT = "equipment"


class AssetStatus(str, enum.Enum):
    AVAILABLE = "available"
    ON_HIRE = "on_hire"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class FuelPolicy(str, enum.Enum):
    """What the hirer owes on fuel when they bring it back."""

    FULL_TO_FULL = "full_to_full"
    SAME_TO_SAME = "same_to_same"
    PREPAID = "prepaid"


class RateBasis(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RentalAsset(OrgScopedMixin, ArchivableMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One hireable thing: a vehicle or a piece of equipment."""

    __tablename__ = "rental_assets"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[AssetKind] = mapped_column(Enum(AssetKind, name="asset_kind"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # The fleet or depot this belongs to. A vehicle rental business models its
    # fleet as a property of type VEHICLE_FLEET, so the whole portfolio, caretaker
    # and document machinery already works on it.
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name="asset_status"), default=AssetStatus.AVAILABLE, nullable=False, index=True
    )

    daily_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    weekly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    photo_file_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- vehicles (US-082) ---
    registration_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    make: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    colour: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel_policy: Mapped[FuelPolicy] = mapped_column(
        Enum(FuelPolicy, name="fuel_policy"), default=FuelPolicy.FULL_TO_FULL, nullable=False
    )
    daily_mileage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excess_mileage_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Vehicle compliance. Kept on the asset rather than in `compliance_items`
    # because a fleet operator checks these per vehicle, every hire, not annually
    # per building.
    insurance_expiry: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    inspection_expiry: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    road_licence_expiry: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # --- equipment (US-083) ---
    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_serviced_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    agreements: Mapped[list["RentalAgreement"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_asset_ref_per_org"),)

    @property
    def compliance_warnings(self) -> list[str]:
        """Everything about this asset that is expired or nearly so.

        Read before every check-out: hiring out a vehicle with lapsed insurance is
        the mistake that ends a rental business.
        """
        today = date.today()
        warnings: list[str] = []
        for label, expiry in (
            ("Insurance", self.insurance_expiry),
            ("Inspection", self.inspection_expiry),
            ("Road licence", self.road_licence_expiry),
        ):
            if expiry is None:
                continue
            days = (expiry - today).days
            if days < 0:
                warnings.append(f"{label} expired {abs(days)} day(s) ago")
            elif days <= 30:
                warnings.append(f"{label} expires in {days} day(s)")

        due = self.service_due_on
        if due is not None and due < today:
            warnings.append(f"Service overdue since {due:%d %b %Y}")
        return warnings

    @property
    def service_due_on(self) -> date | None:
        if not (self.service_interval_days and self.last_serviced_on):
            return None
        from datetime import timedelta

        return self.last_serviced_on + timedelta(days=self.service_interval_days)


class AgreementStatus(str, enum.Enum):
    # Reserved for a future window; the asset is not out yet.
    BOOKED = "booked"
    # Checked out and with the hirer.
    OUT = "out"
    RETURNED = "returned"
    CANCELLED = "cancelled"


AGREEMENT_TRANSITIONS: dict[AgreementStatus, tuple[AgreementStatus, ...]] = {
    AgreementStatus.BOOKED: (AgreementStatus.OUT, AgreementStatus.CANCELLED),
    AgreementStatus.OUT: (AgreementStatus.RETURNED,),
    AgreementStatus.RETURNED: (),
    AgreementStatus.CANCELLED: (),
}

BLOCKING_STATUSES: tuple[AgreementStatus, ...] = (AgreementStatus.BOOKED, AgreementStatus.OUT)


class RentalAgreement(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One hire of one asset, from booking to return."""

    __tablename__ = "rental_agreements"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rental_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The hirer is a `Tenant`: the same person record, the same KYC, the same
    # payment history. A rental business's customer is not a different species.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    rate_basis: Mapped[RateBasis] = mapped_column(
        Enum(RateBasis, name="rate_basis"), default=RateBasis.DAILY, nullable=False
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    deposit_refunded: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    status: Mapped[AgreementStatus] = mapped_column(
        Enum(AgreementStatus, name="agreement_status"),
        default=AgreementStatus.BOOKED,
        nullable=False,
        index=True,
    )

    # --- check-out snapshot ---
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mileage_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel_out_eighths: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_out: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos_out: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    driver_licence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    checked_out_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # --- check-in snapshot ---
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mileage_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel_in_eighths: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_in: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos_in: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    checked_in_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # --- money ---
    hire_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    excess_mileage_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    damage_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    fuel_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    late_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    total_charge: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    agreement_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped["RentalAsset"] = relationship(back_populates="agreements")

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_agreement_ref_per_org"),)

    @property
    def hire_days(self) -> int:
        """Inclusive of both days — a Monday-to-Monday hire is two days, not one,
        which is how every counter in Nairobi counts it."""
        return max((self.end_date - self.start_date).days + 1, 1)

    @property
    def mileage_covered(self) -> int | None:
        if self.mileage_out is None or self.mileage_in is None:
            return None
        return max(self.mileage_in - self.mileage_out, 0)

    @property
    def is_overdue(self) -> bool:
        return self.status == AgreementStatus.OUT and self.end_date < date.today()
