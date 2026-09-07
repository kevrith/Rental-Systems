"""advanced reporting

Sprint 21 (Phase 4): the custom report builder (US-094) and the automatic
monthly summary report (US-093).

`report_definitions` is a saved, replayable query over the same six datasets
`export_service`/`data_exports` already know how to shape — reuses the
existing `export_kind` enum type rather than defining a second one.
`monthly_reports` is one row per organisation per calendar month, unique on
`(organization_id, period_start)` so the Celery Beat scheduler can never
double-generate a period.

Also adds `organizations.report_delivery_channel` — which channel the
monthly summary goes out on, defaulting to both — and extends the existing
`notification_type` and `file_category` enums with `REPORT_READY` and
`REPORT` respectively, the same `ADD VALUE IF NOT EXISTS` approach every
phase since Phase 2 has used to grow those two shared types.

Every Postgres enum label below is the Python enum member's *name*
(`TABLE`, `WHATSAPP`, ...), not its lowercase `.value` — see the Sprint 20
migration's docstring for why that distinction matters here.

Revision ID: 0b6a961c2b8d
Revises: e2f3a4b5c6d7
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "0b6a961c2b8d"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ORG_SCOPED_TABLES = (
    "report_definitions",
    "monthly_reports",
)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'REPORT_READY'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'REPORT'")

    report_delivery_channel = postgresql.ENUM("WHATSAPP", "EMAIL", "BOTH", name="report_delivery_channel")
    report_delivery_channel.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "organizations",
        sa.Column(
            "report_delivery_channel",
            report_delivery_channel,
            nullable=False,
            server_default="BOTH",
        ),
    )

    # --- report_definitions (US-094) ---
    report_chart_type = postgresql.ENUM("TABLE", "BAR", "LINE", "PIE", name="report_chart_type")
    report_schedule = postgresql.ENUM("NONE", "WEEKLY", "MONTHLY", name="report_schedule")
    report_export_format = postgresql.ENUM("CSV", "EXCEL", "PDF", name="report_export_format")
    op.create_table(
        "report_definitions",
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("dataset", postgresql.ENUM(name="export_kind", create_type=False), nullable=False),
        sa.Column("fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("chart_type", report_chart_type, nullable=False, server_default="TABLE"),
        sa.Column("group_by_field", sa.String(100), nullable=True),
        sa.Column("measure_field", sa.String(100), nullable=True),
        sa.Column("export_format", report_export_format, nullable=False, server_default="EXCEL"),
        sa.Column("schedule", report_schedule, nullable=False, server_default="NONE"),
        sa.Column("schedule_day", sa.Integer(), nullable=True),
        sa.Column("delivery_channels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_file_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_run_file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_definitions_organization_id", "report_definitions", ["organization_id"])

    # --- monthly_reports (US-093) ---
    op.create_table(
        "monthly_reports",
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("delivered_channels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "period_start", name="uq_monthly_report_org_period"),
    )
    op.create_index("ix_monthly_reports_organization_id", "monthly_reports", ["organization_id"])

    for statement in enable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("monthly_reports")
    op.drop_table("report_definitions")
    op.execute("DROP TYPE IF EXISTS report_export_format")
    op.execute("DROP TYPE IF EXISTS report_schedule")
    op.execute("DROP TYPE IF EXISTS report_chart_type")

    op.drop_column("organizations", "report_delivery_channel")
    op.execute("DROP TYPE IF EXISTS report_delivery_channel")
