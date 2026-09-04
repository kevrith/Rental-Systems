"""API response-time audit — Phase 2 (US-059).

The acceptance criterion is "all endpoints under 500ms". A wall-clock number is
machine-dependent, so this measures two things instead:

  * **round trips** — the count of SQL statements one request issues. This is
    machine-independent and is what actually determines whether an endpoint stays
    under 500ms once the database is on another host. An N+1 shows up here long
    before it shows up on a stopwatch.
  * **wall time** — kept as a coarse backstop against something pathological,
    with a generous ceiling.

The account is seeded to a realistic size first: an endpoint that is fast on an
empty account tells you nothing.
"""

import time
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import event

# Real-world shape for a small agency: enough rows that an N+1 is visible.
PROPERTIES = 6
UNITS_PER_PROPERTY = 5

# A single request should not need more statements than this. Chosen well above
# the current counts so ordinary work does not trip it, and far below what an
# N+1 over 30 units would produce.
MAX_QUERIES_PER_REQUEST = 60
MAX_SECONDS_PER_REQUEST = 3.0


class QueryCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *_args, **_kwargs) -> None:
        self.count += 1


@pytest.fixture
def query_counter(db_engine):
    counter = QueryCounter()
    event.listen(db_engine.sync_engine, "before_cursor_execute", counter)
    yield counter
    event.remove(db_engine.sync_engine, "before_cursor_execute", counter)


async def _seeded_account(client: AsyncClient) -> dict:
    """An owner account with several properties, units, tenants and payments."""
    suffix = uuid.uuid4().hex[:8]
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Perf Owner",
            "organization_name": f"Perf Org {suffix}",
            "email": f"perf-{suffix}@test.com",
            "phone_number": f"+2547{abs(hash(suffix)) % 100000000:08d}",
            "password": "TestPass123!",
            "account_type": "owner",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['tokens']['access_token']}"}

    today = date.today()
    for p in range(PROPERTIES):
        prop = await client.post(
            "/api/v1/properties",
            headers=headers,
            json={
                "name": f"Block {p}",
                "address": f"{p} Perf Road",
                "property_type": "residential",
                "water_rate_per_unit": "150.00",
            },
        )
        property_id = prop.json()["id"]

        for u in range(UNITS_PER_PROPERTY):
            unit = await client.post(
                "/api/v1/units",
                headers=headers,
                json={
                    "property_id": property_id,
                    "unit_number": f"{p}-{u}",
                    "monthly_rent": "25000.00",
                    "deposit_amount": "25000.00",
                },
            )
            tenant = await client.post(
                "/api/v1/tenants",
                headers=headers,
                json={
                    "full_name": f"Tenant {p}-{u}",
                    "phone_number": f"+2547{abs(hash(f'{suffix}{p}{u}')) % 100000000:08d}",
                    "email": f"t-{uuid.uuid4().hex[:10]}@example.com",
                },
            )
            tenancy = await client.post(
                "/api/v1/tenancies",
                headers=headers,
                json={
                    "tenant_id": tenant.json()["id"],
                    "unit_id": unit.json()["id"],
                    "start_date": (today - timedelta(days=90)).isoformat(),
                    "monthly_rent": "25000.00",
                    "deposit_amount": "25000.00",
                    "billing_day": 1,
                    "payment_method": "mpesa",
                    "is_open_ended": True,
                },
            )
            assert tenancy.status_code == 201, tenancy.text

            # Most units have paid; a few have not, so arrears is non-empty.
            if u % 4 != 0:
                await client.post(
                    "/api/v1/payments",
                    headers=headers,
                    json={
                        "tenancy_id": tenancy.json()["id"],
                        "amount": "25000.00",
                        "payment_date": today.isoformat(),
                        "method": "cash",
                    },
                )

    return {"headers": headers}


# Every read endpoint a person hits on a normal day, with the params it needs.
AUDITED_ENDPOINTS: list[tuple[str, dict | None]] = [
    ("/api/v1/dashboard/portfolio", None),
    ("/api/v1/dashboard/financial", None),
    ("/api/v1/properties", None),
    ("/api/v1/units", None),
    ("/api/v1/tenants", None),
    ("/api/v1/tenancies", None),
    ("/api/v1/payments", None),
    ("/api/v1/invoices", None),
    ("/api/v1/arrears", None),
    ("/api/v1/analytics/revenue", {"months": 12}),
    ("/api/v1/analytics/property-performance", None),
    ("/api/v1/analytics/cash-flow-forecast", None),
    ("/api/v1/analytics/expiring-leases", None),
    ("/api/v1/analytics/maintenance", None),
    ("/api/v1/inspections", None),
    ("/api/v1/inspections/compliance", None),
    ("/api/v1/caretaker/performance", None),
    ("/api/v1/caretaker/today", None),
    ("/api/v1/maintenance", None),
    ("/api/v1/meter-readings", None),
    ("/api/v1/notifications", None),
    ("/api/v1/team", None),
    ("/api/v1/tasks", None),
    ("/api/v1/vault/usage", None),
    ("/api/v1/etims/report", None),
    ("/api/v1/renewals", None),
    ("/api/v1/lease-templates", None),
]


@pytest.mark.asyncio
async def test_no_read_endpoint_scales_its_queries_with_the_portfolio(client: AsyncClient, query_counter):
    """The audit: every dashboard read, on a seeded account, in one pass."""
    account = await _seeded_account(client)
    headers = account["headers"]

    report: list[tuple[str, int, float]] = []
    offenders: list[str] = []

    for path, params in AUDITED_ENDPOINTS:
        before = query_counter.count
        started = time.perf_counter()
        response = await client.get(path, headers=headers, params=params)
        elapsed = time.perf_counter() - started
        queries = query_counter.count - before

        assert response.status_code == 200, f"{path} -> {response.status_code} {response.text}"
        report.append((path, queries, elapsed))
        if queries > MAX_QUERIES_PER_REQUEST or elapsed > MAX_SECONDS_PER_REQUEST:
            offenders.append(f"{path}: {queries} queries, {elapsed * 1000:.0f}ms")

    # Printed so a regression shows what changed, not just that something did.
    print(f"\n{'endpoint':<48} {'queries':>8} {'ms':>8}")
    for path, queries, elapsed in sorted(report, key=lambda row: -row[1]):
        print(f"{path:<48} {queries:>8} {elapsed * 1000:>8.0f}")

    assert not offenders, "Endpoints over budget:\n  " + "\n  ".join(offenders)


@pytest.mark.asyncio
async def test_the_dashboard_does_not_issue_a_query_per_property(client: AsyncClient, query_counter):
    """A guard with teeth: the count must not move when the portfolio grows.

    The property-performance endpoint used to run four queries per property. This
    compares a small account against one three times the size — an N+1 shows as a
    proportional jump, whatever the absolute numbers happen to be.
    """
    small = await _seeded_account(client)

    before = query_counter.count
    await client.get("/api/v1/analytics/property-performance", headers=small["headers"])
    small_count = query_counter.count - before

    # Triple the portfolio on the same account.
    for p in range(PROPERTIES * 2):
        await client.post(
            "/api/v1/properties",
            headers=small["headers"],
            json={
                "name": f"Extra {p}",
                "address": f"{p} Extra Road",
                "property_type": "residential",
            },
        )

    before = query_counter.count
    await client.get("/api/v1/analytics/property-performance", headers=small["headers"])
    large_count = query_counter.count - before

    assert large_count <= small_count + 2, (
        f"Query count grew from {small_count} to {large_count} when the portfolio tripled — "
        f"that is an N+1."
    )
