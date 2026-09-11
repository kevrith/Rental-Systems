"""Digital signature API endpoints — Phase 2 (US-044)."""

import uuid

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.services import signature_service

router = APIRouter()
public_router = APIRouter()


class SigningRequestCreate(BaseModel):
    document_id: uuid.UUID
    tenancy_id: uuid.UUID | None = None
    signer_name: str
    signer_phone: str
    signer_role: str = "tenant"


class SignatureSubmit(BaseModel):
    otp_code: str
    signature_image: str  # base64 data URL


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_signing_request(
    body: SigningRequestCreate,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    sig, _ = await signature_service.create_signing_request(
        db,
        organization_id=context.organization_id,
        document_id=body.document_id,
        tenancy_id=body.tenancy_id,
        signer_name=body.signer_name,
        signer_phone=body.signer_phone,
        signer_role=body.signer_role,
    )
    return sig


# Public endpoints — no auth, accessed via signing link


@public_router.get("/{token}")
async def get_signing_request(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Return signing request details for the public signing page.

    When the signer is a known tenant, their saved signature is included so
    the signing page can pre-fill the pad rather than requiring a fresh drawing.
    """
    sig = await signature_service.get_by_token(db, token)

    # Attempt to look up a saved signature for this signer so the signing UI
    # can pre-fill it. We check the tenant table first (most common), then the
    # user table. The caller never learns whether or not a match was found —
    # the saved_signature field simply stays null when there is no match.
    from sqlalchemy import select

    from app.models.tenant import Tenant
    from app.models.user import User

    saved_signature: str | None = None
    if sig.tenancy_id:
        from app.models.tenant import Tenancy

        tenancy = await db.get(Tenancy, sig.tenancy_id)
        if tenancy:
            tenant = await db.get(Tenant, tenancy.tenant_id)
            if tenant:
                saved_signature = tenant.saved_signature

    if saved_signature is None:
        # Fall back to a user record matching by phone (owner/manager signing).
        user = await db.scalar(select(User).where(User.phone_number == sig.signer_phone))
        if user:
            saved_signature = user.saved_signature

    return {
        "id": str(sig.id),
        "signer_name": sig.signer_name,
        "signer_role": sig.signer_role,
        "document_id": str(sig.document_id),
        "expires_at": sig.expires_at.isoformat(),
        "status": sig.status.value,
        "saved_signature": saved_signature,
    }


@public_router.post("/{token}/send-otp")
async def send_signing_otp(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    sig = await signature_service.get_by_token(db, token)
    await signature_service.send_otp_for_signing(db, sig)
    return {"message": "OTP sent"}


@public_router.post("/{token}/sign")
async def sign_document(
    token: str,
    body: SignatureSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    sig = await signature_service.verify_otp_and_sign(db, token, body.otp_code, body.signature_image, request)
    return {
        "id": str(sig.id),
        "status": sig.status.value,
        "signed_at": sig.signed_at.isoformat() if sig.signed_at else None,
        "signed_document_id": str(sig.signed_document_id) if sig.signed_document_id else None,
    }
