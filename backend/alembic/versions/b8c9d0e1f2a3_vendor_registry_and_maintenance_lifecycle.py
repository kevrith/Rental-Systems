"""vendor registry and the full maintenance lifecycle

Sprint 13. Three things land together because they are one feature: the vendor
list a job is assigned to, the approval/assignment columns on the request, and
the wider set of statuses that lifecycle moves through.

`maintenance_status` is rebuilt rather than extended — the old `ACKNOWLEDGED`
value has no place in the new flow, and existing rows carrying it are rewritten
to `UNDER_REVIEW`, which is what it meant.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_STATUSES = (
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    "ASSIGNED",
    "IN_PROGRESS",
    "COMPLETED",
    "CLOSED",
    "CANCELLED",
)

OLD_STATUSES = ("SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS", "COMPLETED", "CANCELLED")

NEW_NOTIFICATION_TYPES = (
    "MAINTENANCE_APPROVED",
    "MAINTENANCE_REJECTED",
    "MAINTENANCE_OVERDUE",
    "VENDOR_ASSIGNED",
)


def _swap_status_enum(target: Sequence[str], mapping: str) -> None:
    """Rebuild `maintenance_status` in place.

    Postgres will not remove a value from an enum, so the type is replaced and
    the column cast across with `mapping` deciding what each old value becomes.
    """
    values = ", ".join(f"'{value}'" for value in target)
    op.execute("ALTER TYPE maintenance_status RENAME TO maintenance_status_old")
    op.execute(f"CREATE TYPE maintenance_status AS ENUM ({values})")
    op.execute("ALTER TABLE maintenance_requests ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE maintenance_requests ALTER COLUMN status TYPE maintenance_status "
        f"USING ({mapping})::maintenance_status"
    )
    op.execute("ALTER TABLE maintenance_requests ALTER COLUMN status SET DEFAULT 'SUBMITTED'")
    op.execute("DROP TYPE maintenance_status_old")


def upgrade() -> None:
    # --- vendors (US-060) ---
    op.create_table(
        "vendors",
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "specialties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("rate_notes", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rating_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_billed", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "phone_number", name="uq_vendor_phone_per_org"),
    )
    op.create_index("ix_vendors_organization_id", "vendors", ["organization_id"])
    op.create_index("ix_vendors_name", "vendors", ["name"])
    op.create_index("ix_vendors_is_active", "vendors", ["is_active"])
    op.create_index("ix_vendors_is_archived", "vendors", ["is_archived"])

    for statement in enable_table_statements(("vendors",)):
        op.execute(statement)

    # --- the wider lifecycle (US-061) ---
    _swap_status_enum(
        NEW_STATUSES,
        "CASE status::text WHEN 'ACKNOWLEDGED' THEN 'UNDER_REVIEW' ELSE status::text END",
    )

    rejection_reason = postgresql.ENUM(
        "NOT_LANDLORD_RESPONSIBILITY",
        "TENANT_CAUSED_DAMAGE",
        "DUPLICATE_REQUEST",
        "COST_NOT_JUSTIFIED",
        "SCHEDULED_FOR_LATER",
        "OTHER",
        name="maintenance_rejection_reason",
    )
    rejection_reason.create(op.get_bind(), checkfirst=True)

    for column in (
        sa.Column("estimated_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("rejection_reason", rejection_reason, nullable=True),
        sa.Column("rejection_note", sa.Text(), nullable=True),
        sa.Column("info_requested", sa.Text(), nullable=True),
        sa.Column("info_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vendor_id", sa.UUID(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by_id", sa.UUID(), nullable=True),
        sa.Column("expected_completion_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_overdue", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("overdue_flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_id", sa.UUID(), nullable=True),
        sa.Column("vendor_rating", sa.Integer(), nullable=True),
        sa.Column("vendor_review", sa.Text(), nullable=True),
        sa.Column("tenant_rating", sa.Integer(), nullable=True),
        sa.Column("tenant_feedback", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_expense_allocated", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        op.add_column("maintenance_requests", column)

    op.create_foreign_key(
        "fk_maintenance_vendor",
        "maintenance_requests",
        "vendors",
        ["vendor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for name, column in (
        ("fk_maintenance_approved_by", "approved_by_id"),
        ("fk_maintenance_assigned_by", "assigned_by_id"),
        ("fk_maintenance_completed_by", "completed_by_id"),
    ):
        op.create_foreign_key(name, "maintenance_requests", "users", [column], ["id"], ondelete="SET NULL")

    op.create_index("ix_maintenance_requests_vendor_id", "maintenance_requests", ["vendor_id"])
    op.create_index("ix_maintenance_requests_is_overdue", "maintenance_requests", ["is_overdue"])
    op.create_index(
        "ix_maintenance_requests_expected_completion",
        "maintenance_requests",
        ["expected_completion_date"],
    )

    op.create_check_constraint(
        "ck_maintenance_vendor_rating_range",
        "maintenance_requests",
        "vendor_rating IS NULL OR (vendor_rating BETWEEN 1 AND 5)",
    )
    op.create_check_constraint(
        "ck_maintenance_tenant_rating_range",
        "maintenance_requests",
        "tenant_rating IS NULL OR (tenant_rating BETWEEN 1 AND 5)",
    )

    # --- maintenance budget (US-062) ---
    op.add_column("properties", sa.Column("maintenance_budget_monthly", sa.Numeric(12, 2), nullable=True))

    # --- notification types for the new lifecycle events ---
    for value in NEW_NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_column("properties", "maintenance_budget_monthly")

    op.drop_constraint("ck_maintenance_tenant_rating_range", "maintenance_requests", type_="check")
    op.drop_constraint("ck_maintenance_vendor_rating_range", "maintenance_requests", type_="check")
    op.drop_index("ix_maintenance_requests_expected_completion", "maintenance_requests")
    op.drop_index("ix_maintenance_requests_is_overdue", "maintenance_requests")
    op.drop_index("ix_maintenance_requests_vendor_id", "maintenance_requests")

    for name in (
        "fk_maintenance_completed_by",
        "fk_maintenance_assigned_by",
        "fk_maintenance_approved_by",
        "fk_maintenance_vendor",
    ):
        op.drop_constraint(name, "maintenance_requests", type_="foreignkey")

    for column in (
        "owner_expense_allocated",
        "closed_at",
        "tenant_feedback",
        "tenant_rating",
        "vendor_review",
        "vendor_rating",
        "completed_by_id",
        "overdue_flagged_at",
        "is_overdue",
        "started_at",
        "expected_completion_date",
        "assigned_by_id",
        "assigned_at",
        "vendor_id",
        "info_requested_at",
        "info_requested",
        "rejection_note",
        "rejection_reason",
        "approved_by_id",
        "approved_at",
        "reviewed_at",
        "estimated_cost",
    ):
        op.drop_column("maintenance_requests", column)

    op.execute("DROP TYPE IF EXISTS maintenance_rejection_reason")

    # Everything the old enum could not express collapses back onto its nearest
    # pre-Sprint-13 equivalent.
    _swap_status_enum(
        OLD_STATUSES,
        """
        CASE status::text
            WHEN 'UNDER_REVIEW' THEN 'ACKNOWLEDGED'
            WHEN 'APPROVED' THEN 'ACKNOWLEDGED'
            WHEN 'ASSIGNED' THEN 'ACKNOWLEDGED'
            WHEN 'REJECTED' THEN 'CANCELLED'
            WHEN 'CLOSED' THEN 'COMPLETED'
            ELSE status::text
        END
        """,
    )

    for statement in disable_table_statements(("vendors",)):
        op.execute(statement)
    op.drop_table("vendors")
