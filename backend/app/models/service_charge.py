"""Service charges for commercial and multi-tenant buildings (US-069, US-070).

The whole point of a service charge is that it is *not* the landlord's income:
it is money collected from tenants to pay for things the building consumes —
security, cleaning, the generator, the lift. So the model keeps three separate
truths and reconciles between them:

    what was budgeted   (ServiceChargeBudget, per category, per month)
    what was charged    (invoice line items, apportioned by the scheme)
    what was spent      (ServiceChargeExpense, as the invoices land)

The difference between charged and spent is the surplus or deficit an annual
statement has to explain, and the sinking fund is the slice deliberately held
back for capital work rather than spent this year.
"""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

ZERO = Decimal("0.00")


class UseClass(str, enum.Enum):
    """What a commercial unit is actually used for (US-069)."""

    OFFICE = "office"
    RETAIL = "retail"
    WAREHOUSE = "warehouse"
    INDUSTRIAL = "industrial"
    RESTAURANT = "restaurant"
    MEDICAL = "medical"
    OTHER = "other"


class Apportionment(str, enum.Enum):
    """How the building's costs are split between its tenants."""

    # Every unit pays the same — simple, and what most Kenyan blocks actually do.
    FIXED_PER_UNIT = "fixed_per_unit"
    # Split by floor area, the standard for commercial lettings.
    BY_FLOOR_AREA = "by_floor_area"
    # Split evenly across occupied units, so a vacancy costs the landlord rather
    # than the remaining tenants.
    BY_OCCUPIED_UNIT = "by_occupied_unit"


class ServiceChargeCategory(str, enum.Enum):
    SECURITY = "security"
    CLEANING = "cleaning"
    COMMON_AREA_MAINTENANCE = "common_area_maintenance"
    GENERATOR = "generator"
    LIFT = "lift"
    WATER = "water"
    LANDSCAPING = "landscaping"
    INSURANCE = "insurance"
    MANAGEMENT = "management"
    OTHER = "other"


class ServiceChargeScheme(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One property's service charge arrangement (US-070)."""

    __tablename__ = "service_charge_schemes"

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Service charge")

    apportionment: Mapped[Apportionment] = mapped_column(
        Enum(Apportionment, name="service_charge_apportionment"),
        default=Apportionment.FIXED_PER_UNIT,
        nullable=False,
    )
    # Used when apportionment is FIXED_PER_UNIT — the flat monthly amount.
    fixed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    # Used by the two proportional methods: the whole building's monthly cost,
    # which is then divided according to the method.
    monthly_pool: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    # Slice of every charge held back for capital work rather than spent this
    # year. Kept as a percent so it scales with the pool automatically.
    sinking_fund_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=ZERO, nullable=False)

    # Off by default: a landlord opts a property in, and until they do no tenant
    # is billed a service charge.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # When false the charge is invoiced on its own rather than added to the rent
    # invoice — some commercial tenants insist on a separate document.
    bill_with_rent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    budgets: Mapped[list["ServiceChargeBudget"]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (UniqueConstraint("property_id", name="uq_service_charge_scheme_per_property"),)


class ServiceChargeBudget(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What one category of the scheme is expected to cost each month."""

    __tablename__ = "service_charge_budgets"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_charge_schemes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[ServiceChargeCategory] = mapped_column(
        Enum(ServiceChargeCategory, name="service_charge_category"), nullable=False
    )
    monthly_budget: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    scheme: Mapped["ServiceChargeScheme"] = relationship(back_populates="budgets")

    __table_args__ = (UniqueConstraint("scheme_id", "category", name="uq_budget_per_category_per_scheme"),)


class ServiceChargeExpense(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Money actually spent on the building, against a budget category.

    This is what makes the annual statement honest: without it, "service charge"
    is a number a landlord invented, and tenants are right to distrust it.
    """

    __tablename__ = "service_charge_expenses"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_charge_schemes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[ServiceChargeCategory] = mapped_column(
        Enum(ServiceChargeCategory, name="service_charge_category"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    incurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False)

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True
    )
    receipt_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SinkingFundMovement(str, enum.Enum):
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"


class SinkingFundEntry(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A movement on the building's reserve for capital work (US-070).

    Kept as a ledger rather than a running balance column so the reserve can
    always be explained line by line — which is exactly the question a tenant
    association asks.
    """

    __tablename__ = "sinking_fund_entries"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_charge_schemes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movement: Mapped[SinkingFundMovement] = mapped_column(
        Enum(SinkingFundMovement, name="sinking_fund_movement"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    # Set when the contribution was generated automatically from a month's billing
    # rather than paid in by hand.
    billing_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
