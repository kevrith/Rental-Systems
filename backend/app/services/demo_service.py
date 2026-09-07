"""Seeding an account with a believable sample portfolio (Module 24).

A landlord evaluating RentFlow on an empty account sees empty screens. The
dashboard reads zero, the arrears report is blank, the analytics charts have
no bars — none of which tells them anything about whether the product would
help. Demo mode fills the account with a small block of flats and about a
year of plausible history, so every screen has something in it on the first
click.

Two things make this safe enough to hand a real account:

**Teardown is exact.** Every row created is recorded in `DemoDataset` in
creation order, and removal walks that list in reverse. Nothing is matched by
name or by a heuristic, so demo data can never take a real row with it and a
customer who has started entering their own portfolio alongside the sample can
still remove the sample cleanly.

**The tenants are obviously not real.** Names are drawn from a fixed cast and
every phone number is in the +254700000xxx test range, which is not
allocated to a subscriber. If a notification ever escaped, it would go
nowhere. The property is named for what it is.

The history is deliberately uneven — one tenant pays on time, one pays late
every month, one has fallen two months behind, one has just moved in. A
portfolio where everyone pays perfectly makes the arrears report, the
payment-behaviour segments and the demand-letter flow all look like dead
features.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import OrgContext
from app.models.billing import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LineItemKind,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.demo import DemoDataset
from app.models.operations import (
    MaintenanceCategory,
    MaintenancePriority,
    MaintenanceRequest,
    MaintenanceStatus,
    MeterReading,
    MeterType,
)
from app.models.organization import Organization
from app.models.property import Property, PropertyType, Unit, UnitStatus
from app.models.tenant import PaymentMethodPreference, Tenancy, TenancyStatus, Tenant
from app.services import audit_service, reference_service

ZERO = Decimal("0.00")
RECIPE = "starter_portfolio"

# Reserved test range — never allocated to a real Safaricom subscriber, so a
# notification that somehow escaped the demo would reach nobody.
DEMO_PHONE_PREFIX = "+25470000"

# How each sample tenant behaves, which is what makes the reports interesting.
# `paid_months` counts back from the current month: 0 is this month.
PROMPT = "prompt"
LATE = "late"
ARREARS = "arrears"
NEW = "new"

CAST: tuple[dict, ...] = (
    {
        "name": "Amina Otieno",
        "unit": "A1",
        "bedrooms": 2,
        "rent": Decimal("35000.00"),
        "behaviour": PROMPT,
        "months": 10,
    },
    {
        "name": "Brian Kiptoo",
        "unit": "A2",
        "bedrooms": 2,
        "rent": Decimal("35000.00"),
        "behaviour": LATE,
        "months": 10,
    },
    {
        "name": "Grace Mwangi",
        "unit": "B1",
        "bedrooms": 1,
        "rent": Decimal("22000.00"),
        "behaviour": ARREARS,
        "months": 8,
    },
    {
        "name": "Samuel Njoroge",
        "unit": "B2",
        "bedrooms": 1,
        "rent": Decimal("22000.00"),
        "behaviour": NEW,
        "months": 1,
    },
)

# Left vacant on purpose, so occupancy is not 100% and the vacancy screens have
# something to show.
VACANT_UNITS: tuple[tuple[str, int, Decimal], ...] = (
    ("B3", 1, Decimal("22000.00")),
    ("C1", 3, Decimal("48000.00")),
)

# Table name -> model, for teardown. Only what the seeder creates.
# `Any` because every value is both `UUIDPrimaryKeyMixin` and
# `OrgScopedMixin`, and Python has no way to name that intersection.
_MODELS: dict[str, Any] = {
    "payments": Payment,
    "invoices": Invoice,
    "meter_readings": MeterReading,
    "maintenance_requests": MaintenanceRequest,
    "tenancies": Tenancy,
    "tenants": Tenant,
    "units": Unit,
    "properties": Property,
}


class _Ledger:
    """Records what was created, in order, so it can be undone exactly."""

    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, table: str, row_id: uuid.UUID) -> None:
        self.rows.append({"table": table, "id": str(row_id)})


def _month_start(anchor: date, months_back: int) -> date:
    total = anchor.year * 12 + (anchor.month - 1) - months_back
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


async def current(db: AsyncSession, organization_id: uuid.UUID) -> DemoDataset | None:
    """The live sample dataset for this organisation, if one is loaded."""
    return await db.scalar(
        select(DemoDataset)
        .where(DemoDataset.organization_id == organization_id, DemoDataset.removed_at.is_(None))
        .order_by(DemoDataset.created_at.desc())
        .limit(1)
    )


async def seed(db: AsyncSession, context: OrgContext) -> DemoDataset:
    """Create the sample portfolio. Refuses if one is already loaded."""
    existing = await current(db, context.organization_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sample data is already loaded. Remove it before loading it again.",
        )

    today = date.today()
    ledger = _Ledger()

    property_record = Property(
        organization_id=context.organization_id,
        reference_code=await reference_service.generate_reference(
            db, Property, context.organization_id, "PRP"
        ),
        name="Sample Court (demo data)",
        property_type=PropertyType.RESIDENTIAL,
        address="Kiambu Road, Runda",
        county="Nairobi",
        water_rate_per_unit=Decimal("150.00"),
        electricity_rate_per_unit=Decimal("25.00"),
        description="Example data loaded from RentFlow. Safe to delete at any time.",
    )
    db.add(property_record)
    await db.flush()
    ledger.add("properties", property_record.id)

    for index, member in enumerate(CAST):
        unit = await _make_unit(
            db,
            context,
            ledger,
            property_record.id,
            member["unit"],
            member["bedrooms"],
            member["rent"],
            UnitStatus.OCCUPIED,
        )
        tenant = Tenant(
            organization_id=context.organization_id,
            reference_code=await reference_service.generate_reference(
                db, Tenant, context.organization_id, "TNT"
            ),
            full_name=member["name"],
            phone_number=f"{DEMO_PHONE_PREFIX}{index + 1:03d}",
            email=None,
            notes="Sample data loaded from RentFlow.",
        )
        db.add(tenant)
        await db.flush()
        ledger.add("tenants", tenant.id)

        start = _month_start(today, member["months"])
        tenancy = Tenancy(
            organization_id=context.organization_id,
            reference_code=await reference_service.generate_reference(
                db, Tenancy, context.organization_id, "TCY"
            ),
            tenant_id=tenant.id,
            unit_id=unit.id,
            start_date=start,
            end_date=None,
            is_open_ended=True,
            monthly_rent=member["rent"],
            deposit_amount=member["rent"],
            billing_day=1,
            payment_method=PaymentMethodPreference.MPESA,
            status=TenancyStatus.ACTIVE,
        )
        db.add(tenancy)
        await db.flush()
        ledger.add("tenancies", tenancy.id)

        await _make_history(db, context, ledger, tenancy, member["behaviour"], member["months"], today)
        await _make_readings(db, context, ledger, unit.id, today)

    for unit_number, bedrooms, rent in VACANT_UNITS:
        await _make_unit(
            db, context, ledger, property_record.id, unit_number, bedrooms, rent, UnitStatus.VACANT
        )

    await _make_maintenance(db, context, ledger, property_record.id, ledger.rows, today)

    dataset = DemoDataset(
        organization_id=context.organization_id,
        created_rows=ledger.rows,
        row_count=len(ledger.rows),
        recipe=RECIPE,
        seeded_by_id=context.user.id,
    )
    db.add(dataset)

    organization = await db.get(Organization, context.organization_id)
    if organization is not None:
        organization.is_demo = True

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="demo_data.seeded",
        entity_type="organization",
        entity_id=context.organization_id,
        actor=context.user,
        summary=f"Loaded the sample portfolio ({len(ledger.rows)} records)",
    )
    await db.commit()
    await db.refresh(dataset)
    return dataset


async def _make_unit(
    db: AsyncSession,
    context: OrgContext,
    ledger: _Ledger,
    property_id: uuid.UUID,
    unit_number: str,
    bedrooms: int,
    rent: Decimal,
    unit_status: UnitStatus,
) -> Unit:
    unit = Unit(
        organization_id=context.organization_id,
        property_id=property_id,
        reference_code=await reference_service.generate_reference(db, Unit, context.organization_id, "UNT"),
        unit_number=unit_number,
        unit_type=f"{bedrooms} bedroom",
        bedrooms=bedrooms,
        bathrooms=1,
        monthly_rent=rent,
        deposit_amount=rent,
        status=unit_status,
    )
    db.add(unit)
    await db.flush()
    ledger.add("units", unit.id)
    return unit


async def _make_history(
    db: AsyncSession,
    context: OrgContext,
    ledger: _Ledger,
    tenancy: Tenancy,
    behaviour: str,
    months: int,
    today: date,
) -> None:
    """One invoice per month, and payments that match the tenant's habits."""
    rent = Decimal(tenancy.monthly_rent)
    # How many of the most recent months go unpaid, per behaviour.
    unpaid_recent = {PROMPT: 0, LATE: 0, ARREARS: 2, NEW: 0}[behaviour]

    for offset in range(months, -1, -1):
        period_start = _month_start(today, offset)
        if period_start < tenancy.start_date.replace(day=1):
            continue
        period_end = _month_start(today, offset - 1) - timedelta(days=1) if offset > 0 else today
        due = period_start

        invoice = Invoice(
            organization_id=context.organization_id,
            tenancy_id=tenancy.id,
            reference_code=await reference_service.generate_invoice_reference(
                db, Invoice, context.organization_id, period_start
            ),
            period_start=period_start,
            period_end=period_end,
            issue_date=period_start,
            due_date=due,
            status=InvoiceStatus.PENDING,
            total=rent,
            line_items=[
                InvoiceLineItem(
                    kind=LineItemKind.RENT,
                    description=f"Rent for {period_start.strftime('%B %Y')}",
                    quantity=Decimal("1"),
                    unit_amount=rent,
                    amount=rent,
                )
            ],
        )
        db.add(invoice)
        await db.flush()
        ledger.add("invoices", invoice.id)

        if offset < unpaid_recent:
            invoice.status = InvoiceStatus.OVERDUE
            continue

        # A late payer pays around the 18th; a prompt one on the due date.
        paid_on = due + timedelta(days=17 if behaviour == LATE else 0)
        if paid_on > today:
            invoice.status = InvoiceStatus.PENDING
            continue

        payment = Payment(
            organization_id=context.organization_id,
            reference_code=await reference_service.generate_reference(
                db, Payment, context.organization_id, "PMT"
            ),
            tenancy_id=tenancy.id,
            invoice_id=invoice.id,
            amount=rent,
            method=PaymentMethod.MPESA,
            status=PaymentStatus.CONFIRMED,
            payment_date=paid_on,
            paid_at=datetime.combine(paid_on, datetime.min.time(), tzinfo=UTC),
            notes="Sample data loaded from RentFlow.",
        )
        db.add(payment)
        await db.flush()
        ledger.add("payments", payment.id)

        invoice.amount_paid = rent
        invoice.status = InvoiceStatus.PAID


