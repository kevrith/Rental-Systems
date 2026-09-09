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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenancy  # lgtm[py/unsafe-cyclic-import]

ZERO = Decimal("0.00")


class InvoiceStatus(str, enum.Enum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class LineItemKind(str, enum.Enum):
    RENT = "rent"
    WATER = "water"
    ELECTRICITY = "electricity"
    SERVICE_CHARGE = "service_charge"
    ARREARS = "arrears"
    LATE_FEE = "late_fee"
    DEPOSIT = "deposit"
    OTHER = "other"


class PaymentMethod(str, enum.Enum):
    MPESA = "mpesa"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CARD = "card"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REVERSED = "reversed"


class Invoice(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoices"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"), default=InvoiceStatus.PENDING, nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenancy: Mapped["Tenancy"] = relationship(back_populates="invoices")
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_invoice_ref_per_org"),
        # One invoice per tenancy per billing period — the generator relies on this
        # to stay idempotent when the daily Celery task re-runs.
        UniqueConstraint("tenancy_id", "period_start", name="uq_invoice_period_per_tenancy"),
    )

    @property
    def balance(self) -> Decimal:
        return Decimal(self.total) - Decimal(self.amount_paid)


class InvoiceLineItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[LineItemKind] = mapped_column(
        Enum(LineItemKind, name="line_item_kind"), default=LineItemKind.OTHER, nullable=False
    )
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"), nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="line_items")


class Payment(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tenancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method"), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING, nullable=False, index=True
    )

    # M-Pesa specifics. `mpesa_receipt` is unique so the same Daraja confirmation
    # can never be banked twice (US-019).
    mpesa_receipt: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    mpesa_checkout_request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, unique=True
    )
    mpesa_merchant_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Bank transfer / cheque reference, for reconciling against a statement
    # (Sprint 23, US-101). Not globally unique like `mpesa_receipt` — different
    # banks issue overlapping reference formats, so any uniqueness is the
    # caller's job, scoped to the organisation.
    bank_reference: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- dual approval for large cash (masterplan, Fraud Prevention) ---
    # Set when the amount cleared the organisation's
    # `cash_dual_approval_threshold`. Such a payment is created PENDING and is
    # never allocated, receipted or announced to the tenant until a *different*
    # person approves it — one person must not be able to both take the money
    # and declare it banked.
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False, index=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenancy: Mapped["Tenancy"] = relationship(back_populates="payments")
    invoice: Mapped["Invoice | None"] = relationship(back_populates="payments")
    receipt: Mapped["Receipt | None"] = relationship(
        back_populates="payment", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_payment_ref_per_org"),)


class Receipt(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tamper-evident proof of payment (US-023).

    `signature` is an HMAC over the immutable receipt facts using the server
    secret, so an altered PDF can be detected by re-deriving it.
    """

    __tablename__ = "receipts"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, nullable=False)

    payment: Mapped["Payment"] = relationship(back_populates="receipt")

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_receipt_ref_per_org"),)
