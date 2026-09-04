"""KRA eTIMS API — Phase 2 (US-053).

Credential management, the submission report, and a manual retry for anything
the background task gave up on.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.etims import EtimsSubmission
from app.services import etims_service

router = APIRouter()


class CredentialUpsert(BaseModel):
    kra_pin: str = Field(min_length=9, max_length=32)
    device_serial: str = Field(min_length=3, max_length=128)
    api_key: str = Field(min_length=3, max_length=256)
    branch_id: str = Field(default="00", max_length=16)
    environment: str = Field(default="sandbox", pattern="^(sandbox|production)$")


@router.get("/credentials")
async def read_credentials(
    context: OrgContext = Depends(require(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Whether eTIMS is configured, and a masked hint — never the secrets."""
    record = await etims_service.get_credential(db, context.organization_id)
    return etims_service.describe_credential(record)


@router.put("/credentials")
async def save_credentials(
    body: CredentialUpsert,
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    record = await etims_service.save_credential(
        db,
        context.organization_id,
        kra_pin=body.kra_pin,
        device_serial=body.device_serial,
        api_key=body.api_key,
        branch_id=body.branch_id,
        environment=body.environment,
    )
    return etims_service.describe_credential(record)


@router.delete("/credentials")
async def delete_credentials(
    context: OrgContext = Depends(require_write(Permission.ORG_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Stop filing. Receipts already declared keep their stamp."""
    removed = await etims_service.delete_credential(db, context.organization_id)
    return {"removed": removed}


@router.get("/report")
async def submission_report(
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    context: OrgContext = Depends(require(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Submitted, failed and outstanding counts, plus the recent failures."""
    return await etims_service.report(db, context.organization_id, period_start, period_end)


@router.post("/submissions/{submission_id}/retry")
async def retry_submission(
    submission_id: uuid.UUID,
    context: OrgContext = Depends(require_write(Permission.FINANCIALS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    """Try a submission again by hand — including one the retries gave up on."""
    submission = await db.get(EtimsSubmission, submission_id)
    if submission is None or submission.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    # A manual retry resets the attempt budget; a person has decided to try again.
    submission.attempts = 0
    result = await etims_service.submit(db, submission)
    return {
        "id": str(result.id),
        "status": result.status.value,
        "attempts": result.attempts,
        "invoice_number": result.invoice_number,
        "last_error": result.last_error,
    }
