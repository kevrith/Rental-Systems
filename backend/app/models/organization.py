import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class OperatingMode(str, enum.Enum):
    OWNER = "owner"
    AGENCY = "agency"


class SubscriptionPlan(str, enum.Enum):
    TRIAL = "trial"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The top-level SaaS tenant. Every piece of data is scoped to an organization."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    operating_mode: Mapped[OperatingMode] = mapped_column(
        Enum(OperatingMode, name="operating_mode"), default=OperatingMode.OWNER
    )
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), default=SubscriptionPlan.TRIAL
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Branding, used on leases, invoices and receipts (US-016, US-023).
    logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kra_pin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    letterhead_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Operational defaults
    default_caretaker_cash_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    default_billing_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Lease renewal defaults (US-057). A renewal offered automatically uses these,
    # so a landlord sets their annual uplift once rather than per tenancy.
    renewal_rent_increase_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    renewal_term_months: Mapped[int] = mapped_column(Integer, default=12, server_default="12", nullable=False)
    # Renewals go out automatically unless a landlord would rather do it by hand.
    auto_offer_renewals: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    # Highest trial reminder already sent (7, 3 or 1) so Celery Beat never repeats one.
    trial_reminder_sent_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Public API (Sprint 19). None means "use the platform default" — only an
    # enterprise plan gets a bespoke ceiling.
    api_rate_limit_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Referral credit (Sprint 20, US-092). Months of free subscription owed to
    # this organisation for referrals that converted. There is no billing engine
    # yet to draw this down against an invoice — it is a ledger waiting for one.
    credit_months: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")

    @property
    def is_trial_expired(self) -> bool:
        """True once a trial organization is past its end date.

        Expired trials drop to read-only rather than losing access — the owner's
        data stays visible behind an upgrade prompt (US-006).
        """
        if self.subscription_plan != SubscriptionPlan.TRIAL or self.trial_ends_at is None:
            return False
        return datetime.now(self.trial_ends_at.tzinfo) > self.trial_ends_at
