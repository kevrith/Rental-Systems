"""Arrears and aging analysis (US-022).

Aging is bucketed by how long each *invoice* has been overdue, not by the
tenant's total, so a tenant who is up to date on this month but owes from three
months ago lands in the 90+ bucket where they belong.
"""

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext, accessible_property_ids
from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentStatus
from app.models.property import Property, Unit
from app.models.tenant import Tenancy, Tenant

ZERO = Decimal("0.00")

BUCKETS: list[tuple[str, int, int | None]] = [
    ("current", -10_000, 0),
    ("days_1_30", 1, 30),
    ("days_31_60", 31, 60),
    ("days_61_90", 61, 90),
    ("days_90_plus", 91, None),
]


def bucket_for(days_overdue: int) -> str:
    for name, low, high in BUCKETS:
        if days_overdue >= low and (high is None or days_overdue <= high):
            return name
    return "current"


@dataclass
class ArrearsRow:
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_phone: str
    tenancy_id: uuid.UUID
    tenancy_reference: str
    unit_number: str
    property_id: uuid.UUID
    property_name: str
    amount_owed: Decimal = ZERO
    days_overdue: int = 0
    oldest_due_date: date | None = None
    last_payment_date: date | None = None
    invoice_count: int = 0
    aging: dict[str, Decimal] = field(default_factory=lambda: {name: ZERO for name, _, _ in BUCKETS})

    @property
    def bucket(self) -> str:
        return bucket_for(self.days_overdue)


@dataclass
class ArrearsSummary:
    total_arrears: Decimal
    tenants_in_arrears: int
    aging: dict[str, Decimal]
    rows: list[ArrearsRow]


async def build_report(
    db: AsyncSession,
    context: OrgContext,
    *,
    property_id: uuid.UUID | None = None,
    as_of: date | None = None,
    min_amount: Decimal = ZERO,
) -> ArrearsSummary:
    as_of = as_of or date.today()

    query = (
        select(Invoice, Tenancy, Tenant, Unit, Property)
        .join(Tenancy, Tenancy.id == Invoice.tenancy_id)
        .join(Tenant, Tenant.id == Tenancy.tenant_id)
        .join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .where(
            Invoice.organization_id == context.organization_id,
            Invoice.status.notin_([InvoiceStatus.PAID, InvoiceStatus.CANCELLED]),
            Invoice.total > Invoice.amount_paid,
        )
    )

    allowed = await accessible_property_ids(db, context)
    if allowed is not None:
        query = query.where(Unit.property_id.in_(allowed))
    if property_id:
        query = query.where(Unit.property_id == property_id)

    rows_by_tenancy: dict[uuid.UUID, ArrearsRow] = {}
    aging_totals = {name: ZERO for name, _, _ in BUCKETS}
    total = ZERO

    for invoice, tenancy, tenant, unit, property_record in (await db.execute(query)).all():
        owed = Decimal(invoice.total) - Decimal(invoice.amount_paid)
        if owed <= 0:
            continue

        row = rows_by_tenancy.get(tenancy.id)
        if row is None:
            row = ArrearsRow(
                tenant_id=tenant.id,
                tenant_name=tenant.full_name,
                tenant_phone=tenant.phone_number,
                tenancy_id=tenancy.id,
                tenancy_reference=tenancy.reference_code,
                unit_number=unit.unit_number,
                property_id=property_record.id,
                property_name=property_record.name,
            )
            rows_by_tenancy[tenancy.id] = row

        days_overdue = (as_of - invoice.due_date).days
        bucket = bucket_for(days_overdue)

        row.amount_owed += owed
        row.invoice_count += 1
        row.aging[bucket] += owed
        row.days_overdue = max(row.days_overdue, days_overdue)
        if row.oldest_due_date is None or invoice.due_date < row.oldest_due_date:
            row.oldest_due_date = invoice.due_date

        aging_totals[bucket] += owed
        total += owed

    kept = [row for row in rows_by_tenancy.values() if row.amount_owed >= min_amount]

    for row in kept:
        row.last_payment_date = await db.scalar(
            select(Payment.payment_date)
            .where(Payment.tenancy_id == row.tenancy_id, Payment.status == PaymentStatus.CONFIRMED)
            .order_by(Payment.payment_date.desc())
            .limit(1)
        )

    kept.sort(key=lambda r: r.amount_owed, reverse=True)
    return ArrearsSummary(
        total_arrears=total,
        tenants_in_arrears=len(kept),
        aging=aging_totals,
        rows=kept,
    )


def to_csv(summary: ArrearsSummary) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Tenant",
            "Phone",
            "Property",
            "Unit",
            "Tenancy",
            "Amount owed (KES)",
            "Days overdue",
            "Oldest due date",
            "Last payment",
            "Current",
            "1-30",
            "31-60",
            "61-90",
            "90+",
        ]
    )
    for row in summary.rows:
        writer.writerow(
            [
                row.tenant_name,
                row.tenant_phone,
                row.property_name,
                row.unit_number,
                row.tenancy_reference,
                f"{row.amount_owed:.2f}",
                row.days_overdue,
                row.oldest_due_date.isoformat() if row.oldest_due_date else "",
                row.last_payment_date.isoformat() if row.last_payment_date else "",
                f"{row.aging['current']:.2f}",
                f"{row.aging['days_1_30']:.2f}",
                f"{row.aging['days_31_60']:.2f}",
                f"{row.aging['days_61_90']:.2f}",
                f"{row.aging['days_90_plus']:.2f}",
            ]
        )
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", "", "", f"{summary.total_arrears:.2f}"])
    return buffer.getvalue()
