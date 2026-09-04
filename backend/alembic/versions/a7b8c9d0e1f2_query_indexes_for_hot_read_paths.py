"""indexes for the hot read paths found by EXPLAIN ANALYZE

Profiled with EXPLAIN ANALYZE against a seeded five-organisation, 900-unit,
twelve-month portfolio; `tests/test_query_plans.py` pins the results that
mattered so a future change cannot quietly undo them.

Every index below was kept only because the planner actually chose it. Three
more were written, measured, and deleted: composites on
`payments(organization_id, status, payment_date)` and on `invoices` by
`period_start` and by `due_date` all lost to the existing single-column
`organization_id` index, because once a bitmap has narrowed to one tenant the
extra columns do not pay for the wider index. An index nothing chooses is not
neutral — it is a write cost on every insert — so they are not here.

Two things the profiling made obvious, recorded so the next person does not
repeat them:

  * A single-organisation fixture cannot measure a multi-tenant index. With all
    the data under one `organization_id`, that column matches every row and the
    planner rightly ignores it. The profiling seeds five organisations.
  * Whole-table aggregates should sequential-scan. A twelve-month revenue total
    reads most of `payments` however it is indexed; leave it alone.

Column order follows the equality-then-range rule: every leading column is an
equality predicate, and at most the last one is a range.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-04

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, table, columns) — leading column is the one that narrows first.
INDEXES: list[tuple[str, str, list[str]]] = [
    # Caretaker cash discipline: one person's collections over a window. Highly
    # selective on `recorded_by_id`, and the planner picks it unprompted.
    ("ix_payments_org_recorded_by_date", "payments", ["organization_id", "recorded_by_id", "payment_date"]),
    # The vault reads by (entity_type, entity_id) together; two single-column
    # indexes made Postgres bitmap-AND them on every open.
    ("ix_stored_files_org_entity", "stored_files", ["organization_id", "entity_type", "entity_id"]),
    # The "have we already sent this reminder?" check, run once per invoice per
    # night by the reminder sweep.
    ("ix_notifications_entity_type", "notifications", ["entity_id", "notification_type"]),
    # Caretaker meter compliance.
    (
        "ix_meter_readings_org_recorder_date",
        "meter_readings",
        ["organization_id", "recorded_by_id", "reading_date"],
    ),
    # Caretaker response time, and the maintenance cost roll-up per unit.
    ("ix_maintenance_org_unit_created", "maintenance_requests", ["organization_id", "unit_id", "created_at"]),
    # Inspection compliance: move-in reports for a set of tenancies.
    (
        "ix_inspection_org_tenancy_type",
        "inspection_reports",
        ["organization_id", "tenancy_id", "inspection_type"],
    ),
    # Owner rollups on the agency dashboard.
    ("ix_disbursements_org_owner", "disbursements", ["organization_id", "owner_profile_id"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
