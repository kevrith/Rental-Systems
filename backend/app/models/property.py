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
from app.models.base import ArchivableMixin, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agency import OwnerProfile
    from app.models.tenant import Tenancy
    from app.models.user import User


class PropertyType(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED_USE = "mixed_use"
    VEHICLE_FLEET = "vehicle_fleet"
    EQUIPMENT = "equipment"
    EVENT_SPACE = "event_space"
    LAND = "land"


class UnitStatus(str, enum.Enum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    UNDER_MAINTENANCE = "under_maintenance"
    RESERVED = "reserved"
    VACATING = "vacating"


class LateFeeType(str, enum.Enum):
    """How a late fee is worked out once the grace period has run out."""

    FIXED = "fixed"
    PERCENT = "percent"
    DAILY = "daily"


class Property(OrgScopedMixin, ArchivableMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "properties"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    property_type: Mapped[PropertyType] = mapped_column(
        Enum(PropertyType, name="property_type"), default=PropertyType.RESIDENTIAL, nullable=False
    )
    address: Mapped[str] = mapped_column(String(512), nullable=False)
    county: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sub_county: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amenities: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    # Utility rates used to price meter readings (US-026), in KES per unit consumed.
    water_rate_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    electricity_rate_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Late fee configuration (US-055). A property with no `late_fee_type` charges
    # nothing, which is the default — a landlord opts in per property.
    grace_period_days: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    late_fee_type: Mapped[LateFeeType | None] = mapped_column(
        Enum(LateFeeType, name="late_fee_type"), nullable=True
    )
    # A flat KES amount, a percent of the outstanding balance, or KES per day.
    late_fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Ceiling on a daily or percentage fee, so an old arrear cannot compound into
    # something larger than the rent itself.
    late_fee_cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Monthly maintenance allowance, used for budget-vs-actual reporting (US-062).
    # Null means the owner has not set one, and the report simply omits variance.
    maintenance_budget_monthly: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Agency mode: which owner client this property belongs to (US-036)
    owner_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owner_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    owner_profile: Mapped["OwnerProfile | None"] = relationship(back_populates="properties")
    units: Mapped[list["Unit"]] = relationship(
        back_populates="property", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_property_ref_per_org"),)


class Unit(OrgScopedMixin, ArchivableMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "units"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    unit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    features: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)

    status: Mapped[UnitStatus] = mapped_column(
        Enum(UnitStatus, name="unit_status"), default=UnitStatus.VACANT, nullable=False, index=True
    )
    vacancy_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_vacancy_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    property: Mapped["Property"] = relationship(back_populates="units")
    tenancies: Mapped[list["Tenancy"]] = relationship(back_populates="unit")

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_unit_ref_per_org"),
        UniqueConstraint("property_id", "unit_number", name="uq_unit_number_per_property"),
    )


class CaretakerAssignment(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Scopes a caretaker to the properties they may operate on (US-013).

    Absence of any row for a caretaker means they see nothing — assignment is
    opt-in, never implicit.
    """

    __tablename__ = "caretaker_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Owner-configurable ceiling on a single cash payment this caretaker may record.
    cash_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="caretaker_assignments", foreign_keys=[user_id])
    property: Mapped["Property"] = relationship()

    __table_args__ = (UniqueConstraint("user_id", "property_id", name="uq_caretaker_property"),)
