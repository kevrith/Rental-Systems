"""Partner integrations and bank transfer reconciliation

Sprint 23 (Phase 4): property portal sync (US-099), accounting software sync
(US-100), and bank transfer as a first-class payment method (US-101).

`portal_connections`/`portal_listing_syncs` and `accounting_connections`/
`accounting_sync_records` follow the same shape `etims_credentials`/
`etims_submissions` established: an organisation's own credentials for a
partner system, encrypted at rest, and a durable row per sync attempt.
`bank_statement_uploads`/`bank_statement_entries` hold an uploaded statement
and what each line matched to, if anything — matching only ever proposes, it
never writes a payment by itself.

Also adds `organizations.bank_*` (the instructions shown to a tenant),
`payments.bank_reference` (a bank/cheque reference distinct from the globally
unique `mpesa_receipt`, since bank reference formats can collide across
organisations), and `inquiries.source` (so a portal-sourced lead is
distinguishable from one that came through the public listing page).

Every enum label below is the Python enum member's *name*, not its lowercase
`.value` — see the Sprint 20 migration's docstring for why that distinction
matters here.

Revision ID: 7f8a9b0c1d2e
Revises: 1a2b3c4d5e6f
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "7f8a9b0c1d2e"
down_revision: str | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ORG_SCOPED_TABLES = (
    "portal_connections",
    "portal_listing_syncs",
    "accounting_connections",
    "accounting_sync_records",
    "bank_statement_uploads",
    "bank_statement_entries",
)


def upgrade() -> None:
    # --- organizations: bank transfer instructions (US-101) ---
    op.add_column("organizations", sa.Column("bank_name", sa.String(128), nullable=True))
    op.add_column("organizations", sa.Column("bank_account_name", sa.String(255), nullable=True))
    op.add_column("organizations", sa.Column("bank_account_number", sa.String(64), nullable=True))
    op.add_column("organizations", sa.Column("bank_branch", sa.String(128), nullable=True))

    # --- payments: a bank/cheque reference, distinct from mpesa_receipt (US-101) ---
    op.add_column("payments", sa.Column("bank_reference", sa.String(64), nullable=True))
    op.create_index("ix_payments_bank_reference", "payments", ["bank_reference"])

    # --- inquiries: which channel produced this lead (US-099) ---
    op.add_column(
        "inquiries",
        sa.Column("source", sa.String(32), nullable=False, server_default="direct"),
    )

    # --- portal_connections / portal_listing_syncs (US-099) ---
    portal_name = postgresql.ENUM("BUYRENTKENYA", "PIGIAME", name="portal_name")
    op.create_table(
        "portal_connections",
        sa.Column("portal", portal_name, nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("account_id", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "portal", name="uq_portal_connection_per_org"),
    )
    op.create_index("ix_portal_connections_organization_id", "portal_connections", ["organization_id"])

    portal_sync_status = postgresql.ENUM(
        "PENDING", "PUBLISHED", "DEACTIVATED", "FAILED", name="portal_sync_status"
    )
    op.create_table(
        "portal_listing_syncs",
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("external_listing_id", sa.String(128), nullable=True),
        sa.Column("status", portal_sync_status, nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["vacancy_listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["portal_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", "connection_id", name="uq_portal_sync_per_listing_connection"),
    )
    op.create_index("ix_portal_listing_syncs_organization_id", "portal_listing_syncs", ["organization_id"])
    op.create_index("ix_portal_listing_syncs_listing_id", "portal_listing_syncs", ["listing_id"])
    op.create_index("ix_portal_listing_syncs_connection_id", "portal_listing_syncs", ["connection_id"])
    op.create_index("ix_portal_listing_syncs_status", "portal_listing_syncs", ["status"])

    # --- accounting_connections / accounting_sync_records (US-100) ---
    accounting_provider = postgresql.ENUM("QUICKBOOKS", "XERO", name="accounting_provider")
    op.create_table(
        "accounting_connections",
        sa.Column("provider", accounting_provider, nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("connected_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connected_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "provider", name="uq_accounting_connection_per_org"),
    )
    op.create_index(
        "ix_accounting_connections_organization_id", "accounting_connections", ["organization_id"]
    )

    accounting_entity_type = postgresql.ENUM(
        "PAYMENT", "MAINTENANCE_COST", "DISBURSEMENT", name="accounting_entity_type"
    )
    accounting_sync_status = postgresql.ENUM("PENDING", "SYNCED", "FAILED", name="accounting_sync_status")
    op.create_table(
        "accounting_sync_records",
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", accounting_entity_type, nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("status", accounting_sync_status, nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["accounting_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id", "entity_type", "entity_id", name="uq_accounting_sync_per_entity"
        ),
    )
    op.create_index(
        "ix_accounting_sync_records_organization_id", "accounting_sync_records", ["organization_id"]
    )
    op.create_index("ix_accounting_sync_records_connection_id", "accounting_sync_records", ["connection_id"])
    op.create_index("ix_accounting_sync_records_entity_type", "accounting_sync_records", ["entity_type"])
    op.create_index("ix_accounting_sync_records_entity_id", "accounting_sync_records", ["entity_id"])
    op.create_index("ix_accounting_sync_records_status", "accounting_sync_records", ["status"])

    # --- bank_statement_uploads / bank_statement_entries (US-101) ---
    op.create_table(
        "bank_statement_uploads",
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("uploaded_by_id", sa.UUID(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bank_statement_uploads_organization_id", "bank_statement_uploads", ["organization_id"]
    )

    op.create_table(
        "bank_statement_entries",
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("matched_tenancy_id", sa.UUID(), nullable=True),
        sa.Column("matched_payment_id", sa.UUID(), nullable=True),
        sa.Column("is_matched", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["bank_statement_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_tenancy_id"], ["tenancies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bank_statement_entries_organization_id", "bank_statement_entries", ["organization_id"]
    )
    op.create_index("ix_bank_statement_entries_upload_id", "bank_statement_entries", ["upload_id"])

    for statement in enable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("bank_statement_entries")
    op.drop_table("bank_statement_uploads")

    op.drop_table("accounting_sync_records")
    op.execute("DROP TYPE IF EXISTS accounting_sync_status")
    op.execute("DROP TYPE IF EXISTS accounting_entity_type")
    op.drop_table("accounting_connections")
    op.execute("DROP TYPE IF EXISTS accounting_provider")

    op.drop_table("portal_listing_syncs")
    op.execute("DROP TYPE IF EXISTS portal_sync_status")
    op.drop_table("portal_connections")
    op.execute("DROP TYPE IF EXISTS portal_name")

    op.drop_column("inquiries", "source")
    op.drop_index("ix_payments_bank_reference", table_name="payments")
    op.drop_column("payments", "bank_reference")

    op.drop_column("organizations", "bank_branch")
    op.drop_column("organizations", "bank_account_number")
    op.drop_column("organizations", "bank_account_name")
    op.drop_column("organizations", "bank_name")
