import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.tenant import PaymentMethodPreference, TenancyStatus


class TenantBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    phone_number: str = Field(min_length=10, max_length=32)
    email: EmailStr | None = None
    national_id: str | None = Field(default=None, max_length=64)
    employer_name: str | None = Field(default=None, max_length=255)
    occupation: str | None = Field(default=None, max_length=255)
    monthly_income: Decimal | None = Field(default=None, ge=0)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    emergency_contact_relationship: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class TenantCreate(TenantBase):
    id_photo_front_id: uuid.UUID | None = None
    id_photo_back_id: uuid.UUID | None = None
    passport_photo_id: uuid.UUID | None = None
    acknowledge_duplicate: bool = Field(
        default=False, description="Set true to save despite a duplicate phone/ID warning"
    )


class TenantUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone_number: str | None = Field(default=None, min_length=10, max_length=32)
    email: EmailStr | None = None
    national_id: str | None = Field(default=None, max_length=64)
    employer_name: str | None = Field(default=None, max_length=255)
    occupation: str | None = Field(default=None, max_length=255)
    monthly_income: Decimal | None = Field(default=None, ge=0)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    emergency_contact_relationship: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    id_photo_front_id: uuid.UUID | None = None
    id_photo_back_id: uuid.UUID | None = None
    passport_photo_id: uuid.UUID | None = None


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    full_name: str
    phone_number: str
    email: str | None
    national_id: str | None
    employer_name: str | None
    occupation: str | None
    monthly_income: Decimal | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    emergency_contact_relationship: str | None
    notes: str | None
    id_photo_front_id: uuid.UUID | None
    id_photo_back_id: uuid.UUID | None
    passport_photo_id: uuid.UUID | None
    portal_user_id: uuid.UUID | None
    is_archived: bool
    erased_at: datetime | None
    created_at: datetime


class TenantListItem(TenantRead):
    """Row shape for the tenant list — the columns the spec asks to see (US-017)."""

    unit_number: str | None = None
    property_name: str | None = None
    tenancy_id: uuid.UUID | None = None
    tenancy_status: TenancyStatus | None = None
    monthly_rent: Decimal | None = None
    lease_end_date: date | None = None
    balance: Decimal = Decimal("0.00")
    payment_status: str = "no_invoices"


class DuplicateWarning(BaseModel):
    field: str
    value: str
    existing_tenant_id: uuid.UUID
    existing_tenant_name: str


# ---------------------------------------------------------------------- tenancies


class TenancyCreate(BaseModel):
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    is_open_ended: bool = False
    monthly_rent: Decimal = Field(ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    billing_day: int = Field(default=1, ge=1, le=28)
    notice_period_days: int = Field(default=30, ge=0, le=365)
    payment_method: PaymentMethodPreference = PaymentMethodPreference.MPESA
    generate_lease: bool = True
    lease_template_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> "TenancyCreate":
        if not self.is_open_ended and self.end_date is None:
            raise ValueError("Provide an end date, or mark the tenancy open-ended")
        if self.end_date and self.end_date <= self.start_date:
            raise ValueError("End date must be after the start date")
        return self


class TenancyUpdate(BaseModel):
    end_date: date | None = None
    is_open_ended: bool | None = None
    monthly_rent: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    billing_day: int | None = Field(default=None, ge=1, le=28)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    payment_method: PaymentMethodPreference | None = None


class TenancyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    start_date: date
    end_date: date | None
    is_open_ended: bool
    monthly_rent: Decimal
    deposit_amount: Decimal
    billing_day: int
    notice_period_days: int
    payment_method: PaymentMethodPreference
    status: TenancyStatus
    notice_given_at: datetime | None
    move_out_date: date | None
    vacated_at: datetime | None
    lease_document_id: uuid.UUID | None
    created_at: datetime


class TenancyDetail(TenancyRead):
    tenant_name: str | None = None
    tenant_phone: str | None = None
    unit_number: str | None = None
    property_name: str | None = None
    property_id: uuid.UUID | None = None
    lease_url: str | None = None
    days_to_expiry: int | None = None
    balance: Decimal = Decimal("0.00")


class CoTenantAdd(BaseModel):
    tenant_id: uuid.UUID


class CoTenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenancy_id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    tenant_name: str | None = None
    tenant_phone: str | None = None


class VacateTenancyRequest(BaseModel):
    move_out_date: date
    notes: str | None = None


# ----------------------------------------------------------------- lease template


class LeaseTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    body_html: str = Field(min_length=10)
    is_default: bool = False
    logo_file_id: uuid.UUID | None = None
    letterhead_text: str | None = None


class LeaseTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    body_html: str | None = Field(default=None, min_length=10)
    is_default: bool | None = None
    logo_file_id: uuid.UUID | None = None
    letterhead_text: str | None = None


class LeaseTemplatePreview(BaseModel):
    """Preview an unsaved edit, a saved template, or a saved template with overrides."""

    body_html: str | None = None
    letterhead_text: str | None = None
    logo_file_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None


class LeaseTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    body_html: str
    is_default: bool
    version: int
    logo_file_id: uuid.UUID | None
    letterhead_text: str | None
    created_at: datetime
