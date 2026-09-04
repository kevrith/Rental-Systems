"""Agency mode API endpoints — Phase 2 (US-034–US-043).

Owner profile management, disbursements, and agency dashboard.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.services import agency_service

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
