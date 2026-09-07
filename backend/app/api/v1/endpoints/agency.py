"""Agency mode API endpoints — Phase 2 (US-034–US-043).

Owner profile management, disbursements, and agency dashboard.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.agency import ManagementAgreementStatus, TerminationParty
from app.services import agency_service, management_agreement_service

router = APIRouter()


# ----------------------------------------------------------------- schemas


class OwnerProfileCreate(BaseModel):
    full_name: str
    phone_number: str
    email: str | None = None
    national_id: str | None = None
    kra_pin: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_account_name: str | None = None
    mpesa_phone: str | None = None
    management_fee_percent: Decimal = Decimal("8.00")
    disbursement_day: int = Field(default=5, ge=1, le=28)
    maintenance_auto_approve_limit: Decimal = Decimal("5000.00")
    maintenance_notify_limit: Decimal = Decimal("20000.00")
    notes: str | None = None


class OwnerProfileUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    email: str | None = None
    national_id: str | None = None
    kra_pin: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_account_name: str | None = None
    mpesa_phone: str | None = None
    management_fee_percent: Decimal | None = None
    disbursement_day: int | None = Field(default=None, ge=1, le=28)
    maintenance_auto_approve_limit: Decimal | None = None
    maintenance_notify_limit: Decimal | None = None
    notes: str | None = None


class DisbursementCreate(BaseModel):
    owner_profile_id: uuid.UUID
    period_start: date
    period_end: date
    notes: str | None = None


class DisbursementMarkPaid(BaseModel):
    payment_method: str
    payment_reference: str


class DisbursementApprove(BaseModel):
    note: str | None = None


class DisbursementReject(BaseModel):
    reason: str = Field(min_length=3, max_length=512)


# ----------------------------------------------------------------- owner profiles


@router.get("/owner-profiles")
async def list_owner_profiles(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.list_owner_profiles(db, context)


@router.post("/owner-profiles", status_code=status.HTTP_201_CREATED)
async def create_owner_profile(
    body: OwnerProfileCreate,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.create_owner_profile(db, context, **body.model_dump())


@router.get("/owner-profiles/{profile_id}")
async def get_owner_profile(
    profile_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.get_owner_profile(db, context, profile_id)


@router.patch("/owner-profiles/{profile_id}")
async def update_owner_profile(
    profile_id: uuid.UUID,
    body: OwnerProfileUpdate,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return await agency_service.update_owner_profile(db, context, profile_id, updates)


@router.post("/owner-profiles/{profile_id}/invite-portal", status_code=status.HTTP_201_CREATED)
async def invite_owner_to_portal(
    profile_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.invite_owner_to_portal(db, context, profile_id)


# ----------------------------------------------------------------- disbursements


@router.get("/disbursements")
async def list_disbursements(
    owner_profile_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.list_disbursements(db, context, owner_profile_id)


@router.get("/disbursements/calculate")
async def calculate_disbursement(
    owner_profile_id: uuid.UUID,
    period_start: date,
    period_end: date,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    calc = await agency_service.calculate_disbursement(
        db, context, owner_profile_id, period_start, period_end
    )
    # Serialize — remove ORM objects
    return {
        "owner_profile_id": str(owner_profile_id),
        "owner_name": calc["owner_profile"].full_name,
        "gross_rent": float(calc["gross_rent"]),
        "management_fee": float(calc["management_fee"]),
        "maintenance_costs": float(calc["maintenance_costs"]),
        "other_deductions": float(calc["other_deductions"]),
        "net_amount": float(calc["net_amount"]),
        "payment_count": len(calc["payments"]),
    }


@router.post("/disbursements", status_code=status.HTTP_201_CREATED)
async def create_disbursement(
    body: DisbursementCreate,
    context: OrgContext = Depends(require_write(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.create_disbursement(
        db, context, body.owner_profile_id, body.period_start, body.period_end, body.notes
    )


@router.post("/disbursements/{disbursement_id}/mark-paid")
async def mark_disbursement_paid(
    disbursement_id: uuid.UUID,
    body: DisbursementMarkPaid,
    context: OrgContext = Depends(require_write(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.mark_disbursement_paid(
        db, context, disbursement_id, body.payment_method, body.payment_reference
    )


@router.post("/disbursements/{disbursement_id}/approve")
async def approve_disbursement(
    disbursement_id: uuid.UUID,
    body: DisbursementApprove | None = None,
    context: OrgContext = Depends(require_write(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Sign off on a calculated payout. Nothing can be paid until this happens."""
    return await agency_service.approve_disbursement(
        db, context, disbursement_id, body.note if body else None
    )


