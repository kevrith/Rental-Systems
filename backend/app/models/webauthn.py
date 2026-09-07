"""WebAuthn / biometric login (Sprint 25, US-108).

One row per registered authenticator (a phone's fingerprint sensor, a laptop's
Face ID, a hardware security key). `credential_id` and `public_key` are stored
base64url-encoded — the WebAuthn library exchanges them as bytes, but a
`bytea` column buys nothing here and text is trivial to inspect and export.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class WebauthnCredential(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webauthn_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
