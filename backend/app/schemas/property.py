import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.property import LateFeeType, PropertyType, UnitStatus


class PropertyBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    property_type: PropertyType = PropertyType.RESIDENTIAL
    address: str = Field(min_length=3, max_length=512)
    county: str | None = Field(default=None, max_length=128)
    sub_county: str | None = Field(default=None, max_length=128)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = None
    amenities: list[str] = []
    water_rate_per_unit: Decimal | None = Field(default=None, ge=0)
    electricity_rate_per_unit: Decimal | None = Field(default=None, ge=0)
    grace_period_days: int = Field(default=5, ge=0, le=90)
    # Late fees (US-055). Leave `late_fee_type` null to charge nothing.
    late_fee_type: LateFeeType | None = None
    late_fee_amount: Decimal | None = Field(default=None, ge=0)
    late_fee_cap: Decimal | None = Field(default=None, ge=0)
    # Monthly maintenance allowance for budget-vs-actual reporting (US-062).
    maintenance_budget_monthly: Decimal | None = Field(default=None, ge=0)
    # Agency mode: which owner client this property belongs to. Null in owner mode.
    owner_profile_id: uuid.UUID | None = None


class PropertyCreate(PropertyBase):
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class PropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    property_type: PropertyType | None = None
    address: str | None = Field(default=None, min_length=3, max_length=512)
    county: str | None = Field(default=None, max_length=128)
    sub_county: str | None = Field(default=None, max_length=128)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = None
    amenities: list[str] | None = None
    water_rate_per_unit: Decimal | None = Field(default=None, ge=0)
    electricity_rate_per_unit: Decimal | None = Field(default=None, ge=0)
    grace_period_days: int | None = Field(default=None, ge=0, le=90)
    late_fee_type: LateFeeType | None = None
    late_fee_amount: Decimal | None = Field(default=None, ge=0)
    late_fee_cap: Decimal | None = Field(default=None, ge=0)
    maintenance_budget_monthly: Decimal | None = Field(default=None, ge=0)
    owner_profile_id: uuid.UUID | None = None
    photo_file_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)


class PhotoRead(BaseModel):
    id: uuid.UUID
    url: str
    filename: str


class PropertyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    name: str
    property_type: PropertyType
    address: str
    county: str | None
    sub_county: str | None
    latitude: float | None
    longitude: float | None
    description: str | None
    amenities: list[str]
    water_rate_per_unit: Decimal | None
    electricity_rate_per_unit: Decimal | None
    grace_period_days: int
    late_fee_type: LateFeeType | None = None
    late_fee_amount: Decimal | None = None
    late_fee_cap: Decimal | None = None
    maintenance_budget_monthly: Decimal | None = None
    owner_profile_id: uuid.UUID | None = None
    is_archived: bool
    created_at: datetime


class PropertySummary(PropertyRead):
    """Property plus the occupancy roll-up the portfolio cards show."""

    total_units: int = 0
    occupied_units: int = 0
    vacant_units: int = 0
    maintenance_units: int = 0
    reserved_units: int = 0
    occupancy_rate: float = 0.0
    monthly_rent_potential: Decimal = Decimal("0.00")
    photos: list[PhotoRead] = []


# ------------------------------------------------------------------------- units


class UnitBase(BaseModel):
    unit_number: str = Field(min_length=1, max_length=64)
    unit_type: str | None = Field(default=None, max_length=64)
    size_sqm: float | None = Field(default=None, ge=0)
    floor: str | None = Field(default=None, max_length=32)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: int | None = Field(default=None, ge=0, le=50)
    monthly_rent: Decimal = Field(default=Decimal("0.00"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    features: list[str] = []


class UnitCreate(UnitBase):
    property_id: uuid.UUID
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class UnitBulkCreate(BaseModel):
    """'This property has 24 identical units' (US-008)."""

    property_id: uuid.UUID
    count: int = Field(ge=1, le=500)
    name_prefix: str = Field(default="", max_length=32)
    start_number: int = Field(default=1, ge=0)
    number_padding: int = Field(default=0, ge=0, le=6, description="Zero-pad to this width, e.g. 3 -> 001")
    unit_type: str | None = Field(default=None, max_length=64)
    size_sqm: float | None = Field(default=None, ge=0)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: int | None = Field(default=None, ge=0, le=50)
    monthly_rent: Decimal = Field(default=Decimal("0.00"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    features: list[str] = []

    def unit_numbers(self) -> list[str]:
        numbers = []
        for offset in range(self.count):
            value = self.start_number + offset
            text = str(value).zfill(self.number_padding) if self.number_padding else str(value)
            numbers.append(f"{self.name_prefix}{text}")
        return numbers


class UnitUpdate(BaseModel):
    unit_number: str | None = Field(default=None, min_length=1, max_length=64)
    unit_type: str | None = Field(default=None, max_length=64)
    size_sqm: float | None = Field(default=None, ge=0)
    floor: str | None = Field(default=None, max_length=32)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: int | None = Field(default=None, ge=0, le=50)
    monthly_rent: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    features: list[str] | None = None
    photo_file_ids: list[uuid.UUID] | None = Field(default=None, max_length=5)


class UnitStatusUpdate(BaseModel):
    status: UnitStatus
    expected_vacancy_date: date | None = None
    note: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _require_date_for_vacating(self) -> "UnitStatusUpdate":
        if self.status == UnitStatus.VACATING and self.expected_vacancy_date is None:
            raise ValueError("expected_vacancy_date is required when marking a unit as vacating")
        return self


class UnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    property_id: uuid.UUID
    reference_code: str
    unit_number: str
    unit_type: str | None
    size_sqm: float | None
    floor: str | None
    bedrooms: int | None
    bathrooms: int | None
    monthly_rent: Decimal
    deposit_amount: Decimal
    features: list[str]
    status: UnitStatus
    vacancy_date: date | None
    expected_vacancy_date: date | None
    is_archived: bool
    created_at: datetime


class UnitDetail(UnitRead):
    property_name: str | None = None
    photos: list[PhotoRead] = []
    current_tenant_name: str | None = None
    current_tenancy_id: uuid.UUID | None = None


class BulkCreateResult(BaseModel):
    created: int
    units: list[UnitRead]


# --------------------------------------------------------------------- dashboard


class PortfolioStats(BaseModel):
    total_properties: int
    total_units: int
    occupied_units: int
    vacant_units: int
    maintenance_units: int
    reserved_units: int
    vacating_units: int
    occupancy_rate: float
    monthly_rent_potential: Decimal
    monthly_rent_contracted: Decimal


class PortfolioDashboard(BaseModel):
    stats: PortfolioStats
    properties: list[PropertySummary]
