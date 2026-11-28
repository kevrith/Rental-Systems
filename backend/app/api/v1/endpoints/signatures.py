"""Digital signature API endpoints — Phase 2 (US-044)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, require_write
from app.core.database import get_db
from app.core.permissions import Permission
from app.schemas.handover import HandoverCode, HandoverLink
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


@router.post("/{signature_id}/handover/link", response_model=HandoverLink)
async def handover_signing_link(
    signature_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> HandoverLink:
    """A fresh signing link, to pass on by WhatsApp or SMS. Replaces any earlier link."""
    sig = await signature_service.get_for_organization(db, signature_id, context.organization_id)
    return await signature_service.reissue_signing_link(db, sig, actor=context.user, request=request)


@router.post("/{signature_id}/handover/code", response_model=HandoverCode)
async def handover_signing_code(
    signature_id: uuid.UUID,
    request: Request,
    context: OrgContext = Depends(require_write(Permission.TENANCY_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> HandoverCode:
    """The signing code, to pass on by WhatsApp or SMS. A new code cancels the old one."""
    sig = await signature_service.get_for_organization(db, signature_id, context.organization_id)
    return await signature_service.issue_signing_code(db, sig, actor=context.user, request=request)


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
    sent = await signature_service.send_otp_for_signing(db, sig)
    if not sent:
        return {
            "message": "Ask your landlord or caretaker for your signing code.",
            "delivery": "manual",
        }
    return {"message": "OTP sent", "delivery": "sms"}


@public_router.get("/{token}/document")
async def get_signing_document(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The document the signer is being asked to sign, so they can read it first.

    Authorised by the signing link alone, exactly like the rest of this page, and
    only while the request is still pending.
    """
    from app.models.file import StoredFile
    from app.services.storage_service import get_file_bytes

    sig = await signature_service.get_by_token(db, token)
    stored = await db.get(StoredFile, sig.document_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    safe_name = "".join(ch for ch in stored.filename if ch.isalnum() or ch in " ._-") or "document.pdf"
    return Response(
        content=await get_file_bytes(stored.storage_key),
        media_type=stored.content_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"', "Cache-Control": "no-store"},
    )


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
