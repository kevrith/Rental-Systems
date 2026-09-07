import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.vacancy import ExportFormat, ExportKind, LeadStage, ListingStatus


class ListingUpdate(BaseModel):
    headline: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    status: ListingStatus | None = None
    vacant_since: date | None = None


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    unit_id: uuid.UUID
    slug: str
    headline: str | None
    description: str | None
    contact_name: str | None
    contact_phone: str | None
    status: ListingStatus
    vacant_since: date | None
    published_at: datetime | None
    closed_at: datetime | None
    view_count: int
    days_vacant: int | None
    created_at: datetime


class PublicListing(BaseModel):
    """The advert itself. Everything here is safe for a stranger to see."""

    slug: str
    unit_id: uuid.UUID
    unit_number: str
    unit_type: str | None
    bedrooms: int | None
    bathrooms: int | None
    size_sqm: float | None
    features: list[str]
    monthly_rent: float
    deposit_amount: float
    headline: str | None
    description: str | None
    property_name: str
    property_address: str
    county: str | None
    latitude: float | None
    longitude: float | None
    amenities: list[str]
    contact_name: str | None
    contact_phone: str | None
    photo_urls: list[str]


class InquiryCreate(BaseModel):
    """Deliberately short: a name and a number is all anyone gives before a viewing."""

    full_name: str = Field(min_length=2, max_length=255)
    phone_number: str = Field(min_length=10, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=1000)


class InquiryUpdate(BaseModel):
    stage: LeadStage | None = None
    notes: str | None = Field(default=None, max_length=2000)
    mark_contacted: bool = False


class InquiryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unit_id: uuid.UUID
    full_name: str
    phone_number: str
    email: str | None
    message: str | None
    stage: LeadStage
    source: str = "direct"
    application_id: uuid.UUID | None
    last_contacted_at: datetime | None
    notes: str | None
    is_stale: bool
    created_at: datetime


class InquiryDetail(InquiryRead):
    unit_number: str | None = None
    property_name: str | None = None


class VacancyRow(BaseModel):
    unit_id: str
    unit_number: str
    property_name: str
    status: str
    monthly_rent: float
    vacant_since: str | None
    days_vacant: int | None
    revenue_lost: float
    listing_slug: str | None
    listing_status: str | None
    views: int
    open_leads: int
    applications: int


class VacancyReport(BaseModel):
    vacant_units: int
    total_revenue_lost: float
    monthly_revenue_at_risk: float
    units: list[VacancyRow]


class ConversionReport(BaseModel):
    inquiries: int
    applications: int
    approvals: int
    stale_leads: int
    inquiry_to_application_percent: float | None
    application_to_approval_percent: float | None


class ExportRequest(BaseModel):
    kind: ExportKind
    export_format: ExportFormat = ExportFormat.CSV
    date_from: date | None = None
    date_to: date | None = None


class ExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ExportKind
    export_format: ExportFormat
    date_from: date | None
    date_to: date | None
    row_count: int
    file_id: uuid.UUID | None
    is_scheduled: bool
    error: str | None
    created_at: datetime


class ExportDetail(ExportRead):
    download_url: str | None = None
    requested_by_name: str | None = None
    extra: dict[str, Any] = {}
