"""Digital signature service — Phase 2 (US-044).

Generates signing links, verifies OTP, captures signatures, and overlays
them on the document PDF. Full audit trail for legal validity.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import OrgScopedMixin
from app.models.developer import WebhookEvent
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.signature import DigitalSignature, SignatureStatus
from app.models.tenant import Tenancy
from app.services import audit_service, notification_service, otp_service, webhook_service
from app.services.notifications import get_sms_notifier
from app.services.storage_service import store_bytes

SIGNING_LINK_EXPIRY_HOURS = 72
# OTP purpose namespace; the subject is the signature id, so one signer's code
# is never valid for another signing request.
SIGNING_OTP_PURPOSE = "signing"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _assert_owned(
    db: AsyncSession,
    model: type[OrgScopedMixin],
    entity_id: uuid.UUID,
    organization_id: uuid.UUID,
    label: str,
) -> None:
    """404 rather than 403 — a caller must not learn another org's ids exist."""
    record: OrgScopedMixin | None = await db.get(model, entity_id)
    if record is None or record.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")


async def create_signing_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    tenancy_id: uuid.UUID | None,
    signer_name: str,
    signer_phone: str,
    signer_role: str = "tenant",
    document_label: str = "lease agreement",
) -> tuple[DigitalSignature, str]:
    """Create a signing request and return (record, raw_token).

    The raw token is sent to the signer via WhatsApp/SMS as a link.
    Only the hash is stored — the raw token is never persisted.

    `document_label` is what the signer is told they are signing. It defaults
    to a lease because that is what this pipeline was built for, but a
    management agreement goes through the same flow and must not tell an owner
    to sign a lease (Sprint 26).
    """
    # The signing link is public and unauthenticated, so the org check has to
    # happen here: without it one organisation could raise a signing request
    # against another's lease and have a stranger sign it.
    await _assert_owned(db, StoredFile, document_id, organization_id, "Document")
    if tenancy_id is not None:
        await _assert_owned(db, Tenancy, tenancy_id, organization_id, "Tenancy")

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    sig = DigitalSignature(
        organization_id=organization_id,
        document_id=document_id,
        tenancy_id=tenancy_id,
        signer_name=signer_name,
        signer_phone=signer_phone,
        signer_role=signer_role,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=SIGNING_LINK_EXPIRY_HOURS),
        status=SignatureStatus.PENDING,
    )
    db.add(sig)
    await db.flush()

    # Send signing link via WhatsApp
    from app.core.config import settings

    signing_url = f"{settings.FRONTEND_URL}/sign/{raw_token}"
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(phone_number=signer_phone),
        notification_type=NotificationType.DOCUMENT_SIGNED,
        title=f"Please sign your {document_label}",
        body=(
            f"Dear {signer_name}, your {document_label} is ready for signing. "
            f"Please review and sign within {SIGNING_LINK_EXPIRY_HOURS} hours: {signing_url}"
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        organization_id=organization_id,
    )

    await db.commit()
    await db.refresh(sig)
    return sig, raw_token


async def get_by_token(db: AsyncSession, raw_token: str) -> DigitalSignature:
    """Look up a signing request by raw token — used on the public signing page."""
    token_hash = _hash_token(raw_token)
    sig = await db.scalar(select(DigitalSignature).where(DigitalSignature.token_hash == token_hash))
    if sig is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing link not found")
    if sig.status == SignatureStatus.EXPIRED or datetime.now(UTC) > sig.expires_at:
        sig.status = SignatureStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Signing link has expired")
    if sig.status != SignatureStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Document already {sig.status.value}"
        )
    return sig


async def send_otp_for_signing(db: AsyncSession, sig: DigitalSignature) -> None:
    """Send an OTP to the signer's phone to verify identity before signing.

    Delivered straight over SMS rather than through the notification workflow —
    a signer must not be able to opt out of the code that authenticates them.
    """
    code = await otp_service.generate_otp(SIGNING_OTP_PURPOSE, str(sig.id))
    await get_sms_notifier().send(
        sig.signer_phone,
        f"Your RentFlow signing code is {code}. It expires in 5 minutes.",
    )
    sig.otp_sent = True
    await db.commit()


