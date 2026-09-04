"""Analytics under a realistic load — Phase 2 (US-054).

The analytics screens are the ones a landlord opens first, and they aggregate
across every payment and invoice in the account. On a demo account with four
units, an accidental N+1 is invisible; on a 60-property agency it is a
twelve-second page. These tests seed a portfolio large enough for the difference
to show and assert on both round trips and wall time.

The round-trip count is the load-bearing assertion. Wall time depends on the
machine and is deliberately generous — it exists to catch an order-of-magnitude
regression, not to police milliseconds.
"""

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event

from app.models.billing import Invoice, InvoiceStatus, Payment, PaymentMethod, PaymentStatus
from app.models.organization import Organization
from app.models.property import Property, PropertyType, Unit, UnitStatus
from app.models.tenant import PaymentMethodPreference, Tenancy, TenancyStatus, Tenant
from app.services import analytics_service

# Sized so the aggregate work is real but the fixture still builds in seconds.
PROPERTIES = 30
UNITS_PER_PROPERTY = 10
MONTHS_OF_HISTORY = 6

TOTAL_UNITS = PROPERTIES * UNITS_PER_PROPERTY


class QueryCounter:
    """Counts statements issued on a connection, for N+1 assertions."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *_args, **_kwargs) -> None:
        self.count += 1


def count_queries(engine):
    counter = QueryCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    return counter


@pytest_asyncio.fixture
async def big_portfolio(db_engine):
    """A 40-property, 480-unit account with six months of billing history."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        organization = Organization(
            name=f"Perf Test Agency {uuid.uuid4().hex[:6]}",
            slug=f"perf-{uuid.uuid4().hex[:10]}",
        )
        session.add(organization)
        await session.flush()
        org_id = organization.id

        today = date.today()
        properties: list[Property] = []
        for p in range(PROPERTIES):
            record = Property(
                organization_id=org_id,
                reference_code=f"PRP-{p:04d}",
                name=f"Block {p}",
                property_type=PropertyType.RESIDENTIAL,
                address=f"{p} Perf Road, Nairobi",
                grace_period_days=5,
            )
            session.add(record)
            properties.append(record)
        await session.flush()

        units: list[Unit] = []
        for record in properties:
            for u in range(UNITS_PER_PROPERTY):
                unit = Unit(
                    organization_id=org_id,
                    property_id=record.id,
                    reference_code=f"UNT-{record.reference_code}-{u:03d}",
                    unit_number=f"{u + 1}",
                    monthly_rent=Decimal("25000.00"),
                    deposit_amount=Decimal("25000.00"),
                    # A tenth are vacant, so occupancy is not a trivial 100%.
                    status=UnitStatus.VACANT if u % 10 == 0 else UnitStatus.OCCUPIED,
                )
                session.add(unit)
                units.append(unit)
        await session.flush()

        occupied = [unit for unit in units if unit.status == UnitStatus.OCCUPIED]
        tenancies: list[Tenancy] = []
        for index, unit in enumerate(occupied):
            tenant = Tenant(
                organization_id=org_id,
                reference_code=f"TNT-{index:05d}",
                full_name=f"Tenant {index}",
                phone_number=f"+2547{index:08d}",
            )
            session.add(tenant)
            await session.flush()

            tenancy = Tenancy(
                organization_id=org_id,
                reference_code=f"TCY-{index:05d}",
                tenant_id=tenant.id,
                unit_id=unit.id,
                start_date=today - timedelta(days=400),
                is_open_ended=True,
                monthly_rent=Decimal("25000.00"),
                deposit_amount=Decimal("25000.00"),
                billing_day=1,
                payment_method=PaymentMethodPreference.MPESA,
                status=TenancyStatus.ACTIVE,
            )
            session.add(tenancy)
            tenancies.append(tenancy)
        await session.flush()

        # Six months of invoices, each mostly paid — the shape real data has.
        for month_offset in range(MONTHS_OF_HISTORY):
            total = today.year * 12 + (today.month - 1) - month_offset
            year, month = divmod(total, 12)
            period_start = date(year, month + 1, 1)

            for index, tenancy in enumerate(tenancies):
                invoice = Invoice(
                    organization_id=org_id,
                    reference_code=f"INV-{month_offset}-{index:05d}",
                    tenancy_id=tenancy.id,
                    period_start=period_start,
                    period_end=period_start + timedelta(days=27),
                    issue_date=period_start,
                    due_date=period_start + timedelta(days=5),
                    total=Decimal("25000.00"),
                    amount_paid=Decimal("25000.00"),
                    status=InvoiceStatus.PAID,
                )
                session.add(invoice)
                await session.flush()

                # One in eight goes unpaid, so collection rate is not a flat 100%.
                if index % 8 == 0:
                    invoice.amount_paid = Decimal("0.00")
                    invoice.status = InvoiceStatus.OVERDUE
                    continue

                session.add(
                    Payment(
                        organization_id=org_id,
                        reference_code=f"PMT-{month_offset}-{index:05d}",
                        tenancy_id=tenancy.id,
                        invoice_id=invoice.id,
                        amount=Decimal("25000.00"),
                        payment_date=period_start + timedelta(days=3),
                        method=PaymentMethod.MPESA,
                        status=PaymentStatus.CONFIRMED,
                        paid_at=datetime.now(UTC),
                    )
                )

        await session.commit()

    yield org_id

    async with maker() as session:
        record = await session.get(Organization, org_id)
        if record is not None:
            await session.delete(record)
            await session.commit()


