"""Monthly invoicing (US-021).

Invoices are generated per tenancy on its billing day. Generation is idempotent —
one invoice per tenancy per period, enforced by a unique constraint — so the
daily Celery task can run as often as it likes without duplicating charges.

Arrears are carried forward as an explicit line item rather than being folded
into rent, so a tenant reading their invoice can see exactly what is old debt.
"""

import calendar
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LineItemKind,
)
from app.models.file import FileCategory, StoredFile
from app.models.notification import NotificationChannel, NotificationType
from app.models.operations import MeterReading, MeterType
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, TenancyStatus, Tenant
from app.services import file_service, notification_service, pdf_service, reference_service

ZERO = Decimal("0.00")
BILLABLE_STATUSES = [TenancyStatus.ACTIVE, TenancyStatus.EXPIRING_SOON, TenancyStatus.NOTICE_GIVEN]


def period_bounds(billing_day: int, today: date) -> tuple[date, date]:
    """The month a bill issued on `today` covers, given the tenancy's billing day."""
    last_day = calendar.monthrange(today.year, today.month)[1]
    start = today.replace(day=min(billing_day, last_day))
    if today < start:
        # Billing day hasn't arrived yet this month — this is the previous cycle.
        previous_month = start - timedelta(days=1)
        last_of_previous = calendar.monthrange(previous_month.year, previous_month.month)[1]
        start = previous_month.replace(day=min(billing_day, last_of_previous))

    next_month_anchor = (start.replace(day=28) + timedelta(days=7)).replace(day=1)
    last_of_next = calendar.monthrange(next_month_anchor.year, next_month_anchor.month)[1]
    end = next_month_anchor.replace(day=min(billing_day, last_of_next)) - timedelta(days=1)
    return start, end


async def outstanding_balance(db: AsyncSession, tenancy_id: uuid.UUID, before: date | None = None) -> Decimal:
    query = select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)).where(
        Invoice.tenancy_id == tenancy_id,
        Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
    )
    if before:
        query = query.where(Invoice.period_start < before)
    return Decimal(await db.scalar(query) or 0)


async def _unbilled_utilities(db: AsyncSession, unit_id: uuid.UUID, up_to: date) -> list[MeterReading]:
    """Readings recorded on or before `up_to` that no invoice has charged yet.

    The cutoff is the issue date rather than the period start: a reading taken
    mid-period belongs on the next bill raised, and `billed_invoice_id` is what
    guarantees it is charged exactly once (US-026).
    """
    rows = await db.scalars(
        select(MeterReading)
        .where(
            MeterReading.unit_id == unit_id,
            MeterReading.billed_invoice_id.is_(None),
            MeterReading.reading_date <= up_to,
        )
        .order_by(MeterReading.reading_date)
    )
    return list(rows)


async def generate_invoice_for_tenancy(
    db: AsyncSession, tenancy: Tenancy, today: date | None = None, *, notify: bool = True
) -> Invoice | None:
    """Create this period's invoice, or return None if one already exists."""
    today = today or date.today()
    period_start, period_end = period_bounds(tenancy.billing_day, today)

    existing = await db.scalar(
        select(Invoice).where(Invoice.tenancy_id == tenancy.id, Invoice.period_start == period_start)
    )
    if existing:
        return None

    reference = await reference_service.generate_invoice_reference(
        db, Invoice, tenancy.organization_id, period_start
    )

    # Everything is read and assembled before the invoice is added to the session.
    # Assigning `line_items` on a pending object populates the collection outright;
    # appending to an already-flushed one would try to lazily load it first, which
    # async SQLAlchemy cannot do.
    total = ZERO
    month_label = period_start.strftime("%B %Y")
    line_items: list[InvoiceLineItem] = []

    rent = Decimal(tenancy.monthly_rent)
    line_items.append(
        InvoiceLineItem(
            kind=LineItemKind.RENT,
            description=f"Monthly rent — {month_label}",
            quantity=Decimal("1"),
            unit_amount=rent,
            amount=rent,
        )
    )
    total += rent

    billed_readings = []
    for reading in await _unbilled_utilities(db, tenancy.unit_id, today):
        billed_readings.append(reading)
        if reading.amount <= 0:
            continue
        label = "Water" if reading.meter_type == MeterType.WATER else "Electricity"
        line_items.append(
            InvoiceLineItem(
                kind=(
                    LineItemKind.WATER if reading.meter_type == MeterType.WATER else LineItemKind.ELECTRICITY
                ),
                description=(
                    f"{label} — {reading.consumption} units "
                    f"({reading.previous_reading} → {reading.current_reading})"
                ),
                quantity=Decimal(reading.consumption),
                unit_amount=Decimal(reading.rate),
                amount=Decimal(reading.amount),
            )
        )
        total += Decimal(reading.amount)

    arrears = await outstanding_balance(db, tenancy.id, before=period_start)
    if arrears > 0:
        line_items.append(
            InvoiceLineItem(
                kind=LineItemKind.ARREARS,
                description="Balance brought forward from previous invoices",
                quantity=Decimal("1"),
                unit_amount=arrears,
                amount=arrears,
            )
        )
        total += arrears

    invoice = Invoice(
        organization_id=tenancy.organization_id,
        tenancy_id=tenancy.id,
        reference_code=reference,
        period_start=period_start,
        period_end=period_end,
        issue_date=today,
        due_date=period_start,
        status=InvoiceStatus.PENDING,
        total=total,
        line_items=line_items,
    )
    db.add(invoice)
    await db.flush()

    for reading in billed_readings:
        reading.billed_invoice_id = invoice.id

    await render_invoice_pdf(db, invoice)

    if notify:
        await _notify_tenant(db, invoice, tenancy)

    return invoice


