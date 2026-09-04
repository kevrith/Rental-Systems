import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.bulk import BulkOperationKind, BulkOperationStatus


class BulkTargetFilter(BaseModel):
    """Who a bulk action applies to. Everything narrows from the whole portfolio."""

    property_id: uuid.UUID | None = None
    unit_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


class RentIncreasePreview(BulkTargetFilter):
    increase_type: Literal["percent", "fixed"] = "percent"
    value: Decimal = Field(gt=0)
    effective_date: date

    @model_validator(mode="after")
    def _sane_increase(self) -> "RentIncreasePreview":
        if self.effective_date <= date.today():
            raise ValueError("A rent increase must take effect in the future")
        if self.increase_type == "percent" and self.value > 100:
            raise ValueError(
                "An increase over 100% is almost always a typo. "
                "Enter it as a fixed amount if you really mean it."
            )
        return self


class ReminderPreview(BulkTargetFilter):
    pass


class AnnouncementPreview(BulkTargetFilter):
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=5, max_length=1500)


class InvoiceRunPreview(BulkTargetFilter):
    pass


class RenewalNoticePreview(BulkTargetFilter):
    within_days: int = Field(default=60, ge=1, le=365)


class DocumentDistributionPreview(BulkTargetFilter):
    document_file_id: uuid.UUID
    subject: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=1000)


class BulkOperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    kind: BulkOperationKind
    status: BulkOperationStatus
    parameters: dict[str, Any]
    targets: list[Any]
    total: int
    succeeded: int
    failed: int
    failures: list[Any]
    property_id: uuid.UUID | None
    effective_date: date | None
    started_at: datetime | None
    finished_at: datetime | None
    summary: str | None
    error: str | None
    created_at: datetime


class ImportPreview(BaseModel):
    """What the operator is shown before anything is written."""

    ready: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    total_rows: int
    ready_count: int
    error_count: int


class ImportCommit(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=2000)


class ImportResult(BaseModel):
    created: int
    failed: int
    failures: list[dict[str, Any]]
