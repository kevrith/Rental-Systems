import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LegalHold(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An explicit override that suspends retention and erasure for one entity.

    Scoped the same way `AuditLog` is (`entity_type` + `entity_id`), except
    `entity_id` is nullable: a hold with `entity_type="organization"` and no
    id covers everything in the organization, for a matter broad enough that
    naming individual tenants would miss something. A hold has no expiry —
    `retention_service.py` and `privacy_service.py` both treat any row with
    `released_at IS NULL` as active and refuse to act on whatever it covers.
    """

    __tablename__ = "legal_holds"
    __table_args__ = (Index("ix_legal_holds_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    placed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    placed_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    released_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    release_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_active(self) -> bool:
        return self.released_at is None