async def verify_otp_and_sign(
    db: AsyncSession,
    raw_token: str,
    otp_code: str,
    signature_image: str,
    request: Request | None = None,
) -> DigitalSignature:
    """Verify OTP, capture signature, overlay on PDF, mark signed."""
    sig = await get_by_token(db, raw_token)

    # Verify OTP
    valid = await otp_service.verify_otp(SIGNING_OTP_PURPOSE, str(sig.id), otp_code)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    now = datetime.now(UTC)
    sig.otp_verified_at = now
    sig.signed_at = now
    sig.signature_image = signature_image
    sig.status = SignatureStatus.SIGNED

    # Capture audit trail
    if request:
        forwarded = request.headers.get("x-forwarded-for")
        sig.ip_address = (forwarded.split(",")[0].strip() if forwarded else None) or (
            request.client.host if request.client else None
        )
        sig.user_agent = request.headers.get("user-agent")
        geo = request.headers.get("x-geo-position", "")
        if "," in geo:
            lat, _, lng = geo.partition(",")
            sig.gps_latitude = lat.strip()
            sig.gps_longitude = lng.strip()

    # Generate signed PDF with signature overlay
    try:
        signed_doc_id = await _overlay_signature(db, sig)
        sig.signed_document_id = signed_doc_id
    except Exception:  # noqa: BLE001 — the signature is already legally captured
        # `pypdf` may be absent, or the original may not be a PDF at all. Neither
        # invalidates the signature, but a silent pass hid a real bug once, so
        # the failure is logged rather than swallowed.
        logging.getLogger("rentflow.signature").exception(
            "Signature overlay failed for %s; the signature itself stands", sig.id
        )

    audit_service.record(
        db,
        organization_id=sig.organization_id,
        action="document.signed",
        entity_type="digital_signature",
        entity_id=sig.id,
        summary=f"{sig.signer_name} ({sig.signer_role}) signed document {sig.document_id}",
    )

    # An agreement needing two signatures activates only once the second one
    # lands (Sprint 26). Tolerant of every other kind of signature — a lease
    # signature simply matches nothing and falls through.
    from app.services import management_agreement_service

    await management_agreement_service.activate_if_fully_signed(db, sig)

    # Notify all parties
    await _notify_signed(db, sig)

    await db.commit()
    await db.refresh(sig)
    await webhook_service.dispatch(
        db,
        sig.organization_id,
        WebhookEvent.LEASE_SIGNED,
        {
            "id": str(sig.id),
            "document_id": str(sig.document_id),
            "tenancy_id": str(sig.tenancy_id) if sig.tenancy_id else None,
            "signer_name": sig.signer_name,
            "signer_role": sig.signer_role,
            "signed_at": sig.signed_at.isoformat() if sig.signed_at else None,
        },
    )
    return sig


async def _overlay_signature(db: AsyncSession, sig: DigitalSignature) -> uuid.UUID:
    """Overlay the signature image on the PDF and store the signed copy."""
    from app.models.file import StoredFile
    from app.services.storage_service import get_file_bytes

    original_file = await db.get(StoredFile, sig.document_id)
    if original_file is None:
        raise ValueError("Original document not found")

    pdf_bytes = await get_file_bytes(original_file.storage_key)

    # Simple approach: append a signature page to the PDF
    # In production this would use PyMuPDF or reportlab to overlay on the last page
    signed_bytes = _append_signature_page(pdf_bytes, sig)

    file_id = await store_bytes(
        db,
        data=signed_bytes,
        filename=f"signed_{original_file.filename}",
        content_type="application/pdf",
        category=FileCategory.SIGNED_DOCUMENT,
        organization_id=sig.organization_id,
        entity_type="digital_signature",
        entity_id=sig.id,
    )
    return file_id


def _append_signature_page(pdf_bytes: bytes, sig: DigitalSignature) -> bytes:
    """Append a signature attestation page to the PDF.

    Uses reportlab to create a minimal signature page and concatenate it.
    Falls back to returning the original if reportlab is unavailable.
    """
    try:
        from io import BytesIO

        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        # Build signature page
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, 750, "Digital Signature Certificate")
        c.setFont("Helvetica", 11)
        c.drawString(72, 720, f"Signer: {sig.signer_name}")
        c.drawString(72, 700, f"Role: {sig.signer_role}")
        c.drawString(72, 680, f"Phone: {sig.signer_phone}")
        c.drawString(
            72, 660, f"Signed at: {sig.signed_at.strftime('%d %b %Y %H:%M UTC') if sig.signed_at else '—'}"
        )
        c.drawString(72, 640, f"IP Address: {sig.ip_address or '—'}")
        verified_at = sig.otp_verified_at.strftime("%d %b %Y %H:%M UTC") if sig.otp_verified_at else "—"
        c.drawString(72, 620, f"OTP Verified: {verified_at}")
        c.drawString(72, 580, "This document was signed electronically under the Kenya ICT Act.")
        c.save()
        buf.seek(0)

        writer = PdfWriter()
        for page in PdfReader(BytesIO(pdf_bytes)).pages:
            writer.add_page(page)
        for page in PdfReader(buf).pages:
            writer.add_page(page)

        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes


async def _notify_signed(db: AsyncSession, sig: DigitalSignature) -> None:
    """Notify the signer and the organization that signing is complete."""
    await notification_service.send(
        db,
        recipient=notification_service.Recipient(phone_number=sig.signer_phone),
        notification_type=NotificationType.DOCUMENT_SIGNED,
        title="Document signed successfully",
        body=(
            f"Dear {sig.signer_name}, your document has been signed successfully. "
            f"A copy will be sent to you shortly."
        ),
        channels=[NotificationChannel.WHATSAPP],
        organization_id=sig.organization_id,
    )

    # Notify owners/agency
    from sqlalchemy import select

    from app.models.user import User, UserRole

    owners = await db.scalars(
        select(User).where(
            User.organization_id == sig.organization_id,
            User.role.in_([UserRole.OWNER, UserRole.AGENCY_ADMIN]),
            User.is_active.is_(True),
        )
    )
    for owner in owners:
        await notification_service.send(
            db,
            recipient=notification_service.Recipient.for_user(owner),
            notification_type=NotificationType.DOCUMENT_SIGNED,
            title="Lease signed",
            body=f"{sig.signer_name} has signed the lease document.",
            channels=[NotificationChannel.PUSH],
            organization_id=sig.organization_id,
        )