@router.post("/disbursements/{disbursement_id}/reject")
async def reject_disbursement(
    disbursement_id: uuid.UUID,
    body: DisbursementReject,
    context: OrgContext = Depends(require_write(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.reject_disbursement(db, context, disbursement_id, body.reason)


@router.post("/disbursements/{disbursement_id}/pay-mpesa")
async def pay_disbursement_via_mpesa(
    disbursement_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Send an approved disbursement to the owner's M-Pesa number (Daraja B2C)."""
    return await agency_service.initiate_mpesa_payout(db, context, disbursement_id)


@router.get("/disbursements/{disbursement_id}/statement")
async def disbursement_statement(
    disbursement_id: uuid.UUID,
    regenerate: bool = False,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """A signed download URL for the owner statement PDF, rendered on demand."""
    return await agency_service.statement_for_disbursement(
        db, context, disbursement_id, regenerate=regenerate
    )


# ----------------------------------------------------------------- agency dashboard


@router.get("/dashboard")
async def agency_dashboard(
    context: OrgContext = Depends(require(Permission.DASHBOARD_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await agency_service.agency_dashboard_stats(db, context)


@router.get("/owner-summaries")
async def owner_summaries(
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Per-owner summary cards: units, occupancy, collection rate, arrears, disbursement state."""
    return await agency_service.owner_summaries(db, context)


# ----------------------------------------------------------------- owner portal


@router.get("/owner-portal/summary")
async def owner_portal_summary(
    context: OrgContext = Depends(require(Permission.DASHBOARD_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Read-only summary for an owner portal user."""
    return await agency_service.owner_portal_summary(db, context.user.id, context.organization_id)


# ----------------------------------------------------- management agreements


class ManagementAgreementCreate(BaseModel):
    owner_profile_id: uuid.UUID
    start_date: date
    term_months: int = Field(default=12, ge=0, le=120)
    notice_period_days: int = Field(default=90, ge=30, le=365)
    scope_of_management: str | None = Field(default=None, max_length=5000)
    # Empty means every property currently attached to the owner profile.
    property_ids: list[uuid.UUID] = Field(default_factory=list)
    # Each omitted term is copied from the owner profile.
    management_fee_percent: Decimal | None = Field(default=None, ge=0, le=100)
    disbursement_day: int | None = Field(default=None, ge=1, le=28)
    maintenance_auto_approve_limit: Decimal | None = Field(default=None, ge=0)
    maintenance_notify_limit: Decimal | None = Field(default=None, ge=0)


class ManagementAgreementSend(BaseModel):
    """Who signs for the agency. The owner's details come from their profile."""

    agency_signatory_name: str = Field(min_length=2, max_length=255)
    agency_signatory_phone: str = Field(min_length=9, max_length=32)


class ManagementAgreementTerminate(BaseModel):
    requested_by: TerminationParty
    reason: str | None = Field(default=None, max_length=2000)
    # Defaults to the contractual notice period from today. An earlier date is
    # accepted as an agreed shortening and recorded as one.
    effective_date: date | None = None


class ManagementAgreementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference_code: str
    owner_profile_id: uuid.UUID
    status: ManagementAgreementStatus
    management_fee_percent: Decimal
    disbursement_day: int
    maintenance_auto_approve_limit: Decimal
    maintenance_notify_limit: Decimal
    scope_of_management: str | None
    property_ids: list[str]
    start_date: date
    term_months: int
    end_date: date | None
    notice_period_days: int
    document_id: uuid.UUID | None
    owner_signature_id: uuid.UUID | None
    agency_signature_id: uuid.UUID | None
    activated_at: datetime | None
    termination_requested_at: datetime | None
    termination_requested_by: TerminationParty | None
    termination_reason: str | None
    termination_effective_date: date | None
    terminated_at: datetime | None
    created_at: datetime


@router.get("/management-agreements", response_model=list[ManagementAgreementRead])
async def list_management_agreements(
    owner_profile_id: uuid.UUID | None = None,
    live_only: bool = False,
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[ManagementAgreementRead]:
    rows = await management_agreement_service.list_agreements(
        db, context, owner_profile_id=owner_profile_id, live_only=live_only
    )
    return [ManagementAgreementRead.model_validate(row) for row in rows]


@router.post(
    "/management-agreements",
    response_model=ManagementAgreementRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_management_agreement(
    body: ManagementAgreementCreate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ManagementAgreementRead:
    """Draft the contract and render its PDF. Nothing is binding until signed."""
    agreement = await management_agreement_service.create(db, context, request=request, **body.model_dump())
    return ManagementAgreementRead.model_validate(agreement)


@router.get("/management-agreements/{agreement_id}", response_model=ManagementAgreementRead)
async def get_management_agreement(
    agreement_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ManagementAgreementRead:
    agreement = await management_agreement_service.get(db, context, agreement_id)
    return ManagementAgreementRead.model_validate(agreement)


@router.post("/management-agreements/{agreement_id}/send", response_model=ManagementAgreementRead)
async def send_management_agreement(
    agreement_id: uuid.UUID,
    body: ManagementAgreementSend,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ManagementAgreementRead:
    """Send one OTP signing link to the owner and one to the agency signatory."""
    agreement = await management_agreement_service.send_for_signature(
        db,
        context,
        agreement_id,
        agency_signatory_name=body.agency_signatory_name,
        agency_signatory_phone=body.agency_signatory_phone,
        request=request,
    )
    return ManagementAgreementRead.model_validate(agreement)


@router.post("/management-agreements/{agreement_id}/terminate", response_model=ManagementAgreementRead)
async def terminate_management_agreement(
    agreement_id: uuid.UUID,
    body: ManagementAgreementTerminate,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ManagementAgreementRead:
    """Serve notice. Management continues until the effective date."""
    agreement = await management_agreement_service.request_termination(
        db,
        context,
        agreement_id,
        requested_by=body.requested_by,
        reason=body.reason,
        effective_date=body.effective_date,
        request=request,
    )
    return ManagementAgreementRead.model_validate(agreement)


@router.post(
    "/management-agreements/{agreement_id}/withdraw-termination",
    response_model=ManagementAgreementRead,
)
async def withdraw_management_agreement_termination(
    agreement_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ManagementAgreementRead:
    agreement = await management_agreement_service.withdraw_termination(
        db, context, agreement_id, request=request
    )
    return ManagementAgreementRead.model_validate(agreement)
