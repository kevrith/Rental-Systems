"""Vacancy listings and the lead pipeline (US-074, US-075).

A vacant unit costs money every day it stays empty, and the two things that fill
it are a link somebody can share and a list of who has already asked. This module
is both: a public listing with a token of its own, and an `Inquiry` row for every
person who got in touch before they were ready to fill in a full application.

The listing token is deliberately not the unit id. A unit id appears in operator
URLs and in exports; a listing token is meant to be pasted into WhatsApp groups,
so it gets its own opaque value that can be rotated if a listing is over-shared.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

ZERO = Decimal("0.00")


class ListingStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    # Closed automatically when the unit is occupied, or by hand.
    CLOSED = "closed"


class VacancyListing(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The shareable advert for one vacant unit (US-074)."""

    __tablename__ = "vacancy_listings"

    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Opaque and rotatable, so an over-shared link can be replaced without
    # touching the unit it advertises.
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, name="listing_status"),
        default=ListingStatus.PUBLISHED,
        nullable=False,
        index=True,
    )
    # The day the unit actually became empty, which is what days-vacant counts
    # from — not the day somebody got round to listing it.
    vacant_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def days_vacant(self) -> int | None:
        if self.vacant_since is None:
            return None
        end = self.closed_at.date() if self.closed_at else date.today()
        return max((end - self.vacant_since).days, 0)


class LeadStage(str, enum.Enum):
    """Where someone is in the pipeline for one vacancy (US-075)."""

    INQUIRED = "inquired"
    APPLIED = "applied"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    LOST = "lost"


OPEN_LEAD_STAGES: tuple[LeadStage, ...] = (
    LeadStage.INQUIRED,
    LeadStage.APPLIED,
    LeadStage.UNDER_REVIEW,
)


class Inquiry(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone who asked about a unit but has not applied yet.

    Deliberately tiny — a name and a phone number is all a person will give
    before they have seen the place, and asking for more loses the lead.
    """

    __tablename__ = "inquiries"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Where this lead came from (Sprint 23, US-099): "direct" is the public
    # listing page; a connected portal tags its own inquiries so the pipeline
    # shows which channel is actually producing leads.
    source: Mapped[str] = mapped_column(String(32), default="direct", server_default="direct", nullable=False)

    stage: Mapped[LeadStage] = mapped_column(
        Enum(LeadStage, name="lead_stage"), default=LeadStage.INQUIRED, nullable=False, index=True
    )
    # Set once the inquiry turns into a real application, which is what makes the
    # conversion rate in US-075 computable rather than guessed at.
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_applications.id", ondelete="SET NULL"), nullable=True
    )

    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_stale(self) -> bool:
        """No contact for three days, and still open (US-075)."""
        from datetime import UTC, timedelta

        if self.stage not in OPEN_LEAD_STAGES:
            return False
        last = self.last_contacted_at or self.created_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return datetime.now(UTC) - last > timedelta(days=3)


class ExportFormat(str, enum.Enum):
    CSV = "csv"
    EXCEL = "excel"


class ExportKind(str, enum.Enum):
    TENANTS = "tenants"
    TENANCIES = "tenancies"
    PAYMENTS = "payments"
    PROPERTIES = "properties"
    UNITS = "units"
    INVOICES = "invoices"


class DataExport(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A generated export, kept so a large one can be built in the background and
    collected later (US-077)."""

    __tablename__ = "data_exports"

    kind: Mapped[ExportKind] = mapped_column(Enum(ExportKind, name="export_kind"), nullable=False)
    export_format: Mapped[ExportFormat] = mapped_column(
        Enum(ExportFormat, name="export_format"), default=ExportFormat.CSV, nullable=False
    )
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
