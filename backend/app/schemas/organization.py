import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.organization import OperatingMode, SubscriptionPlan


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    operating_mode: OperatingMode
    subscription_plan: SubscriptionPlan
    trial_ends_at: datetime | None
    is_active: bool
    legal_name: str | None = None
    address: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    kra_pin: str | None = None
    logo_file_id: uuid.UUID | None = None
    default_billing_day: int = 1
    default_caretaker_cash_limit: float | None = None
    renewal_rent_increase_percent: Decimal = Decimal("0.00")
    renewal_term_months: int = 12
    auto_offer_renewals: bool = True


class OrganizationWithTrial(OrganizationRead):
    """Adds the derived trial state the dashboard banner needs (US-006)."""

    is_trial: bool
    is_trial_expired: bool
    trial_days_remaining: int | None
    is_read_only: bool


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=512)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32)
    kra_pin: str | None = Field(default=None, max_length=32)
    letterhead_note: str | None = None
    logo_file_id: uuid.UUID | None = None
    default_billing_day: int | None = Field(default=None, ge=1, le=28)
    default_caretaker_cash_limit: float | None = Field(default=None, ge=0)
    # Lease renewal defaults (US-057).
    renewal_rent_increase_percent: Decimal | None = Field(default=None, ge=0, le=100)
    renewal_term_months: int | None = Field(default=None, ge=1, le=60)
    auto_offer_renewals: bool | None = None
