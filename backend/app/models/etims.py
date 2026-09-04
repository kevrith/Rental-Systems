"""KRA eTIMS models — Phase 2 (US-053).

Kenya's Electronic Tax Invoice Management System. A landlord registered for VAT
must have every receipt signed by KRA, which returns a control unit serial and an
invoice number that together prove the receipt was declared.

Two things live here: the landlord's credentials, held encrypted because they are
the landlord's own KRA identity and not ours to leak; and one row per submission
attempt, because "did this receipt reach KRA?" must be answerable months later.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EtimsStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"
    # Retries are exhausted; a person has to look at it.
    ABANDONED = "abandoned"


class EtimsCredential(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organisation's eTIMS registration. At most one row per organisation."""

    __tablename__ = "etims_credentials"

    kra_pin: Mapped[str] = mapped_column(String(32), nullable=False)
    # KRA issues these per device; they are the landlord's, so both are stored
    # encrypted (see `app.core.crypto`) and never returned by the API.
    device_serial_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    branch_id: Mapped[str] = mapped_column(String(16), default="00", server_default="00", nullable=False)

    environment: Mapped[str] = mapped_column(
        String(16), default="sandbox", server_default="sandbox", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (UniqueConstraint("organization_id", name="uq_etims_credential_per_org"),)


class EtimsSubmission(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One receipt's journey to KRA, including every failed attempt."""

    __tablename__ = "etims_submissions"

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[EtimsStatus] = mapped_column(
        Enum(EtimsStatus, name="etims_status"),
        default=EtimsStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # What KRA gave back. `verification_url` is what the QR code encodes.
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_unit_serial: Mapped[str | None] = mapped_column(String(64), nullable=True)
    control_unit_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # The raw KRA response, kept verbatim: it is the evidence in a tax dispute.
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("receipt_id", name="uq_etims_submission_per_receipt"),)
