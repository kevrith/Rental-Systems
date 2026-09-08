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
from app.models.base import ArchivableMixin, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.billing import Invoice, Payment  # lgtm[py/unsafe-cyclic-import]
    from app.models.property import Unit  # lgtm[py/unsafe-cyclic-import]


class TenancyStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    NOTICE_GIVEN = "notice_given"
    VACATED = "vacated"


class PaymentMethodPreference(str, enum.Enum):
    MPESA = "mpesa"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    CHEQUE = "cheque"


class Tenant(OrgScopedMixin, ArchivableMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # National ID is field-level encrypted per-organization (Sprint 26A) rather
    # than mapped as plaintext — see `app/services/tenant_pii.py`'s
    # `set_national_id`/`decrypt_national_id`/`masked_national_id`, which are
    # the only code meant to touch these three columns directly.
    # `_blind_index` is a deterministic HMAC (`app/core/crypto.blind_index`)
    # so exact-match duplicate detection still works without decrypting
    # anything; `_last4` is a plaintext display/search hint, same idea as
    # `crypto.mask()`. The original plaintext `national_id` column is dropped
    # in a later, explicitly separate migration once every environment has
    # been backfilled — see `backend/scripts/backfill_national_id_encryption.py`.
    national_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    national_id_blind_index: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    national_id_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    if TYPE_CHECKING:
        # Transient, unmapped — never persisted, never read from the db.
        # `tenant_pii.py`'s callers stash a decrypted (single-record reveal)
        # or masked (list view) national ID here for exactly the duration of
        # one request or one PDF render; a fresh load never has it set. This
        # block only exists so mypy accepts the assignment — it is skipped at
        # runtime and does not reach SQLAlchemy's declarative class scan, so
        # it cannot be mistaken for a mapped column.
        national_id: str | None

    # KYC documents (stored_files ids)
    id_photo_front_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    id_photo_back_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    passport_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    # Employment
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Emergency contact
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact_relationship: Mapped[str | None] = mapped_column(String(64), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Portal login, created when the tenant accepts their invitation (US-029).
    portal_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    # Set once an erasure request (Sprint 25, US-106) has redacted this tenant's
    # PII. Financial records (tenancies, invoices, payments) are untouched — only
    # this row's own personal fields are blanked. A tenant erased twice is a
    # no-op, which this timestamp is what makes checkable.
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenancies: Mapped[list["Tenancy"]] = relationship(back_populates="tenant", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("organization_id", "reference_code", name="uq_tenant_ref_per_org"),
        UniqueConstraint("organization_id", "phone_number", name="uq_tenant_phone_per_org"),
    )


class Tenancy(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The rental relationship between one tenant and one unit."""

    __tablename__ = "tenancies"

    reference_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_open_ended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    billing_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    payment_method: Mapped[PaymentMethodPreference] = mapped_column(
        Enum(PaymentMethodPreference, name="payment_method_preference"),
        default=PaymentMethodPreference.MPESA,
        nullable=False,
    )

    status: Mapped[TenancyStatus] = mapped_column(
        Enum(TenancyStatus, name="tenancy_status"), default=TenancyStatus.ACTIVE, nullable=False, index=True
    )
    notice_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    move_out_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vacated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lease_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="tenancies")
    unit: Mapped["Unit"] = relationship(back_populates="tenancies")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="tenancy")
    payments: Mapped[list["Payment"]] = relationship(back_populates="tenancy")

    __table_args__ = (UniqueConstraint("organization_id", "reference_code", name="uq_tenancy_ref_per_org"),)


class TenancyCoTenant(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An additional tenant on a tenancy, beyond its primary `Tenancy.tenant_id`
    (Sprint 25, US-107).

    Deliberately additive: every financial flow (invoices, payments, arrears)
    keys off `Tenancy.tenant_id` alone, so adding a co-tenant here can never
    duplicate a charge or split a balance. What it does change is who can see
    the tenancy in the portal and who is asked to sign the lease.
    """

    __tablename__ = "tenancy_co_tenants"

    tenancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (UniqueConstraint("tenancy_id", "tenant_id", name="uq_co_tenant_per_tenancy"),)


class LeaseTemplate(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A lease body with `{{variable}}` placeholders, rendered to PDF per tenancy.

    Templates are versioned: editing bumps `version` on a new row rather than
    mutating one already used to generate a signed lease.
    """

    __tablename__ = "lease_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    logo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    letterhead_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
