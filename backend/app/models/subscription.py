"""RentFlow's own billing — what an organisation pays *us* (Sprint 27, US-113).

Not to be confused with `app.models.billing`, which is rent: what a tenant pays
a landlord. The two never mix. This side has exactly one subscription per
organisation and raises its own invoices against a saved card.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.organization import SubscriptionPlan


class BillingInterval(str, enum.Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(str, enum.Enum):
    """Where a subscription sits in its lifecycle.

    PAST_DUE is the dunning window: a charge failed, the account still works,
    and it has until `grace_ends_at` to pay before LAPSED drops it to read-only.
    LAPSED never deletes anything — the same principle as an expired trial, the
    landlord's data stays fully visible and simply stops growing.
    """

    ACTIVE = "active"
    PAST_DUE = "past_due"
    LAPSED = "lapsed"
    CANCELLED = "cancelled"


class SubscriptionInvoiceStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class Subscription(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), nullable=False
    )
    interval: Mapped[BillingInterval] = mapped_column(
        Enum(BillingInterval, name="billing_interval"),
        default=BillingInterval.MONTHLY,
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    current_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    # The day the next charge is attempted. Indexed because the nightly biller
    # selects on it across every organisation.
    next_billing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Paystack's handle on the saved card. Charging it also requires our secret
    # key, so on its own it authorises nothing — but it is still the token that
    # moves money, and it is never returned by the API.
    paystack_authorization_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Paystack ties an authorization to the email it was created with; a charge
    # against a different address is rejected.
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_brand: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Dunning state. `failed_attempts` resets to zero on every success.
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grace_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    invoices: Mapped[list["SubscriptionInvoice"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    @property
    def has_saved_card(self) -> bool:
        return bool(self.paystack_authorization_code and self.billing_email)


class SubscriptionInvoice(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscription_invoices"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    status: Mapped[SubscriptionInvoiceStatus] = mapped_column(
        Enum(SubscriptionInvoiceStatus, name="subscription_invoice_status"),
        default=SubscriptionInvoiceStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Unique for the same reason a payment's is: a re-delivered webhook must
    # never mark the same month paid twice.
    paystack_reference: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscription: Mapped["Subscription"] = relationship(back_populates="invoices")