async def render_invoice_pdf(db: AsyncSession, invoice: Invoice) -> None:
    from app.models.organization import Organization

    tenancy = await db.get(Tenancy, invoice.tenancy_id)
    tenant = await db.get(Tenant, tenancy.tenant_id) if tenancy else None
    unit = await db.get(Unit, tenancy.unit_id) if tenancy else None
    property_record = await db.get(Property, unit.property_id) if unit else None
    organization = await db.get(Organization, invoice.organization_id)
    if not (tenant and unit and property_record and organization):
        return

    line_items = list(invoice.line_items)
    pdf_bytes = pdf_service.render_pdf(
        "invoice.html",
        {
            "organization": organization,
            "logo_url": None,
            "invoice": invoice,
            "line_items": line_items,
            "tenant": tenant,
            "unit": unit,
            "property": property_record,
            "balance": invoice.balance,
            "generated_at": date.today(),
        },
    )
    record = await file_service.register_generated(
        db,
        invoice.organization_id,
        data=pdf_bytes,
        filename=f"Invoice-{invoice.reference_code}.pdf",
        category=FileCategory.INVOICE,
        entity_type="tenant",
        entity_id=tenant.id,
    )
    invoice.document_id = record.id


async def _notify_tenant(db: AsyncSession, invoice: Invoice, tenancy: Tenancy) -> None:
    tenant = await db.get(Tenant, tenancy.tenant_id)
    if tenant is None:
        return

    attachment = None
    if invoice.document_id:
        record = await db.get(StoredFile, invoice.document_id)
        if record:
            attachment = notification_service.Attachment(
                url=file_service.to_url(record), filename=record.filename
            )

    await notification_service.send(
        db,
        recipient=notification_service.Recipient.for_tenant(tenant),
        notification_type=NotificationType.INVOICE_ISSUED,
        title=f"Invoice {invoice.reference_code}",
        body=(
            f"Your rent invoice for {invoice.period_start.strftime('%B %Y')} is ready. "
            f"Total due: KES {pdf_service.format_kes(invoice.total)}, "
            f"payable by {invoice.due_date.strftime('%d %b %Y')}."
        ),
        channels=[NotificationChannel.WHATSAPP, NotificationChannel.SMS],
        attachment=attachment,
        entity_type="invoice",
        entity_id=invoice.id,
        organization_id=invoice.organization_id,
    )


async def generate_due_invoices(db: AsyncSession, today: date | None = None) -> int:
    """Every tenancy whose billing day is today gets its invoice. Runs daily."""
    today = today or date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]

    # On a short month, tenancies whose billing day falls past its end bill on the
    # last day instead. `today.day == last_day` is a plain Python bool, so the
    # branch is chosen here rather than composed into the SQL.
    due_today = Tenancy.billing_day == today.day
    if today.day == last_day:
        due_today = due_today | (Tenancy.billing_day > last_day)

    rows = await db.scalars(select(Tenancy).where(Tenancy.status.in_(BILLABLE_STATUSES), due_today))

    created = 0
    for tenancy in rows:
        invoice = await generate_invoice_for_tenancy(db, tenancy, today)
        if invoice is not None:
            created += 1
    if created:
        await db.commit()
    return created


def recalculate_status(invoice: Invoice, today: date | None = None) -> InvoiceStatus:
    today = today or date.today()
    paid = Decimal(invoice.amount_paid)
    total = Decimal(invoice.total)

    if invoice.status == InvoiceStatus.CANCELLED:
        return InvoiceStatus.CANCELLED
    if paid >= total and total > 0:
        return InvoiceStatus.PAID
    if paid > 0:
        return InvoiceStatus.PARTIALLY_PAID
    if invoice.due_date < today:
        return InvoiceStatus.OVERDUE
    return InvoiceStatus.PENDING


async def open_invoices_for_tenancy(db: AsyncSession, tenancy_id: uuid.UUID) -> list[Invoice]:
    """Unpaid invoices, oldest first — payments settle the oldest debt first."""
    rows = await db.scalars(
        select(Invoice)
        .where(
            Invoice.tenancy_id == tenancy_id,
            Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
        )
        .order_by(Invoice.due_date)
    )
    return list(rows)
