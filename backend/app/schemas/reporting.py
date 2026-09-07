import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.reporting import ReportChartType, ReportExportFormat, ReportSchedule
from app.models.vacancy import ExportKind

ALLOWED_DELIVERY_CHANNELS = {"whatsapp", "email", "in_app"}


class ReportFieldMeta(BaseModel):
    key: str
    label: str
    type: str


class ReportDefinitionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    dataset: ExportKind
    fields: list[str] = Field(default_factory=list, min_length=1)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    date_from: date | None = None
    date_to: date | None = None
    chart_type: ReportChartType = ReportChartType.TABLE
    group_by_field: str | None = None
    measure_field: str | None = None
    export_format: ReportExportFormat = ReportExportFormat.EXCEL
    schedule: ReportSchedule = ReportSchedule.NONE
    schedule_day: int | None = Field(default=None, ge=0, le=28)
    delivery_channels: list[str] = Field(default_factory=list)


class ReportDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    fields: list[str] | None = None
    filters: dict[str, list[str]] | None = None
    date_from: date | None = None
    date_to: date | None = None
    chart_type: ReportChartType | None = None
    group_by_field: str | None = None
    measure_field: str | None = None
    export_format: ReportExportFormat | None = None
    schedule: ReportSchedule | None = None
    schedule_day: int | None = Field(default=None, ge=0, le=28)
    delivery_channels: list[str] | None = None


class ReportDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    dataset: ExportKind
    fields: list[str]
    filters: dict[str, Any]
    date_from: date | None
    date_to: date | None
    chart_type: ReportChartType
    group_by_field: str | None
    measure_field: str | None
    export_format: ReportExportFormat
    schedule: ReportSchedule
    schedule_day: int | None
    delivery_channels: list[str]
    created_by_id: uuid.UUID | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReportPreviewRequest(BaseModel):
    dataset: ExportKind
    fields: list[str] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    date_from: date | None = None
    date_to: date | None = None


class ReportPreviewResult(BaseModel):
    rows: list[dict[str, Any]]
    row_count: int


class MonthlyReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    period_start: date
    period_end: date
    delivered_channels: list[str]
    delivered_at: datetime | None
    created_at: datetime
    download_url: str | None = None
