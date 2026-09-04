"""PostgreSQL Row Level Security — the second lock on multi-tenant isolation.

The application already scopes every query by `organization_id` (see
`app.api.deps`). RLS exists for the case where that fails: a missed `WHERE`
clause, a hand-written query, a future contributor's mistake. With RLS on, the
database itself refuses to return another tenant's rows.

The mechanism is a per-transaction setting, `app.current_org_id`, which the
policies compare against each row. `SET LOCAL` scopes it to the transaction, so
a pooled connection handed to the next request never carries the previous
tenant's identity.

Background workers and the M-Pesa callback legitimately operate across
organizations, so they run as the table owner, which bypasses RLS by default.
Only the dedicated application role is forced to obey it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Every tenant-owned table. `organizations` and `users` are keyed differently and
# are handled by their own policies below.
# Split by the migration that creates the tables: a migration can only build
# policies for tables that already exist when it runs.
PHASE_1_ORG_SCOPED_TABLES: Sequence[str] = (
    "properties",
    "units",
    "caretaker_assignments",
    "tenants",
    "tenancies",
    "lease_templates",
    "invoices",
    "payments",
    "receipts",
    "meter_readings",
    "maintenance_requests",
    "vacate_notices",
    "stored_files",
    "audit_logs",
    "notifications",
    "notification_preferences",
    "push_subscriptions",
    "user_sessions",
    "trusted_devices",
    "invitations",
)

PHASE_2_ORG_SCOPED_TABLES: Sequence[str] = (
    "owner_profiles",
    "disbursements",
    "inspection_reports",
    "digital_signatures",
)

# Added after the Phase 2 migration, so they carry their own policies.
# `task_runs` is deliberately absent: scheduled tasks sweep every organisation,
# so a run belongs to the platform and has no organization_id to scope by.
ETIMS_ORG_SCOPED_TABLES: Sequence[str] = (
    "etims_credentials",
    "etims_submissions",
    "lease_renewals",
)

# Phase 3 tables, added by the Sprint 13 migration.
PHASE_3_ORG_SCOPED_TABLES: Sequence[str] = (
    "vendors",
    "tenant_applications",
    "guarantors",
    "reference_checks",
    "service_charge_schemes",
    "service_charge_budgets",
    "service_charge_expenses",
    "sinking_fund_entries",
    "bulk_operations",
    "vacancy_listings",
    "inquiries",
    "data_exports",
    "compliance_items",
    "parking_bays",
    "parking_allocations",
    "amenities",
    "amenity_bookings",
    "utility_accounts",
    "rental_assets",
    "rental_agreements",
)

ORG_SCOPED_TABLES: Sequence[str] = (
    *PHASE_1_ORG_SCOPED_TABLES,
    *PHASE_2_ORG_SCOPED_TABLES,
    *ETIMS_ORG_SCOPED_TABLES,
    *PHASE_3_ORG_SCOPED_TABLES,
)

SETTING = "app.current_org_id"

# `current_setting(..., true)` returns NULL rather than erroring when the value
# was never set, which is what makes "no context, no rows" work.
_ORG_MATCH = "organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def enable_table_statements(tables: Sequence[str]) -> list[str]:
    """Turn on the standard `organization_id` policy for each table given.

    Separate from `enable_statements` so a later migration can cover tables that
    did not exist when the first RLS migration ran.
    """
    statements: list[str] = []
    for table in tables:
        statements.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        statements.append(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING ({_ORG_MATCH})
            WITH CHECK ({_ORG_MATCH})
            """
        )
    return statements


def disable_table_statements(tables: Sequence[str]) -> list[str]:
    statements: list[str] = []
    for table in tables:
        statements.append(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        statements.append(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    return statements


def enable_statements(tables: Sequence[str] = ORG_SCOPED_TABLES) -> list[str]:
    """The DDL that turns RLS on, as a list of statements.

    Defined here rather than inline in the migration so the Alembic upgrade and
    the test database build the exact same policies — a divergence between them
    would make the RLS tests meaningless.
    """
    statements: list[str] = [
        """
        CREATE OR REPLACE FUNCTION app_current_org_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.current_org_id', true), '')::uuid
        $$
        """
    ]

    statements.extend(enable_table_statements(tables))

    # Line items have no organization_id — they inherit isolation from their invoice.
    statements.append("ALTER TABLE invoice_line_items ENABLE ROW LEVEL SECURITY")
    statements.append(
        """
        CREATE POLICY invoice_line_items_tenant_isolation ON invoice_line_items
        USING (
            EXISTS (
                SELECT 1 FROM invoices
                WHERE invoices.id = invoice_line_items.invoice_id
                  AND invoices.organization_id = app_current_org_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM invoices
                WHERE invoices.id = invoice_line_items.invoice_id
                  AND invoices.organization_id = app_current_org_id()
            )
        )
        """
    )

    statements.append("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    statements.append(
        """
        CREATE POLICY users_tenant_isolation ON users
        USING (organization_id = app_current_org_id())
        WITH CHECK (organization_id = app_current_org_id())
        """
    )

    # Registration and the login lookup run before any org context exists, so
    # those paths depend on the table-owner bypass.
    statements.append("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    statements.append(
        """
        CREATE POLICY organizations_self_isolation ON organizations
        USING (id = app_current_org_id())
        WITH CHECK (id = app_current_org_id())
        """
    )

    return statements


def disable_statements(tables: Sequence[str] = ORG_SCOPED_TABLES) -> list[str]:
    statements = [
        "DROP POLICY IF EXISTS organizations_self_isolation ON organizations",
        "ALTER TABLE organizations DISABLE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS users_tenant_isolation ON users",
        "ALTER TABLE users DISABLE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS invoice_line_items_tenant_isolation ON invoice_line_items",
        "ALTER TABLE invoice_line_items DISABLE ROW LEVEL SECURITY",
    ]
    statements.extend(disable_table_statements(tables))
    statements.append("DROP FUNCTION IF EXISTS app_current_org_id()")
    return statements


async def set_org_context(db: AsyncSession, organization_id: uuid.UUID | None) -> None:
    """Bind this transaction to one organization.

    `set_config(..., is_local => true)` rather than `SET LOCAL` because only the
    function form accepts a bind parameter — interpolating the id into DDL-style
    SQL would be an injection surface. The `true` keeps it transaction-scoped, so
    a connection returned to the pool cannot leak tenant identity into whatever
    request borrows it next.
    """
    await db.execute(
        text("SELECT set_config(:setting, :value, true)"),
        {"setting": SETTING, "value": str(organization_id) if organization_id else ""},
    )


async def clear_org_context(db: AsyncSession) -> None:
    await db.execute(text("SELECT set_config(:setting, '', true)"), {"setting": SETTING})
