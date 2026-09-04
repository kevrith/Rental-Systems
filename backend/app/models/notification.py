import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    PUSH = "push"
    EMAIL = "email"
    IN_APP = "in_app"


class NotificationType(str, enum.Enum):
    PAYMENT_CONFIRMED = "payment_confirmed"
    RENT_REMINDER = "rent_reminder"
    INVOICE_ISSUED = "invoice_issued"
    RECEIPT_ISSUED = "receipt_issued"
    MAINTENANCE_UPDATE = "maintenance_update"
    MAINTENANCE_SUBMITTED = "maintenance_submitted"
    LEASE_EXPIRY = "lease_expiry"
    TRIAL_EXPIRY = "trial_expiry"
    UNIT_STATUS_CHANGED = "unit_status_changed"
    SUSPICIOUS_LOGIN = "suspicious_login"
    VACATE_NOTICE = "vacate_notice"
    CARETAKER_DAILY_SUMMARY = "caretaker_daily_summary"
    WELCOME = "welcome"
    ACCOUNT = "account"
    # Phase 2
    DISBURSEMENT_SENT = "disbursement_sent"
    INSPECTION_COMPLETED = "inspection_completed"
    LATE_FEE_APPLIED = "late_fee_applied"
    OWNER_PORTAL_INVITE = "owner_portal_invite"
    LEASE_RENEWAL = "lease_renewal"
    DOCUMENT_SIGNED = "document_signed"
    # Phase 3 — maintenance lifecycle
    MAINTENANCE_APPROVED = "maintenance_approved"
    MAINTENANCE_REJECTED = "maintenance_rejected"
    MAINTENANCE_OVERDUE = "maintenance_overdue"
    VENDOR_ASSIGNED = "vendor_assigned"
    # Phase 3 — tenant screening
    APPLICATION_RECEIVED = "application_received"
    APPLICATION_APPROVED = "application_approved"
    APPLICATION_REJECTED = "application_rejected"
    GUARANTOR_REQUEST = "guarantor_request"
    REFERENCE_REQUEST = "reference_request"
    # Phase 3 — bulk operations
    RENT_INCREASE = "rent_increase"
    ANNOUNCEMENT = "announcement"
    # Phase 3 — vacancy marketing and exports
    INQUIRY_RECEIVED = "inquiry_received"
    EXPORT_READY = "export_ready"
    # Phase 3 — facilities
    COMPLIANCE_EXPIRY = "compliance_expiry"
    AMENITY_BOOKING = "amenity_booking"
    UTILITY_OVERDUE = "utility_overdue"


class DeliveryStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


# Both `notifications` and `notification_preferences` use these two enums. Sharing
# one type instance per enum stops Alembic emitting a duplicate CREATE TYPE.
CHANNEL_ENUM = Enum(NotificationChannel, name="notification_channel")
TYPE_ENUM = Enum(NotificationType, name="notification_type")


class Notification(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One delivery attempt on one channel. A single event (e.g. payment confirmed)
    fans out into several rows — WhatsApp, SMS and push — each tracked separately
    so a partial failure is visible (US-031)."""

    __tablename__ = "notifications"

    channel: Mapped[NotificationChannel] = mapped_column(CHANNEL_ENUM, nullable=False)
    notification_type: Mapped[NotificationType] = mapped_column(TYPE_ENUM, nullable=False, index=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    link_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status"), default=DeliveryStatus.QUEUED, nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class NotificationPreference(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-user opt-out for one notification type on one channel. A missing row
    means 'enabled' — users only ever store their exceptions."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(TYPE_ENUM, nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(CHANNEL_ENUM, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", "channel", name="uq_notification_preference"),
    )


class PushSubscription(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Web Push endpoint registered by one browser/device (US-030)."""

    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh_key: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_key: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
