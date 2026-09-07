"""Partner integrations — Sprint 23 (US-099, US-100, US-101).

Two unrelated partner surfaces share a shape with `app.models.etims`: an
organisation's own credentials for someone else's system, held encrypted
because they are the landlord's identity with that partner and not ours to
leak, and a durable row per sync attempt because "did this reach QuickBooks?"
has to be answerable months later. Property portals and accounting software
each get one connection/sync-record pair on that pattern.

Bank transfer reconciliation is unrelated to either: a landlord uploads their
bank statement, and every line either matches a tenancy by its reference code
appearing in the description, or it does not — nothing here writes a payment
by itself. Matching only ever proposes; a person still confirms.
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

# --------------------------------------------------------------- property portals


class PortalName(str, enum.Enum):
    BUYRENTKENYA = "buyrentkenya"
    PIGIAME = "pigiame"


class PortalSyncStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    DEACTIVATED = "deactivated"
    FAILED = "failed"


class PortalConnection(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organisation's credentials with one listing portal."""

    __tablename__ = "portal_connections"

    portal: Mapped[PortalName] = mapped_column(Enum(PortalName, name="portal_name"), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (UniqueConstraint("organization_id", "portal", name="uq_portal_connection_per_org"),)


class PortalListingSync(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One vacancy listing's publish state on one connected portal."""

    __tablename__ = "portal_listing_syncs"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portal_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    external_listing_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[PortalSyncStatus] = mapped_column(
        Enum(PortalSyncStatus, name="portal_sync_status"),
        default=PortalSyncStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        UniqueConstraint("listing_id", "connection_id", name="uq_portal_sync_per_listing_connection"),
    )


# ------------------------------------------------------------ accounting software


class AccountingProvider(str, enum.Enum):
    QUICKBOOKS = "quickbooks"
    XERO = "xero"


class AccountingEntityType(str, enum.Enum):
    PAYMENT = "payment"
    MAINTENANCE_COST = "maintenance_cost"
    DISBURSEMENT = "disbursement"


class AccountingSyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class AccountingConnection(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organisation's OAuth grant with QuickBooks or Xero.

    Both tokens are stored encrypted (see `app.core.crypto`) — a refresh token
    is a standing ability to act as this landlord's accounting software.
    """

    __tablename__ = "accounting_connections"

    provider: Mapped[AccountingProvider] = mapped_column(
        Enum(AccountingProvider, name="accounting_provider"), nullable=False
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # QuickBooks calls this the realmId, Xero the tenantId — one external
    # company identity either way.
    external_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(16), default="sandbox", server_default="sandbox", nullable=False
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connected_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "provider", name="uq_accounting_connection_per_org"),
    )


class AccountingSyncRecord(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One RentFlow entity's journey to the accounting ledger, so a sync never
    double-posts and a failure can be retried and inspected."""

    __tablename__ = "accounting_sync_records"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounting_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[AccountingEntityType] = mapped_column(
        Enum(AccountingEntityType, name="accounting_entity_type"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[AccountingSyncStatus] = mapped_column(
        Enum(AccountingSyncStatus, name="accounting_sync_status"),
        default=AccountingSyncStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("connection_id", "entity_type", "entity_id", name="uq_accounting_sync_per_entity"),
    )


# ------------------------------------------------------------- bank reconciliation


class BankStatementUpload(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded statement and the tally of how well it matched (US-101)."""

    __tablename__ = "bank_statement_uploads"

    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    row_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    unmatched_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    entries: Mapped[list["BankStatementEntry"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", lazy="selectin"
    )


class BankStatementEntry(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One line of an uploaded statement, and what it was matched to, if anything."""

    __tablename__ = "bank_statement_entries"

    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_statement_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    matched_tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="SET NULL"), nullable=True
    )
    # Set once a person confirms the match and a payment is recorded from it —
    # the entry itself never creates one on its own.
    matched_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    is_matched: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    upload: Mapped["BankStatementUpload"] = relationship(back_populates="entries")
