"""Late fee automation service — Phase 2 (US-055).

Calculates and applies late fees to overdue invoices based on per-property
configuration. Runs daily via Celery Beat.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Invoice, InvoiceLineItem, InvoiceStatus, LineItemKind
from app.models.notification import NotificationChannel, NotificationType
from app.models.property import LateFeeType, Property, Unit
from app.models.tenant import Tenancy, Tenant
from app.services import notification_service
from app.services.pdf_service import format_kes

ZERO = Decimal("0.00")


async def apply_late_fees(db: AsyncSession) -> int:
    """Apply late fees to all overdue invoices across all organizations.

    Called daily by Celery Beat. Idempotent — checks for existing late fee
    line items before adding another.
    """
    today = date.today()
    applied = 0

    # Find all overdue invoices past their grace period
    overdue_invoices = list(
        await db.scalars(
            select(Invoice).where(
                Invoice.status.in_(
                    [InvoiceStatus.PENDING, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]
                ),
                Invoice.due_date < today,
            )
        )
    )

    for invoice in overdue_invoices:
        days_overdue = (today - invoice.due_date).days
        if days_overdue <= 0:
            continue

        # Get property config via tenancy → unit → property
        tenancy = await db.get(Tenancy, invoice.tenancy_id)
        if tenancy is None:
            continue
        unit = await db.get(Unit, tenancy.unit_id)
        if unit is None:
            continue
        prop = await db.get(Property, unit.property_id)
        if prop is None:
            continue

        grace = prop.grace_period_days or 5
        if days_overdue <= grace:
            continue

        # A property with no late fee configured charges nothing — opting in is
        # per property, and this is the switch.
        if prop.late_fee_type is None or prop.late_fee_amount is None:
            continue

        # Check if late fee already applied this month
        already_applied = await db.scalar(
            select(InvoiceLineItem.id).where(
                InvoiceLineItem.invoice_id == invoice.id,
                InvoiceLineItem.kind == LineItemKind.LATE_FEE,
            )
        )
        if already_applied:
            continue

        balance = Decimal(invoice.total) - Decimal(invoice.amount_paid)
        if balance <= ZERO:
            continue

        fee = _calculate_fee(
            prop.late_fee_type,
            Decimal(prop.late_fee_amount),
            balance,
            days_overdue - grace,
            cap=Decimal(prop.late_fee_cap) if prop.late_fee_cap is not None else None,
        )
        if fee <= ZERO:
            continue

        # Add late fee line item
        line_item = InvoiceLineItem(
            invoice_id=invoice.id,
            kind=LineItemKind.LATE_FEE,
            description=f"Late fee ({days_overdue - grace} days overdue)",
            quantity=Decimal("1"),
            unit_amount=fee,
            amount=fee,
        )
        db.add(line_item)
        invoice.total = Decimal(invoice.total) + fee
        invoice.status = InvoiceStatus.OVERDUE

        # Notify tenant
        tenant = await db.get(Tenant, tenancy.tenant_id)
        if tenant:
            await notification_service.send(
                db,
                recipient=notification_service.Recipient.for_tenant(tenant),
                notification_type=NotificationType.LATE_FEE_APPLIED,
                title="Late fee applied",
                body=(
                    f"A late fee of KES {format_kes(fee)} has been added to invoice "
                    f"{invoice.reference_code}. Total outstanding: KES {format_kes(balance + fee)}."
                ),
                channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
                entity_type="invoice",
                entity_id=invoice.id,
                organization_id=invoice.organization_id,
            )

        applied += 1

    await db.commit()
    return applied


def _calculate_fee(
    fee_type: LateFeeType,
    fee_amount: Decimal,
    balance: Decimal,
    days_past_grace: int,
    *,
    cap: Decimal | None = None,
) -> Decimal:
    """The fee for one overdue invoice, never more than `cap` and never more
    than the balance itself — a late fee that exceeds the debt is indefensible."""
    if fee_type == LateFeeType.FIXED:
        fee = fee_amount
    elif fee_type == LateFeeType.PERCENT:
        fee = (balance * fee_amount / Decimal("100")).quantize(Decimal("0.01"))
    elif fee_type == LateFeeType.DAILY:
        fee = (fee_amount * max(0, days_past_grace)).quantize(Decimal("0.01"))
    else:
        return ZERO

    if cap is not None:
        fee = min(fee, cap)
    return max(ZERO, min(fee, balance))


async def waive_late_fee(
    db: AsyncSession,
    invoice_id: uuid.UUID,
    organization_id: uuid.UUID,
    reason: str,
    waived_by_id: uuid.UUID,
) -> int:
    """Remove late fee line items from an invoice and adjust the total."""
    from app.services import audit_service

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.organization_id != organization_id:
        return 0

    late_fee_items = list(
        await db.scalars(
            select(InvoiceLineItem).where(
                InvoiceLineItem.invoice_id == invoice_id,
                InvoiceLineItem.kind == LineItemKind.LATE_FEE,
            )
        )
    )
    total_waived = ZERO
    for item in late_fee_items:
        total_waived += Decimal(item.amount)
        await db.delete(item)

    if total_waived > ZERO:
        invoice.total = max(ZERO, Decimal(invoice.total) - total_waived)
        # Recalculate status
        from app.services.invoice_service import recalculate_status

        invoice.status = recalculate_status(invoice)

        from app.models.user import User

        actor = await db.get(User, waived_by_id)
        audit_service.record(
            db,
            organization_id=organization_id,
            action="late_fee.waived",
            entity_type="invoice",
            entity_id=invoice_id,
            actor=actor,
            summary=f"Late fee of KES {format_kes(total_waived)} waived. Reason: {reason}",
        )
        await db.commit()

    return len(late_fee_items)
