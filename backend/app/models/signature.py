"""Digital signature model — Phase 2 (US-044).

Captures the full audit trail for a legally-binding OTP-verified signature.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SignatureStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED = "signed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class DigitalSignature(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An OTP-verified digital signature on a document.

    The signing link is single-use and expires after 72 hours. Once signed,
    the record is immutable — the audit trail is the legal evidence.
    """

    __tablename__ = "digital_signatures"

    # The document being signed (stored_files id)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The tenancy this signature relates to
    tenancy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenancies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Who is signing
    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    signer_role: Mapped[str] = mapped_column(String(32), nullable=False)  # "tenant", "owner", "guarantor"

    # Signing link token (hashed)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[SignatureStatus] = mapped_column(
        Enum(SignatureStatus, name="signature_status"),
        default=SignatureStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Audit trail captured at signing time
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Stored as text exactly as the browser reported them, so the audit trail
    # preserves the original precision rather than a float round-trip.
    gps_latitude: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gps_longitude: Mapped[str | None] = mapped_column(String(32), nullable=True)
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Signature image stored as base64 data URL or file reference
    signature_image: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Signed document (with signature overlaid)
    signed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )

    otp_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
