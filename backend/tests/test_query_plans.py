"""Query-plan guards for the hot read paths — Phase 2 (US-059).

These are not timing tests. Wall time depends on the machine; a *plan* does not.
Each test asserts that a query the dashboards run on every page load uses an
index rather than reading the table, so a future migration or query change that
reintroduces a sequential scan fails here rather than in production six months
later.

The fixture seeds several organisations on purpose. With everything under one
`organization_id`, that column matches every row, the planner correctly ignores
it, and any conclusion drawn about a multi-tenant index would be wrong.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from alembic.config import Config
from app.core.config import settings

ORGANISATIONS = 4
UNITS = 120
MONTHS = 6


def _sync_url(database: str) -> str:
    base, _, _ = settings.sync_database_url.rpartition("/")
    return f"{base}/{database}"


def _plan(conn, sql: str, params: dict) -> str:
    rows = conn.execute(text(f"EXPLAIN {sql}"), params).fetchall()
    return "\n".join(row[0] for row in rows)


@pytest.fixture(scope="module")
def planned_db():
    """A migrated scratch database with several tenants' worth of billing."""
    name = f"rentflow_plan_{uuid.uuid4().hex[:8]}"
    admin = create_engine(_sync_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')

    url = _sync_url(name)
    original = settings.DATABASE_URL_SYNC
    settings.DATABASE_URL_SYNC = url
    try:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")

        engine = create_engine(url)
        params = _seed(engine)
        yield engine, params
        engine.dispose()
    finally:
        settings.DATABASE_URL_SYNC = original
        with admin.connect() as conn:
            conn.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{name}' AND pid <> pg_backend_pid()"
            )
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
        admin.dispose()


