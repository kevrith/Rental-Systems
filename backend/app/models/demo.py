"""Sample data for a new account (Module 24).

A landlord evaluating RentFlow on an empty account sees empty screens, which
tells them nothing about whether the product would help. Demo mode fills the
account with a plausible small portfolio — a block of flats, tenants at
various stages of paying, a couple of open maintenance jobs — so every report
and dashboard has something in it on the first click.

The problem with seeded data is removing it again. Rather than tagging a
dozen tables with an `is_demo` column, one `DemoDataset` row records exactly
which ids were created, in creation order. Teardown walks that list in
reverse, so it deletes precisely what was seeded and can never touch a row
the customer entered themselves.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DemoDataset(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The receipt for one seeding run, and the instructions for undoing it."""

    __tablename__ = "demo_datasets"

    # `[{"table": "tenancies", "id": "..."}, ...]` in creation order.
    created_rows: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Which seed script produced this, so a future revision of the sample
    # portfolio can be told apart from what an older account was given.
    recipe: Mapped[str] = mapped_column(String(64), default="starter_portfolio", nullable=False)

    seeded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
