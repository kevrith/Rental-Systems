import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.organization import OperatingMode, ReportDeliveryChannel, SubscriptionPlan
from app.models.user import UserRole


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
    report_delivery_channel: ReportDeliveryChannel = ReportDeliveryChannel.BOTH
    ip_whitelist: list[str] = Field(default_factory=list)
    role_session_timeouts: dict[str, int] = Field(default_factory=dict)
    fraud_max_cash_payments_per_window: int = 5
    fraud_cash_window_minutes: int = 30
    fraud_unusual_amount_multiplier: Decimal = Decimal("3.00")
    bank_name: str | None = None
    bank_account_name: str | None = None
    bank_account_number: str | None = None
    bank_branch: str | None = None
    # Sprint 26 — dual approval, session cap, suspension state, demo mode.
    cash_dual_approval_threshold: Decimal | None = None
    max_concurrent_sessions: int | None = None
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
    is_demo: bool = False
    # Sprint 26A, item 14 — scheduled Parquet drops for a warehouse/BI team.
    bi_export_enabled: bool = False


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
    # Sprint 21 (US-093) — where the automatic monthly summary is sent.
    report_delivery_channel: ReportDeliveryChannel | None = None
    # Sprint 22 (US-098) — security hardening, organisation-wide.
    ip_whitelist: list[str] | None = None
    role_session_timeouts: dict[str, int] | None = None
    fraud_max_cash_payments_per_window: int | None = Field(default=None, ge=1, le=1000)
    fraud_cash_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    fraud_unusual_amount_multiplier: Decimal | None = Field(default=None, gt=1)
    # Sprint 23 (US-101) — bank transfer instructions shown to a tenant.
    bank_name: str | None = Field(default=None, max_length=128)
    bank_account_name: str | None = Field(default=None, max_length=255)
    bank_account_number: str | None = Field(default=None, max_length=64)
    bank_branch: str | None = Field(default=None, max_length=128)
    # Sprint 26 — cash above this figure is held for a second signature. Only
    # settable through the general update route, which is ORG_MANAGE-gated, so
    # a caretaker cannot raise their own ceiling.
    cash_dual_approval_threshold: Decimal | None = Field(default=None, ge=0)
    max_concurrent_sessions: int | None = Field(default=None, ge=1, le=50)
    # Sprint 26A, item 14.
    bi_export_enabled: bool | None = None

    @field_validator("role_session_timeouts")
    @classmethod
    def _valid_roles_and_minutes(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        valid_roles = {role.value for role in UserRole}
        for role, minutes in value.items():
            if role not in valid_roles:
                raise ValueError(f"'{role}' is not a valid role")
            if not (5 <= minutes <= 1440):
                raise ValueError("Session timeout must be between 5 and 1440 minutes")
        return value

    @field_validator("ip_whitelist")
    @classmethod
    def _valid_ip_entries(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        import ipaddress

        cleaned = []
        for entry in value:
            entry = entry.strip()
            if not entry:
                continue
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"'{entry}' is not a valid IP address or CIDR range") from exc
            cleaned.append(entry)
        return cleaned
