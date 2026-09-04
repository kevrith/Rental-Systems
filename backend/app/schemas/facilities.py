import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.facilities import (
    AmenityKind,
    BayType,
    BookingStatus,
    ComplianceStatus,
    ComplianceType,
    UtilityAccountType,
    UtilityPaymentStatus,
)


class ComplianceCreate(BaseModel):
    property_id: uuid.UUID
    compliance_type: ComplianceType
    name: str = Field(min_length=2, max_length=255)
    reference_number: str | None = Field(default=None, max_length=128)
    issued_on: date | None = None
    expires_on: date | None = None
    issuing_authority: str | None = Field(default=None, max_length=255)
    responsible_party: str | None = Field(default=None, max_length=255)
    responsible_phone: str | None = Field(default=None, max_length=32)
    document_id: uuid.UUID | None = None
    insurer_name: str | None = Field(default=None, max_length=255)
    insurer_contact: str | None = Field(default=None, max_length=64)
    coverage_amount: Decimal | None = Field(default=None, ge=0)
    premium_amount: Decimal | None = Field(default=None, ge=0)
    premium_due_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _expiry_after_issue(self) -> "ComplianceCreate":
        if self.issued_on and self.expires_on and self.expires_on <= self.issued_on:
            raise ValueError("A certificate cannot expire before it was issued")
        return self


class ComplianceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    reference_number: str | None = Field(default=None, max_length=128)
    issued_on: date | None = None
    expires_on: date | None = None
    issuing_authority: str | None = Field(default=None, max_length=255)
    responsible_party: str | None = Field(default=None, max_length=255)
    responsible_phone: str | None = Field(default=None, max_length=32)
    document_id: uuid.UUID | None = None
    insurer_name: str | None = Field(default=None, max_length=255)
    insurer_contact: str | None = Field(default=None, max_length=64)
    coverage_amount: Decimal | None = Field(default=None, ge=0)
    premium_amount: Decimal | None = Field(default=None, ge=0)
    premium_due_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_archived: bool | None = None


class ComplianceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    compliance_type: ComplianceType
    name: str
    reference_number: str | None
    issued_on: date | None
    expires_on: date | None
    issuing_authority: str | None
    responsible_party: str | None
    responsible_phone: str | None
    document_id: uuid.UUID | None
    insurer_name: str | None
    insurer_contact: str | None
    coverage_amount: Decimal | None
    premium_amount: Decimal | None
    premium_due_on: date | None
    notes: str | None
    status: ComplianceStatus
    days_until_expiry: int | None
    created_at: datetime


class ComplianceDetail(ComplianceRead):
    property_name: str | None = None
    document_url: str | None = None


class BayCreate(BaseModel):
    property_id: uuid.UUID
    bay_number: str = Field(min_length=1, max_length=32)
    bay_type: BayType = BayType.OPEN
    level: str | None = Field(default=None, max_length=32)
    monthly_fee: Decimal = Field(default=Decimal("0.00"), ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class AllocationCreate(BaseModel):
    tenancy_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, max_length=255)
    guest_phone: str | None = Field(default=None, max_length=32)
    vehicle_registration: str | None = Field(default=None, max_length=32)
    start_date: date
    end_date: date | None = None
    monthly_fee: Decimal | None = Field(default=None, ge=0)
    bill_monthly: bool = True
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _someone_holds_it(self) -> "AllocationCreate":
        if self.tenancy_id is None and not (self.guest_name or "").strip():
            raise ValueError("A bay goes either to a tenancy or to a named visitor")
        if self.tenancy_id is None and self.end_date is None:
            raise ValueError("A visitor allocation needs an end date")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("The allocation ends before it starts")
        return self


class AllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bay_id: uuid.UUID
    tenancy_id: uuid.UUID | None
    guest_name: str | None
    guest_phone: str | None
    vehicle_registration: str | None
    start_date: date
    end_date: date | None
    monthly_fee: Decimal
    bill_monthly: bool
    released_at: datetime | None
    is_current: bool
    created_at: datetime


class BayRow(BaseModel):
    bay_id: str
    bay_number: str
    bay_type: str
    level: str | None
    monthly_fee: float
    is_active: bool
    allocation_id: str | None
    holder: str | None
    vehicle_registration: str | None
    allocated_until: str | None


class ParkingOverview(BaseModel):
    total_bays: int
    allocated: int
    available: int
    monthly_parking_income: float
    bays: list[BayRow]


class AmenityCreate(BaseModel):
    property_id: uuid.UUID
    name: str = Field(min_length=2, max_length=255)
    kind: AmenityKind = AmenityKind.OTHER
    description: str | None = Field(default=None, max_length=2000)
    max_hours_per_booking: int = Field(default=2, ge=1, le=24)
    min_notice_hours: int = Field(default=2, ge=0, le=168)
    max_bookings_per_week: int = Field(default=3, ge=1, le=50)
    opens_at_hour: int = Field(default=6, ge=0, le=23)
    closes_at_hour: int = Field(default=22, ge=1, le=24)
    is_bookable: bool = True
    booking_fee: Decimal = Field(default=Decimal("0.00"), ge=0)

    @model_validator(mode="after")
    def _opens_before_it_closes(self) -> "AmenityCreate":
        if self.closes_at_hour <= self.opens_at_hour:
            raise ValueError("The amenity closes before it opens")
        return self


class AmenityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    name: str
    kind: AmenityKind
    description: str | None
    max_hours_per_booking: int
    min_notice_hours: int
    max_bookings_per_week: int
    opens_at_hour: int
    closes_at_hour: int
    is_bookable: bool
    booking_fee: Decimal
    created_at: datetime


class BookingCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    tenancy_id: uuid.UUID | None = None
    purpose: str | None = Field(default=None, max_length=255)
    guests: int = Field(default=0, ge=0, le=500)


class BlockCreate(BaseModel):
    """A manager taking the amenity out of service."""

    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=3, max_length=255)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amenity_id: uuid.UUID
    tenancy_id: uuid.UUID | None
    tenant_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    purpose: str | None
    guests: int
    created_at: datetime


class BookingDetail(BookingRead):
    tenant_name: str | None = None
    amenity_name: str | None = None


class AmenityUsageRow(BaseModel):
    amenity_id: str
    name: str
    kind: str
    bookings: int
    hours_booked: float
    distinct_tenants: int


class UtilityAccountUpsert(BaseModel):
    property_id: uuid.UUID
    account_type: UtilityAccountType
    account_number: str = Field(min_length=2, max_length=64)
    account_name: str | None = Field(default=None, max_length=255)
    provider: str | None = Field(default=None, max_length=128)
    next_due_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class UtilityStatusUpdate(BaseModel):
    payment_status: UtilityPaymentStatus
    last_paid_on: date | None = None
    last_amount: Decimal | None = Field(default=None, ge=0)
    next_due_on: date | None = None


class UtilityAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    account_type: UtilityAccountType
    account_number: str
    account_name: str | None
    provider: str | None
    payment_status: UtilityPaymentStatus
    last_paid_on: date | None
    last_amount: Decimal | None
    next_due_on: date | None
    status_updated_at: datetime | None
    notes: str | None
    is_overdue: bool
    created_at: datetime
