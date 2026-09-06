"""Programmatic access to an organisation's data: API keys and outbound webhooks
(Sprint 19).

An API key never stores its own secret — only a SHA-256 digest, exactly like a
refresh token (`app.core.security.hash_token`). The `key_prefix` is stored in
the clear so a lookup does not need to hash every key in the table to find the
right row, and so the owner can recognise which key is which in the UI without
ever seeing the secret again after creation.

A webhook's secret is the opposite case: the customer must be able to retrieve
it to verify HMAC signatures on their end, so it is symmetrically encrypted
with `app.core.crypto` (the same treatment as eTIMS credentials) rather than
hashed.

Usage counters (requests per day, endpoints hit) live in Redis, not here — an
API key can be called far more often than any other write path in the system,
and that traffic has no audit or accounting value once counted. Only the
identity and lifecycle of the key belongs in Postgres.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import ArchivableMixin, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ApiKeyScope(str, enum.Enum):
    PROPERTIES_READ = "properties:read"
    UNITS_READ = "units:read"
    TENANTS_READ = "tenants:read"
    PAYMENTS_READ = "payments:read"
    INVOICES_READ = "invoices:read"


class WebhookEvent(str, enum.Enum):
    PAYMENT_RECEIVED = "payment.received"
    TENANT_CREATED = "tenant.created"
    LEASE_SIGNED = "lease.signed"
    INSPECTION_COMPLETED = "inspection.completed"
    MAINTENANCE_STATUS_CHANGED = "maintenance.status_changed"
    INVOICE_GENERATED = "invoice.generated"


class WebhookDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class ApiKey(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A long-lived credential for the public REST API (US-086)."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # e.g. "rf_live_9f8a2c1b" — enough to tell keys apart in a list, never the secret.
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_usable(self, now: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return not (self.expires_at is not None and self.expires_at < now)


class WebhookEndpoint(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, ArchivableMixin, Base):
    """Where an organisation wants event payloads pushed (US-087). Capped at 10
    per organisation by the service layer — enough for any integration a solo
    landlord or small agency runs, not enough to become a fan-out problem."""

    __tablename__ = "webhook_endpoints"

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookDelivery(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One attempt to deliver one event to one endpoint. `organization_id` is
    denormalised from the endpoint at creation time purely so this table can
    carry the same RLS policy as everything else, rather than the join-based
    policy `invoice_line_items` needs."""

    __tablename__ = "webhook_deliveries"

    webhook_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, name="webhook_delivery_status"),
        default=WebhookDeliveryStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
