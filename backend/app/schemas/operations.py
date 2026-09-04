import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.operations import (
    MaintenanceCategory,
    MaintenancePriority,
    MaintenanceStatus,
    MeterType,
    RejectionReason,
    VacateNoticeStatus,
)
from app.schemas.maintenance import MaintenanceTimelineEntry, VendorSummary


class MeterReadingCreate(BaseModel):
    unit_id: uuid.UUID
    meter_type: MeterType
    current_reading: Decimal = Field(ge=0)
    reading_date: date
    photo_file_id: uuid.UUID = Field(description="A photo of the meter is mandatory")
    previous_reading: Decimal | None = Field(default=None, ge=0)
    rate: Decimal | None = Field(default=None, ge=0, description="Overrides the property rate")
    notes: str | None = Field(default=None, max_length=1000)
    gps_latitude: float | None = Field(default=None, ge=-90, le=90)
    gps_longitude: float | None = Field(default=None, ge=-180, le=180)


class MeterReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    unit_id: uuid.UUID
    meter_type: MeterType
    previous_reading: Decimal
    current_reading: Decimal
    consumption: Decimal
    rate: Decimal
    amount: Decimal
    reading_date: date
    photo_file_id: uuid.UUID | None
    billed_invoice_id: uuid.UUID | None
    notes: str | None
    created_at: datetime


class MeterReadingDetail(MeterReadingRead):
    unit_number: str | None = None
    property_name: str | None = None
    photo_url: str | None = None
    recorded_by_name: str | None = None


class MeterContext(BaseModel):
    """Everything the capture form needs pre-filled before the caretaker types."""

    unit_id: uuid.UUID
    unit_number: str
    property_name: str
    meter_type: MeterType
    previous_reading: Decimal
    previous_reading_date: date | None
    rate: Decimal
    has_rate_configured: bool


# -------------------------------------------------------------------- maintenance


class MaintenanceCreate(BaseModel):
    unit_id: uuid.UUID
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    category: MaintenanceCategory = MaintenanceCategory.OTHER
    priority: MaintenancePriority = MaintenancePriority.ROUTINE
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _photo_required_for_urgent(self) -> "MaintenanceCreate":
        if self.priority != MaintenancePriority.ROUTINE and not self.photo_file_ids:
            raise ValueError("At least one photo is required for urgent and emergency requests")
        return self


class MaintenanceUpdate(BaseModel):
    """Edits to the request itself.

    Status is deliberately absent: every state change goes through its own
    action endpoint (`/approve`, `/assign`, `/complete`, ...) so the required
    fields and the audit summary for each move cannot be bypassed.
    """

    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=3)
    category: MaintenanceCategory | None = None
    priority: MaintenancePriority | None = None
    resolution_notes: str | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    expected_completion_date: date | None = None


class MaintenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    unit_id: uuid.UUID
    tenancy_id: uuid.UUID | None
    title: str
    description: str
    category: MaintenanceCategory
    priority: MaintenancePriority
    status: MaintenanceStatus
    photo_file_ids: list[uuid.UUID]
    resolution_notes: str | None
    cost: Decimal | None
    estimated_cost: Decimal | None
    acknowledged_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    # Lifecycle (Sprint 13)
    vendor_id: uuid.UUID | None = None
    expected_completion_date: date | None = None
    is_overdue: bool = False
    approved_at: datetime | None = None
    reviewed_at: datetime | None = None
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    closed_at: datetime | None = None
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = None
    info_requested: str | None = None
    vendor_rating: int | None = None
    vendor_review: str | None = None
    tenant_rating: int | None = None
    tenant_feedback: str | None = None
    owner_expense_allocated: bool = False


class MaintenanceDetail(MaintenanceRead):
    unit_number: str | None = None
    property_name: str | None = None
    property_id: uuid.UUID | None = None
    reported_by_name: str | None = None
    approved_by_name: str | None = None
    photo_urls: list[str] = []
    vendor: VendorSummary | None = None
    cost_variance: Decimal | None = None
    days_open: int | None = None
    timeline: list[MaintenanceTimelineEntry] = []


# ------------------------------------------------------------------ vacate notice


class VacateNoticeCreate(BaseModel):
    tenancy_id: uuid.UUID
    move_out_date: date
    reason: str | None = Field(default=None, max_length=2000)


class VacateNoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    tenancy_id: uuid.UUID
    move_out_date: date
    reason: str | None
    notice_days_given: int
    meets_notice_period: bool
    status: VacateNoticeStatus
    acknowledged_at: datetime | None
    document_id: uuid.UUID | None
    created_at: datetime


class VacateNoticeDetail(VacateNoticeRead):
    tenant_name: str | None = None
    unit_number: str | None = None
    property_name: str | None = None
    required_notice_days: int = 30
    document_url: str | None = None


# ---------------------------------------------------------------------- activity


class ActivityEntry(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str | None
    actor_name: str | None
    user_id: uuid.UUID | None
    created_at: datetime
    gps_latitude: float | None = None
    gps_longitude: float | None = None


class CaretakerActivitySummary(BaseModel):
    user_id: uuid.UUID
    full_name: str
    payments_recorded: int
    meter_readings: int
    maintenance_requests: int
    unit_status_changes: int
    last_login_at: datetime | None
    days_since_login: int | None
    total_actions: int


class CaretakerTaskList(BaseModel):
    """The caretaker home screen (US-024)."""

    readings_due: list[MeterContext]
    open_maintenance: list[MaintenanceDetail]
    units_vacant: int
    tenants_in_arrears: int
    recent_activity: list[ActivityEntry]