def _seed(engine) -> dict:
    today = date.today()
    subject_org = uuid.uuid4()
    subject_user = uuid.uuid4()
    subject_tenant = uuid.uuid4()
    subject_invoice = uuid.uuid4()

    with engine.begin() as conn:
        for index in range(ORGANISATIONS):
            org_id = subject_org if index == 0 else uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, operating_mode,"
                    " subscription_plan, is_active) VALUES"
                    " (:id, 'Org', :slug, 'OWNER', 'TRIAL', true)"
                ),
                {"id": org_id, "slug": f"plan-{uuid.uuid4().hex[:10]}"},
            )
            if index == 0:
                conn.execute(
                    text(
                        "INSERT INTO users (id, organization_id, full_name, email, phone_number,"
                        " password_hash, role, is_active, is_email_verified,"
                        " is_phone_verified) VALUES"
                        " (:id, :org, 'Caretaker', :email, :phone, 'x', 'CARETAKER', true,"
                        " true, true)"
                    ),
                    {
                        "id": subject_user,
                        "org": org_id,
                        "email": f"c-{uuid.uuid4().hex[:8]}@example.com",
                        "phone": f"+2547{index:08d}0",
                    },
                )

            prop_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO properties (id, organization_id, reference_code, name,"
                    " property_type, address, amenities, grace_period_days, is_archived)"
                    " VALUES (:id, :org, :ref, 'Block', 'RESIDENTIAL', 'Nairobi', '[]'::jsonb,"
                    " 5, false)"
                ),
                {"id": prop_id, "org": org_id, "ref": f"PRP-{uuid.uuid4().hex[:8]}"},
            )

            units = [
                {
                    "id": uuid.uuid4(),
                    "org": org_id,
                    "prop": prop_id,
                    "ref": f"UNT-{uuid.uuid4().hex[:12]}",
                    "num": str(u),
                }
                for u in range(UNITS)
            ]
            conn.execute(
                text(
                    "INSERT INTO units (id, organization_id, property_id, reference_code,"
                    " unit_number, monthly_rent, deposit_amount, features, status, is_archived)"
                    " VALUES (:id, :org, :prop, :ref, :num,"
                    " 25000, 25000, '[]'::jsonb, 'OCCUPIED', false)"
                ),
                units,
            )

            tenants = [
                {
                    "id": subject_tenant if index == 0 and u == 0 else uuid.uuid4(),
                    "org": org_id,
                    "ref": f"TNT-{uuid.uuid4().hex[:12]}",
                    "phone": f"+2547{index:03d}{u:05d}",
                }
                for u in range(UNITS)
            ]
            conn.execute(
                text(
                    "INSERT INTO tenants (id, organization_id, reference_code, full_name,"
                    " phone_number, is_archived) VALUES"
                    " (:id, :org, :ref, 'Tenant', :phone, false)"
                ),
                tenants,
            )

            tenancies = [
                {
                    "id": uuid.uuid4(),
                    "org": org_id,
                    "ref": f"TCY-{uuid.uuid4().hex[:12]}",
                    "tenant": tenants[u]["id"],
                    "unit": units[u]["id"],
                    "start": today - timedelta(days=400),
                    "end": today + timedelta(days=u % 90),
                }
                for u in range(UNITS)
            ]
            conn.execute(
                text(
                    "INSERT INTO tenancies (id, organization_id, tenant_id, unit_id,"
                    " reference_code, start_date, end_date, is_open_ended, monthly_rent,"
                    " deposit_amount, billing_day, notice_period_days, payment_method, status)"
                    " VALUES (:id, :org, :tenant, :unit, :ref, :start, :end, false,"
                    " 25000, 25000, 1, 30, 'MPESA', 'ACTIVE')"
                ),
                tenancies,
            )

            invoices = []
            payments = []
            for month in range(MONTHS):
                total = today.year * 12 + (today.month - 1) - month
                year, m = divmod(total, 12)
                period = date(year, m + 1, 1)
                for u, tenancy in enumerate(tenancies):
                    invoice_id = subject_invoice if index == 0 and month == 0 and u == 0 else uuid.uuid4()
                    paid = u % 8 != 0
                    invoices.append(
                        {
                            "id": invoice_id,
                            "org": org_id,
                            "ref": f"INV-{uuid.uuid4().hex[:12]}",
                            "tenancy": tenancy["id"],
                            "ps": period,
                            "pe": period + timedelta(days=27),
                            "due": period + timedelta(days=5),
                            "paid": 25000 if paid else 0,
                            "status": "PAID" if paid else "OVERDUE",
                        }
                    )
                    if paid:
                        payments.append(
                            {
                                "id": uuid.uuid4(),
                                "org": org_id,
                                "ref": f"PMT-{uuid.uuid4().hex[:12]}",
                                "tenancy": tenancy["id"],
                                "date": period + timedelta(days=3),
                                # Only the subject organisation has a recorder, so
                                # `recorded_by_id` is genuinely selective.
                                "user": subject_user if index == 0 else None,
                            }
                        )

            conn.execute(
                text(
                    "INSERT INTO invoices (id, organization_id, tenancy_id, reference_code,"
                    " period_start, period_end, issue_date, due_date, total, amount_paid, status)"
                    " VALUES (:id, :org, :tenancy, :ref, :ps, :pe, :ps, :due, 25000,"
                    " :paid, :status)"
                ),
                invoices,
            )
            conn.execute(
                text(
                    "INSERT INTO payments (id, organization_id, tenancy_id, reference_code,"
                    " amount, method, status, payment_date, recorded_by_id) VALUES"
                    " (:id, :org, :tenancy, :ref, 25000, 'MPESA', 'CONFIRMED', :date, :user)"
                ),
                payments,
            )

            conn.execute(
                text(
                    "INSERT INTO stored_files (id, organization_id, storage_key, filename,"
                    " content_type, size_bytes, category, status, entity_type, entity_id,"
                    " version, is_archived, tags) SELECT gen_random_uuid(), :org,"
                    " 'k/' || gen_random_uuid(), 'r.pdf', 'application/pdf', 1024,"
                    " 'RECEIPT', 'UPLOADED', 'tenant', id, 1, false, '[]'::jsonb"
                    " FROM tenants WHERE organization_id = :org"
                ),
                {"org": org_id},
            )
            conn.execute(
                text(
                    "INSERT INTO notifications (id, organization_id, channel, notification_type,"
                    " recipient, title, body, status, entity_type, entity_id, payload)"
                    " SELECT gen_random_uuid(), :org, 'WHATSAPP', 'RENT_REMINDER', '+254700000000',"
                    " 't', 'b', 'SENT', 'invoice', id, jsonb_build_object('marker', 'due-7')"
                    " FROM invoices WHERE organization_id = :org"
                ),
                {"org": org_id},
            )

        conn.execute(text("ANALYZE"))

    return {
        "org": subject_org,
        "user": subject_user,
        "tenant": subject_tenant,
        "invoice": subject_invoice,
        "month": today.replace(day=1),
    }


