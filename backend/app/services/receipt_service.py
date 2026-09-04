"""Enterprise receipt generation (US-023).

Every confirmed payment gets a professional, tamper-evident PDF within seconds.
The `signature` is an HMAC over the facts that must never change — receipt code,
payment code, amount, tenancy and issue time — so a doctored PDF can be caught
by re-deriving it from the database.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import sign_payload, verify_signature
from app.models.billing import Invoice, Payment, Receipt
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.organization import Organization
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.models.user import User
from app.services import file_service, notification_service, pdf_service, reference_service


def _signature_parts(receipt_code: str, payment: Payment, issued_at: datetime) -> tuple[str, ...]:
    return (
        receipt_code,
        payment.reference_code,
        f"{Decimal(payment.amount):.2f}",
        str(payment.tenancy_id),
        issued_at.isoformat(),
    )


async def issue_receipt(db: AsyncSession, payment: Payment, balance_after: Decimal) -> Receipt:
    """Create the receipt row, render its PDF, and file it in the tenant's vault."""
    # Queried rather than read off `payment.receipt`: a lazy relationship load
    # inside async code raises MissingGreenlet.
    existing = await db.scalar(select(Receipt).where(Receipt.payment_id == payment.id))
    if existing is not None:
        return existing

    reference = await reference_service.generate_reference(db, Receipt, payment.organization_id, "RCT")
    issued_at = datetime.now(UTC)
    receipt = Receipt(
        organization_id=payment.organization_id,
        reference_code=reference,
        payment_id=payment.id,
        issued_at=issued_at,
        signature=sign_payload(*_signature_parts(reference, payment, issued_at)),
        balance_after=balance_after,
    )
    db.add(receipt)
    await db.flush()

    # File with KRA before rendering, so a receipt that succeeds first time carries
    # its eTIMS stamp. A failure only queues a retry; the tenant still gets a
    # receipt, because they have paid.
    await _declare_to_kra(db, receipt)

    record = await _render(db, receipt, payment)
    if record:
        receipt.document_id = record.id

    return receipt


async def _declare_to_kra(db: AsyncSession, receipt: Receipt) -> None:
    """eTIMS submission is best-effort and must never block a receipt (US-053)."""
    from app.services import etims_service

    try:
        await etims_service.submit_receipt_now(db, receipt)
    except Exception:  # noqa: BLE001 — the tenant's receipt does not wait on KRA
        logging.getLogger("rentflow.etims").exception(
            "eTIMS declaration failed for receipt %s", receipt.reference_code
        )


async def _render(db: AsyncSession, receipt: Receipt, payment: Payment) -> StoredFile | None:
    tenancy = await db.get(Tenancy, payment.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, payment.organization_id)
    if not (tenancy and tenant and unit and property_record and organization):
        return None

    invoice = await db.get(Invoice, payment.invoice_id) if payment.invoice_id else None
    recorded_by = await db.get(User, payment.recorded_by_id) if payment.recorded_by_id else None

    from app.services import etims_service

    etims = await etims_service.receipt_stamp(db, receipt)

    pdf_bytes = pdf_service.render_pdf(
        "receipt.html",
        {
            "organization": organization,
            "logo_url": None,
            "etims": etims,
            "receipt": receipt,
            "payment": payment,
            "invoice": invoice,
            "tenant": tenant,
            "tenancy": tenancy,
            "unit": unit,
            "property": property_record,
            "recorded_by": recorded_by.full_name if recorded_by else None,
            "issued_at": receipt.issued_at.strftime("%d %b %Y, %H:%M"),
            "generated_at": receipt.issued_at.date(),
        },
    )
    return await file_service.register_generated(
        db,
        payment.organization_id,
        data=pdf_bytes,
        filename=f"Receipt-{receipt.reference_code}.pdf",
        category=FileCategory.RECEIPT,
        entity_type="tenant",
        entity_id=tenant.id,
    )


async def deliver(db: AsyncSession, receipt: Receipt, payment: Payment) -> None:
    """Send the receipt to the tenant on WhatsApp (with PDF) and SMS."""
    tenancy = await db.get(Tenancy, payment.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    if tenant is None:
        return

    attachment = None
    if receipt.document_id:
        record = await db.get(StoredFile, receipt.document_id)
        if record:
            attachment = notification_service.Attachment(
                url=file_service.to_url(record), filename=record.filename
            )

    amount = pdf_service.format_kes(payment.amount)
    balance = pdf_service.format_kes(receipt.balance_after)
    method = payment.method.value.replace("_", " ").title()

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.RECEIPT_ISSUED,
        title=f"Receipt {receipt.reference_code}",
        body=(
            f"Payment of KES {amount} received by {method}"
            + (f" (M-Pesa ref {payment.mpesa_receipt})" if payment.mpesa_receipt else "")
            + f". Receipt {receipt.reference_code}. Outstanding balance: KES {balance}."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        attachment=attachment,
        entity_type="receipt",
        entity_id=receipt.id,
        organization_id=payment.organization_id,
    )


def is_authentic(receipt: Receipt, payment: Payment) -> bool:
    """Re-derive the signature to confirm a receipt has not been tampered with."""
    return verify_signature(
        receipt.signature, *_signature_parts(receipt.reference_code, payment, receipt.issued_at)
    )
