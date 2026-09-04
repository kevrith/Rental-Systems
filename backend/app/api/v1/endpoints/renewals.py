"""Lease renewal API — Phase 2 (US-057).

Two surfaces: the management one behind auth, and the public accept/decline pair
the tenant reaches from a WhatsApp link with no account and no password.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.services import renewal_service

router = APIRouter()
public_router = APIRouter()


class OfferRenewal(BaseModel):
    """Override the organisation's defaults for one tenancy."""

    proposed_rent: Decimal | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, ge=1, le=60)


class DeclineRenewal(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


@router.get("")
async def list_renewals(
    tenancy_id: uuid.UUID | None = None,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    return await renewal_service.list_renewals(db, context, tenancy_id)


@router.post("/tenancies/{tenancy_id}")
async def offer_renewal(
    tenancy_id: uuid.UUID,
    body: OfferRenewal | None = None,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Offer a renewal now, rather than waiting for the 30-day sweep."""
    return await renewal_service.offer_for_tenancy(
        db,
        context,
        tenancy_id,
        proposed_rent=body.proposed_rent if body else None,
        term_months=body.term_months if body else None,
    )


@router.get("/tenancies/{tenancy_id}/proposed-terms")
async def proposed_terms(
    tenancy_id: uuid.UUID,
    context: OrgContext = Depends(require(Permission.TENANCY_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """What the organisation's configured uplift implies for this tenancy."""
    from app.api.deps import assert_in_org
    from app.models.tenant import Tenancy

    tenancy = assert_in_org(await db.get(Tenancy, tenancy_id), context, label="tenancy")
    terms = renewal_service.proposed_terms(tenancy, context.organization)
    return {
        "current_rent": str(terms["current_rent"]),
        "proposed_rent": str(terms["proposed_rent"]),
        "rent_increase_percent": str(terms["rent_increase_percent"]),
        "term_months": terms["term_months"],
        "new_start_date": terms["new_start_date"].isoformat(),
        "new_end_date": terms["new_end_date"].isoformat(),
    }


# --------------------------------------------------------------- public (token only)


@public_router.get("/{token}")
async def read_renewal(token: str, db: AsyncSession = Depends(get_db)):
    """What the tenant sees when they open the link. No auth — the token is it."""
    renewal = await renewal_service.get_by_token(db, token)
    return await renewal_service.describe(db, renewal)


@public_router.post("/{token}/accept")
async def accept_renewal(token: str, db: AsyncSession = Depends(get_db)):
    renewal = await renewal_service.accept(db, token)
    return {
        "status": renewal.status.value,
        "reference_code": renewal.reference_code,
        "new_end_date": renewal.new_end_date.isoformat(),
        "message": "Your renewal is confirmed. A copy has been sent to you.",
    }


@public_router.post("/{token}/decline")
async def decline_renewal(
    token: str,
    body: DeclineRenewal | None = None,
    db: AsyncSession = Depends(get_db),
):
    renewal = await renewal_service.decline(db, token, body.reason if body else None)
    return {
        "status": renewal.status.value,
        "reference_code": renewal.reference_code,
        "message": (
            "Your landlord has been told. They will be in touch about the move-out inspection "
            "and your deposit."
        ),
    }
