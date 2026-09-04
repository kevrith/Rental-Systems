"""Request and response shapes for tenant screening (Sprint 14)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.application import (
    ApplicationRejectionReason,
    ApplicationStatus,
    EmploymentStatus,
    GuarantorStatus,
    ReferenceStatus,
)


class GuarantorCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    relationship_to_applicant: str = Field(min_length=2, max_length=64)
    phone_number: str = Field(min_length=10, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    national_id: str | None = Field(default=None, max_length=64)
    id_document_id: uuid.UUID | None = None
    employer_name: str | None = Field(default=None, max_length=255)
    occupation: str | None = Field(default=None, max_length=255)
    monthly_income: Decimal | None = Field(default=None, ge=0)


class ReferenceRequest(BaseModel):
    landlord_name: str = Field(min_length=2, max_length=255)
    landlord_phone: str = Field(min_length=10, max_length=32)
    property_reference: str | None = Field(default=None, max_length=255)


class ApplicationCreate(BaseModel):
    unit_id: uuid.UUID

    full_name: str = Field(min_length=2, max_length=255)
    phone_number: str = Field(min_length=10, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    national_id: str | None = Field(default=None, max_length=64)
    date_of_birth: date | None = None

    current_address: str | None = Field(default=None, max_length=512)
    current_landlord_name: str | None = Field(default=None, max_length=255)
    current_landlord_phone: str | None = Field(default=None, max_length=32)
    years_at_current_address: Decimal | None = Field(default=None, ge=0, le=99)
    reason_for_moving: str | None = Field(default=None, max_length=2000)

    employment_status: EmploymentStatus = EmploymentStatus.EMPLOYED
    employer_name: str | None = Field(default=None, max_length=255)
    employer_phone: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=255)
    monthly_income: Decimal | None = Field(default=None, ge=0)
    months_in_employment: int | None = Field(default=None, ge=0, le=840)

    occupants: int = Field(default=1, ge=1, le=30)
    intended_move_in: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    id_document_id: uuid.UUID | None = None
    passport_photo_id: uuid.UUID | None = None
    payslip_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=6)

    # Captured in the same submission rather than chased afterwards — the
    # guarantor and reference requests go out the moment the form is sent.
    guarantors: list[GuarantorCreate] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _employment_details_match_status(self) -> "ApplicationCreate":
        needs_employer = self.employment_status in (
            EmploymentStatus.EMPLOYED,
            EmploymentStatus.BUSINESS_OWNER,
        )
        if needs_employer and not (self.employer_name or "").strip():
            raise ValueError("Tell us where you work — an employer or business name is required")
        if self.employment_status != EmploymentStatus.UNEMPLOYED and self.monthly_income is None:
            raise ValueError("A monthly income is required so affordability can be assessed")
        return self


class ApplicationUpdate(BaseModel):
    """Staff corrections to a submitted application. Status is not editable here —
    every decision goes through its own endpoint."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    national_id: str | None = Field(default=None, max_length=64)
    current_address: str | None = Field(default=None, max_length=512)
    employment_status: EmploymentStatus | None = None
    employer_name: str | None = Field(default=None, max_length=255)
    employer_phone: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=255)
    monthly_income: Decimal | None = Field(default=None, ge=0)
    months_in_employment: int | None = Field(default=None, ge=0, le=840)
    occupants: int | None = Field(default=None, ge=1, le=30)
    intended_move_in: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    interview_notes: str | None = Field(default=None, max_length=2000)
    id_document_id: uuid.UUID | None = None
    passport_photo_id: uuid.UUID | None = None


class ApplicationApprove(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    # Default on: leaving the rest of the waiting list unanswered is the failure
    # mode this whole flow exists to remove.
    reject_others: bool = True


class ApplicationReject(BaseModel):
    reason: ApplicationRejectionReason
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _note_required_for_other(self) -> "ApplicationReject":
        if self.reason == ApplicationRejectionReason.OTHER and not (self.note or "").strip():
            raise ValueError("A note is required when the reason is 'other'")
        return self


class ApplicationWithdraw(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class InterviewSchedule(BaseModel):
    scheduled_for: datetime
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _in_the_future(self) -> "InterviewSchedule":
        from datetime import UTC

        when = self.scheduled_for
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        if when < datetime.now(UTC):
            raise ValueError("An interview cannot be scheduled in the past")
        return self


class GuarantorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    relationship_to_applicant: str
    phone_number: str
    email: str | None
    national_id: str | None
    employer_name: str | None
    occupation: str | None
    monthly_income: Decimal | None
    status: GuarantorStatus
    acknowledged_at: datetime | None
    declined_reason: str | None
    signature_id: uuid.UUID | None
    id_document_url: str | None = None


class ReferenceCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    landlord_name: str
    landlord_phone: str
    property_reference: str | None
    status: ReferenceStatus
    sent_at: datetime
    responded_at: datetime | None
    paid_on_time: bool | None
    would_rent_again: bool | None
    response_note: str | None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    reference_code: str
    unit_id: uuid.UUID

    full_name: str
    phone_number: str
    email: str | None
    national_id: str | None
    date_of_birth: date | None

    current_address: str | None
    current_landlord_name: str | None
    current_landlord_phone: str | None
    years_at_current_address: Decimal | None
    reason_for_moving: str | None

    employment_status: EmploymentStatus
    employer_name: str | None
    employer_phone: str | None
    job_title: str | None
    monthly_income: Decimal | None
    months_in_employment: int | None

    occupants: int
    intended_move_in: date | None
    notes: str | None

    score: int
    score_breakdown: dict[str, Any]
    status: ApplicationStatus
    reviewed_at: datetime | None
    interview_at: datetime | None
    interview_notes: str | None
    decided_at: datetime | None
    rejection_reason: ApplicationRejectionReason | None
    decision_note: str | None
    tenant_id: uuid.UUID | None
    tenancy_id: uuid.UUID | None
    submitted_online: bool
    created_at: datetime


class ApplicationDetail(ApplicationRead):
    unit_number: str | None = None
    property_name: str | None = None
    property_id: uuid.UUID | None = None
    monthly_rent: Decimal | None = None
    decided_by_name: str | None = None
    band: str = "red"
    id_document_url: str | None = None
    passport_photo_url: str | None = None
    payslip_urls: list[str] = []
    guarantors: list[GuarantorRead] = []
    references: list[ReferenceCheckRead] = []


# --- what the public pages return, which is deliberately the bare minimum ---


class PublicUnitListing(BaseModel):
    unit_id: uuid.UUID
    unit_number: str
    property_name: str
    property_address: str
    monthly_rent: Decimal
    deposit_amount: Decimal
    bedrooms: int | None = None
    unit_type: str | None = None
    description: str | None = None
    photo_urls: list[str] = []
    accepting_applications: bool = True


class GuarantorInvite(BaseModel):
    """What the guarantor sees before deciding — enough to know what they are
    agreeing to, and nothing about the applicant they should not see."""

    guarantor_name: str
    applicant_name: str
    relationship_to_applicant: str
    unit_number: str
    property_name: str
    monthly_rent: Decimal
    status: GuarantorStatus
    already_answered: bool


class GuarantorResponse(BaseModel):
    accepted: bool
    reason: str | None = Field(default=None, max_length=1000)


class ReferenceInvite(BaseModel):
    landlord_name: str
    applicant_name: str
    property_reference: str | None
    already_answered: bool


class ReferenceResponse(BaseModel):
    paid_on_time: bool
    would_rent_again: bool
    note: str | None = Field(default=None, max_length=1000)