@pytest.mark.asyncio
async def test_property_performance_does_not_scale_queries_with_the_portfolio(big_portfolio, db_engine):
    """The whole point: a 30-property account must not cost 120 round trips."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    counter = count_queries(db_engine)
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        started = time.perf_counter()
        rows = await analytics_service.property_performance(session, big_portfolio)
        elapsed = time.perf_counter() - started

    assert len(rows) == PROPERTIES
    assert sum(row["total_units"] for row in rows) == TOTAL_UNITS
    # Occupancy and collection are non-trivial, so the aggregation really ran.
    assert 0 < rows[0]["occupancy_rate"] < 100
    assert any(row["collected_this_month"] > 0 for row in rows)

    # Constant regardless of portfolio size: properties, units, payments,
    # invoices, maintenance — plus a little headroom for session bookkeeping.
    assert counter.count <= 12, f"{counter.count} queries for {PROPERTIES} properties"

    assert elapsed < 5.0, f"took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_revenue_analytics_is_two_queries_regardless_of_window(big_portfolio, db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    counter = count_queries(db_engine)
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        started = time.perf_counter()
        rows = await analytics_service.revenue_analytics(session, big_portfolio, months=12)
        elapsed = time.perf_counter() - started

    assert len(rows) == 12
    # The seeded history sits inside the window and is partially collected.
    recent = [row for row in rows if row["expected"] > 0]
    assert len(recent) >= MONTHS_OF_HISTORY - 1
    assert all(0 < row["collection_rate"] < 100 for row in recent)

    assert counter.count <= 6, f"{counter.count} queries for a 12-month window"
    assert elapsed < 5.0, f"took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_cash_flow_and_maintenance_analytics_stay_fast(big_portfolio, db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        started = time.perf_counter()
        forecast = await analytics_service.cash_flow_forecast(session, big_portfolio, 3)
        expiring = await analytics_service.expiring_leases_forecast(session, big_portfolio)
        maintenance = await analytics_service.maintenance_analytics(session, big_portfolio)
        elapsed = time.perf_counter() - started

    assert len(forecast) == 3
    assert forecast[0]["active_rent_roll"] > 0
    assert set(expiring) == {
        "expiring_in_30_days",
        "expiring_in_60_days",
        "expiring_in_90_days",
    }
    assert maintenance["spike_alert"] is False
    assert elapsed < 5.0, f"took {elapsed:.2f}s"
