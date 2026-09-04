import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.vendor import VendorSpecialty


class VendorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    specialties: list[VendorSpecialty] = Field(min_length=1, max_length=12)
    phone_number: str = Field(min_length=10, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    rate_notes: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("specialties")
    @classmethod
    def _unique(cls, value: list[VendorSpecialty]) -> list[VendorSpecialty]:
        return list(dict.fromkeys(value))


class VendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    specialties: list[VendorSpecialty] | None = Field(default=None, min_length=1, max_length=12)
    phone_number: str | None = Field(default=None, min_length=10, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    rate_notes: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    company_name: str | None
    specialties: list[str]
    phone_number: str
    email: str | None
    rate_notes: str | None
    notes: str | None
    is_active: bool
    jobs_completed: int
    rating_count: int
    total_billed: Decimal
    average_rating: float | None
    average_job_cost: Decimal
    created_at: datetime


class VendorJobSummary(BaseModel):
    id: uuid.UUID
    reference_code: str
    title: str
    status: str
    completed_at: datetime | None
    cost: Decimal | None
    rating: int | None
    property_name: str | None = None
    unit_number: str | None = None


class VendorDetail(VendorRead):
    open_jobs: int = 0
    recent_jobs: list[VendorJobSummary] = []
