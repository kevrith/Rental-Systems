"""AI lease document intelligence (Sprint 22, US-096).

`LeaseAnalysis` is one Claude review of one lease template's body at the
moment the owner asked for it — a new analysis is a new row, not an update, so
the history of what the AI once flagged survives even after suggestions are
resolved. Each finding is its own `LeaseSuggestion`, accepted or dismissed
individually: the acceptance criteria are explicit that the AI never edits a
lease itself, only proposes wording an owner approves one clause at a time.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LeaseSuggestionCategory(str, enum.Enum):
    MISSING_CLAUSE = "missing_clause"
    PROBLEMATIC_TERM = "problematic_term"
    UNCLEAR_LANGUAGE = "unclear_language"


class LeaseSuggestionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class LeaseAnalysis(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lease_analyses"

    lease_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lease_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    suggestions: Mapped[list["LeaseSuggestion"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="LeaseSuggestion.created_at",
    )


class LeaseSuggestion(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lease_suggestions"

    lease_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lease_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[LeaseSuggestionCategory] = mapped_column(
        Enum(LeaseSuggestionCategory, name="lease_suggestion_category"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    # A drop-in clause or replacement wording. Blank for a suggestion that is
    # purely a flag (e.g. "this clause is unenforceable") with nothing to insert.
    suggested_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeaseSuggestionStatus] = mapped_column(
        Enum(LeaseSuggestionStatus, name="lease_suggestion_status"),
        default=LeaseSuggestionStatus.PENDING,
        nullable=False,
        index=True,
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis: Mapped["LeaseAnalysis"] = relationship(back_populates="suggestions")
