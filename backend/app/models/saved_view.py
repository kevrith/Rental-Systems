import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SavedView(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named, reusable set of filters for one list screen (Sprint 26A, item 11).

    `entity_type` is whatever string the frontend list page identifies itself
    with (`"tenants"`, `"maintenance"`, ...) — not an enum, since a new list
    screen adopting saved views should not need a migration to do it.
    `filters` is a JSONB bag shaped however that page's own filter state is
    shaped; this table has no opinion on what a "tenant filter" looks like,
    only on storing and naming one. Private to the user who made it unless
    `is_shared`, in which case every member of the organisation sees it too —
    the common case for "the view the whole team uses," e.g. an operations
    lead's "overdue and unassigned" maintenance view.
    """

    __tablename__ = "saved_views"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "name", name="uq_saved_view_user_entity_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
