"""lease renewals, scheduled task telemetry, and renewal defaults

Three Sprint 12 features that had no schema: the renewal offer a tenant answers,
the per-run record behind the task monitoring dashboard, and the organisation
defaults an automatic renewal is generated from.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_table_statements

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- organisation-level renewal defaults (US-057) ---
    op.add_column(
        "organizations",
        sa.Column(
            "renewal_rent_increase_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0.00",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("renewal_term_months", sa.Integer(), nullable=False, server_default="12"),
    )
    op.add_column(
        "organizations",
        sa.Column("auto_offer_renewals", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # --- lease_renewals ---
    op.create_table(
        "lease_renewals",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("tenancy_id", sa.UUID(), nullable=False),
        sa.Column("current_rent", sa.Numeric(12, 2), nullable=False),
        sa.Column("proposed_rent", sa.Numeric(12, 2), nullable=False),
        sa.Column("rent_increase_percent", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("new_start_date", sa.Date(), nullable=False),
        sa.Column("new_end_date", sa.Date(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column(
            "status",
            sa.Enum("OFFERED", "ACCEPTED", "DECLINED", "LAPSED", name="renewal_status"),
            nullable=False,
            server_default="OFFERED",
        ),
        sa.Column("respond_by", sa.Date(), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("signature_id", sa.UUID(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["signature_id"], ["digital_signatures.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_renewal_ref_per_org"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_lease_renewals_organization_id", "lease_renewals", ["organization_id"])
    op.create_index("ix_lease_renewals_reference_code", "lease_renewals", ["reference_code"])
    op.create_index("ix_lease_renewals_tenancy_id", "lease_renewals", ["tenancy_id"])
    op.create_index("ix_lease_renewals_status", "lease_renewals", ["status"])
    op.create_index("ix_lease_renewals_token_hash", "lease_renewals", ["token_hash"])

    for statement in enable_table_statements(("lease_renewals",)):
        op.execute(statement)

    # --- task_runs ---
    # Deliberately not organisation-scoped and so deliberately without RLS: these
    # tasks sweep every organisation, and a run belongs to the platform.
    op.create_table(
        "task_runs",
        sa.Column("task_name", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("RUNNING", "SUCCEEDED", "FAILED", name="task_run_status"),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_manually", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_runs_task_name", "task_runs", ["task_name"])
    op.create_index("ix_task_runs_status", "task_runs", ["status"])
    op.create_index("ix_task_runs_started_at", "task_runs", ["started_at"])
    # The dashboard's hot query is "latest run per task", so index the pair.
    op.create_index("ix_task_runs_name_started", "task_runs", ["task_name", "started_at"])


def downgrade() -> None:
    op.drop_table("task_runs")
    op.execute("DROP TYPE IF EXISTS task_run_status")

    op.drop_table("lease_renewals")
    op.execute("DROP TYPE IF EXISTS renewal_status")

    op.drop_column("organizations", "auto_offer_renewals")
    op.drop_column("organizations", "renewal_term_months")
    op.drop_column("organizations", "renewal_rent_increase_percent")