async def _make_readings(
    db: AsyncSession,
    context: OrgContext,
    ledger: _Ledger,
    unit_id: uuid.UUID,
    today: date,
) -> None:
    """Three months of water readings, so the utility analytics have a trend."""
    previous = Decimal("1200.00")
    rate = Decimal("150.00")
    for offset in (2, 1, 0):
        reading_date = _month_start(today, offset)
        if reading_date > today:
            continue
        consumption = Decimal("7.00") + Decimal(offset)
        current_reading = previous + consumption
        reading = MeterReading(
            organization_id=context.organization_id,
            unit_id=unit_id,
            meter_type=MeterType.WATER,
            previous_reading=previous,
            current_reading=current_reading,
            consumption=consumption,
            rate=rate,
            amount=(consumption * rate).quantize(Decimal("0.01")),
            reading_date=reading_date,
            notes="Sample data loaded from RentFlow.",
        )
        db.add(reading)
        await db.flush()
        ledger.add("meter_readings", reading.id)
        previous = current_reading


async def _make_maintenance(
    db: AsyncSession,
    context: OrgContext,
    ledger: _Ledger,
    property_id: uuid.UUID,
    rows: list[dict[str, str]],
    today: date,
) -> None:
    """Two jobs: one open, one finished with a cost, so the reports have both."""
    unit_ids = [uuid.UUID(row["id"]) for row in rows if row["table"] == "units"]
    if not unit_ids:
        return

    open_job = MaintenanceRequest(
        organization_id=context.organization_id,
        reference_code=await reference_service.generate_reference(
            db, MaintenanceRequest, context.organization_id, "MNT"
        ),
        unit_id=unit_ids[0],
        title="Kitchen tap dripping",
        description="Sample data loaded from RentFlow. The cold tap drips overnight.",
        category=MaintenanceCategory.PLUMBING,
        priority=MaintenancePriority.ROUTINE,
        status=MaintenanceStatus.SUBMITTED,
    )
    db.add(open_job)
    await db.flush()
    ledger.add("maintenance_requests", open_job.id)

    done_job = MaintenanceRequest(
        organization_id=context.organization_id,
        reference_code=await reference_service.generate_reference(
            db, MaintenanceRequest, context.organization_id, "MNT"
        ),
        unit_id=unit_ids[min(1, len(unit_ids) - 1)],
        title="Replaced corridor light fitting",
        description="Sample data loaded from RentFlow.",
        category=MaintenanceCategory.ELECTRICAL,
        priority=MaintenancePriority.ROUTINE,
        status=MaintenanceStatus.COMPLETED,
        cost=Decimal("3500.00"),
        estimated_cost=Decimal("3000.00"),
        completed_at=datetime.combine(today - timedelta(days=9), datetime.min.time(), tzinfo=UTC),
    )
    db.add(done_job)
    await db.flush()
    ledger.add("maintenance_requests", done_job.id)


async def remove(db: AsyncSession, context: OrgContext) -> int:
    """Delete exactly what was seeded, newest row first. Returns how many.

    Reverse creation order means a child is always gone before its parent, so
    no foreign key ever blocks the delete and no cascade has to be relied on to
    reach something the ledger did not list.
    """
    dataset = await current(db, context.organization_id)
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This account has no sample data loaded"
        )

    removed = 0
    for row in reversed(dataset.created_rows):
        model = _MODELS.get(str(row.get("table")))
        if model is None:
            continue
        result = await db.execute(
            delete(model).where(
                model.id == uuid.UUID(str(row["id"])),
                # Belt and braces: the ledger is already organisation-scoped,
                # but a delete by bare id is not something to leave unbounded.
                model.organization_id == context.organization_id,
            )
        )
        removed += result.rowcount or 0

    dataset.removed_at = datetime.now(UTC)

    organization = await db.get(Organization, context.organization_id)
    if organization is not None:
        organization.is_demo = False

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="demo_data.removed",
        entity_type="organization",
        entity_id=context.organization_id,
        actor=context.user,
        summary=f"Removed the sample portfolio ({removed} records)",
    )
    await db.commit()
    return removed
