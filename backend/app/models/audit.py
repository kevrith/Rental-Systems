import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only record of every state change and caretaker action.

    Doubles as the caretaker activity log (US-028) — hence the optional GPS
    columns, which mobile clients populate when the user grants location access.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Hash chain (Sprint 26A) — see `app/services/audit_chain_service.py`. Left
    # null at insert time; a scheduled task fills both columns in shortly
    # after, in append order, chaining each row's HMAC onto the previous
    # row's. `record()` itself stays synchronous and untouched by this — every
    # one of its ~130 call sites keeps working exactly as before, and rows
    # only ever get chained going forward, never rewritten.
    prev_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
