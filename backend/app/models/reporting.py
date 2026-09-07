"""Custom report builder and scheduled monthly reports — Sprint 21 (US-093/094).

`ReportDefinition` is a saved, replayable query over the same six datasets
`export_service` already knows how to shape (`ExportKind`, reused rather than
duplicated) — a chosen column set, a set of equality filters, an optional
chart projection, and an optional delivery schedule. `MonthlyReport` is the
simpler, unconfigurable cousin: one row per organisation per calendar month,
generated and delivered automatically, kept so the last 12 months are always
browsable without regenerating anything.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.vacancy import ExportKind


class ReportChartType(str, enum.Enum):
    TABLE = "table"
    BAR = "bar"
    LINE = "line"
    PIE = "pie"


class ReportSchedule(str, enum.Enum):
    NONE = "none"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportExportFormat(str, enum.Enum):
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"


class ReportDefinition(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved custom report: a dataset, a column selection, filters, and an
    optional chart and delivery schedule."""

    __tablename__ = "report_definitions"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    dataset: Mapped[ExportKind] = mapped_column(Enum(ExportKind, name="export_kind"), nullable=False)

    # Ordered subset of the keys export_service's row-shaping function for this
    # dataset returns — see reporting_service.DATASET_FIELDS.
    fields: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    # field name -> allowed values, applied as an exact-match-in-list filter.
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    chart_type: Mapped[ReportChartType] = mapped_column(
        Enum(ReportChartType, name="report_chart_type"), default=ReportChartType.TABLE, nullable=False
    )
    # Only meaningful when chart_type != TABLE — both must be in `fields`.
    group_by_field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    measure_field: Mapped[str | None] = mapped_column(String(100), nullable=True)

    export_format: Mapped[ReportExportFormat] = mapped_column(
        Enum(ReportExportFormat, name="report_export_format"),
        default=ReportExportFormat.EXCEL,
        nullable=False,
    )
    schedule: Mapped[ReportSchedule] = mapped_column(
        Enum(ReportSchedule, name="report_schedule"), default=ReportSchedule.NONE, nullable=False
    )
    # Weekly: 0 (Monday) - 6 (Sunday). Monthly: 1-28.
    schedule_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Values from {"whatsapp", "email", "in_app"}.
    delivery_channels: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )


class MonthlyReport(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One automatically generated financial summary per organisation per
    calendar month (US-093). Unique per period so the scheduler is idempotent."""

    __tablename__ = "monthly_reports"

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="SET NULL"), nullable=True
    )
    delivered_channels: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "period_start", name="uq_monthly_report_org_period"),
    )