def test_vault_reads_one_entity_with_a_single_index_scan(planned_db):
    """Two single-column indexes made Postgres bitmap-AND them on every open."""
    engine, params = planned_db
    with engine.connect() as conn:
        plan = _plan(
            conn,
            """
            SELECT id FROM stored_files
            WHERE organization_id = :org AND entity_type = 'tenant' AND entity_id = :tenant
              AND is_archived = false AND status = 'UPLOADED'
            """,
            params,
        )
    assert "Seq Scan" not in plan, plan
    assert "ix_stored_files_org_entity" in plan, plan


def test_reminder_marker_lookup_uses_an_index(planned_db):
    """Run once per invoice per night; a sequential scan here is a nightly outage."""
    engine, params = planned_db
    with engine.connect() as conn:
        plan = _plan(
            conn,
            """
            SELECT id FROM notifications
            WHERE notification_type = 'RENT_REMINDER' AND entity_id = :invoice
              AND payload->>'marker' = 'due-7'
            LIMIT 1
            """,
            params,
        )
    assert "Seq Scan" not in plan, plan
    assert "ix_notifications_entity_type" in plan, plan


def test_caretaker_collections_use_the_recorder_index(planned_db):
    engine, params = planned_db
    with engine.connect() as conn:
        plan = _plan(
            conn,
            """
            SELECT method, coalesce(sum(amount), 0) FROM payments
            WHERE organization_id = :org AND recorded_by_id = :user
              AND status = 'CONFIRMED' AND payment_date >= :month
            GROUP BY method
            """,
            params,
        )
    assert "ix_payments_org_recorded_by_date" in plan, plan


def test_every_hot_read_path_can_reach_an_index(planned_db):
    """None of these should be reduced to reading a whole table.

    Checked with sequential scans disabled, which separates "the planner chose
    something else because the table is small" from "there is no index at all".
    """
    engine, params = planned_db
    queries = {
        "collected in a period": """
            SELECT coalesce(sum(amount), 0) FROM payments
            WHERE organization_id = :org AND status = 'CONFIRMED' AND payment_date >= :month
        """,
        "billed in a period": """
            SELECT coalesce(sum(total), 0) FROM invoices
            WHERE organization_id = :org AND period_start >= :month
        """,
        "unpaid invoices": """
            SELECT id FROM invoices
            WHERE organization_id = :org AND status NOT IN ('CANCELLED', 'PAID')
        """,
        "leases expiring on a date": """
            SELECT id FROM tenancies
            WHERE end_date = :month AND is_open_ended = false
              AND status IN ('ACTIVE', 'EXPIRING_SOON')
        """,
    }
    with engine.connect() as conn:
        conn.execute(text("SET enable_seqscan = off"))
        for label, sql in queries.items():
            plan = _plan(conn, sql, params)
            assert "Seq Scan" not in plan, f"{label} has no usable index:\n{plan}"
        conn.execute(text("SET enable_seqscan = on"))
