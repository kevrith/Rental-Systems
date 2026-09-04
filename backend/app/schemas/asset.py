import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.asset import AgreementStatus, AssetKind, AssetStatus, FuelPolicy, RateBasis


class AssetCreate(BaseModel):
    kind: AssetKind
    name: str = Field(min_length=2, max_length=255)
    property_id: uuid.UUID | None = None
    daily_rate: Decimal = Field(ge=0, le=Decimal("9999999.99"))
    weekly_rate: Decimal | None = Field(default=None, ge=0)
    monthly_rate: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)

    # Vehicles
    registration_number: str | None = Field(default=None, max_length=32)
    make: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=64)
    year: int | None = Field(default=None, ge=1950, le=2100)
    colour: str | None = Field(default=None, max_length=32)
    mileage: int | None = Field(default=None, ge=0)
    fuel_policy: FuelPolicy = FuelPolicy.FULL_TO_FULL
    daily_mileage_limit: int | None = Field(default=None, ge=0)
    excess_mileage_rate: Decimal | None = Field(default=None, ge=0)
    insurance_expiry: date | None = None
    inspection_expiry: date | None = None
    road_licence_expiry: date | None = None

    # Equipment
    serial_number: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=64)
    service_interval_days: int | None = Field(default=None, ge=1, le=3650)
    last_serviced_on: date | None = None

    @model_validator(mode="after")
    def _kind_has_its_identifier(self) -> "AssetCreate":
        if self.kind == AssetKind.VEHICLE and not (self.registration_number or "").strip():
            raise ValueError("A vehicle needs its registration number")
        if self.kind == AssetKind.EQUIPMENT and not (self.serial_number or "").strip():
            raise ValueError("Equipment needs a serial number so it can be told apart")
        return self


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    status: AssetStatus | None = None
    daily_rate: Decimal | None = Field(default=None, ge=0)
    weekly_rate: Decimal | None = Field(default=None, ge=0)
    monthly_rate: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    mileage: int | None = Field(default=None, ge=0)
    fuel_policy: FuelPolicy | None = None
    daily_mileage_limit: int | None = Field(default=None, ge=0)
    excess_mileage_rate: Decimal | None = Field(default=None, ge=0)
    insurance_expiry: date | None = None
    inspection_expiry: date | None = None
    road_licence_expiry: date | None = None
    service_interval_days: int | None = Field(default=None, ge=1, le=3650)
    last_serviced_on: date | None = None
    is_archived: bool | None = None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    kind: AssetKind
    name: str
    property_id: uuid.UUID | None
    status: AssetStatus
    daily_rate: Decimal
    weekly_rate: Decimal | None
    monthly_rate: Decimal | None
    deposit_amount: Decimal
    notes: str | None
    registration_number: str | None
    make: str | None
    model: str | None
    year: int | None
    colour: str | None
    mileage: int | None
    fuel_policy: FuelPolicy
    daily_mileage_limit: int | None
    excess_mileage_rate: Decimal | None
    insurance_expiry: date | None
    inspection_expiry: date | None
    road_licence_expiry: date | None
    serial_number: str | None
    category: str | None
    service_interval_days: int | None
    last_serviced_on: date | None
    service_due_on: date | None
    compliance_warnings: list[str]
    created_at: datetime


class AssetDetail(AssetRead):
    photo_urls: list[str] = []
    current_hire: str | None = None
    current_hirer: str | None = None


class AgreementCreate(BaseModel):
    asset_id: uuid.UUID
    tenant_id: uuid.UUID
    start_date: date
    end_date: date
    rate_basis: RateBasis = RateBasis.DAILY
    rate: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _sane_window(self) -> "AgreementCreate":
        if self.end_date < self.start_date:
            raise ValueError("The hire ends before it starts")
        return self


class CheckOut(BaseModel):
    mileage: int | None = Field(default=None, ge=0)
    fuel_eighths: int | None = Field(default=None, ge=0, le=8)
    condition_notes: str | None = Field(default=None, max_length=4000)
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    driver_licence_file_id: uuid.UUID | None = None
    # Handing out an asset with lapsed insurance has to be a deliberate,
    # attributable act rather than something that just happens.
    override_compliance: bool = False
    override_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _override_needs_a_reason(self) -> "CheckOut":
        if self.override_compliance and not (self.override_reason or "").strip():
            raise ValueError("An override needs a written reason")
        return self


class CheckIn(BaseModel):
    mileage: int | None = Field(default=None, ge=0)
    fuel_eighths: int | None = Field(default=None, ge=0, le=8)
    condition_notes: str | None = Field(default=None, max_length=4000)
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    damage_charge: Decimal | None = Field(default=None, ge=0)
    returned_on: date | None = None


class AgreementCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class AgreementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    asset_id: uuid.UUID
    tenant_id: uuid.UUID
    start_date: date
    end_date: date
    rate_basis: RateBasis
    rate: Decimal
    deposit_amount: Decimal
    deposit_refunded: Decimal | None
    status: AgreementStatus
    checked_out_at: datetime | None
    mileage_out: int | None
    fuel_out_eighths: int | None
    condition_out: str | None
    checked_in_at: datetime | None
    mileage_in: int | None
    fuel_in_eighths: int | None
    condition_in: str | None
    hire_charge: Decimal
    excess_mileage_charge: Decimal
    damage_charge: Decimal
    fuel_charge: Decimal
    late_charge: Decimal
    total_charge: Decimal
    notes: str | None
    cancelled_reason: str | None
    hire_days: int
    mileage_covered: int | None
    is_overdue: bool
    created_at: datetime


class AgreementDetail(AgreementRead):
    asset_name: str | None = None
    asset_kind: AssetKind | None = None
    registration_number: str | None = None
    hirer_name: str | None = None
    hirer_phone: str | None = None
    photos_out_urls: list[str] = []
    photos_in_urls: list[str] = []


class AvailabilityRow(BaseModel):
    agreement_id: str
    reference_code: str
    start_date: str
    end_date: str
    status: str
    hirer: str | None


class ComplianceWarning(BaseModel):
    asset_id: str
    name: str
    reference_code: str
    kind: str
    warnings: list[str]


class FleetOverview(BaseModel):
    total_assets: int
    vehicles: int
    equipment: int
    on_hire: int
    available: int
    in_maintenance: int
    overdue_returns: int
    revenue_this_month: float
    compliance_warnings: list[ComplianceWarning]
