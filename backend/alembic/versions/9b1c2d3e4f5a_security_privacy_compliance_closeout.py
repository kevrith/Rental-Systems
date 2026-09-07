"""security, privacy & compliance closeout

Sprint 25 (Phase 5): virus scanning on upload (US-105), a data subject access
and erasure workflow for tenants (US-106), co-tenant support (US-107), and
WebAuthn/passkey login (US-108) — plus the caretaker visitor log (US-109).

`stored_files` gains a scan verdict per file rather than a separate scan-log
table: every file has exactly one current verdict, and the retry sweep only
ever needs to update it in place. `tenancy_co_tenants` is purely additive next
to `tenancies.tenant_id` — nothing about invoicing or arrears changes shape.
`data_requests` is scoped to tenants only; a staff account's own export and
erasure paths already exist (`/auth/me/data-export`, `/auth/me/delete`) and
gain nothing from a second tracking table. `webauthn_credentials` holds one row
per registered authenticator, `credential_id`/`public_key` stored base64url
the same way the WebAuthn exchange itself represents them.

Every enum label below is the Python enum member's *name*, not its lowercase
`.value` — see the Sprint 20 migration's docstring for why that distinction
matters here.

Revision ID: 9b1c2d3e4f5a
Revises: 7f8a9b0c1d2e
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "9b1c2d3e4f5a"
down_revision: str | None = "7f8a9b0c1d2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ORG_SCOPED_TABLES = (
    "visitor_logs",
    "tenancy_co_tenants",
    "data_requests",
    "webauthn_credentials",
)

SCAN_STATUS_VALUES = ("PENDING", "CLEAN", "INFECTED", "FAILED", "SKIPPED")


def _scan_status() -> postgresql.ENUM:
    return postgresql.ENUM(*SCAN_STATUS_VALUES, name="scan_status", create_type=False)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DATA_REQUEST'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'DATA_REQUEST_EXPORT'")

    # --- virus scanning on upload (US-105) ---
    scan_status_literals = ", ".join(f"'{value}'" for value in SCAN_STATUS_VALUES)
    op.execute(f"CREATE TYPE scan_status AS ENUM ({scan_status_literals})")
    op.add_column(
        "stored_files",
        sa.Column("scan_status", _scan_status(), nullable=False, server_default="PENDING"),
    )
    op.add_column("stored_files", sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stored_files", sa.Column("scan_detail", sa.String(255), nullable=True))

    # --- caretaker visitor log (US-109) ---
    op.create_table(
        "visitor_logs",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("visitor_name", sa.String(255), nullable=False),
        sa.Column("visitor_phone", sa.String(32), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("gps_latitude", sa.Float(), nullable=True),
        sa.Column("gps_longitude", sa.Float(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_visitor_logs_organization_id", "visitor_logs", ["organization_id"])
    op.create_index("ix_visitor_logs_property_id", "visitor_logs", ["property_id"])
    op.create_index("ix_visitor_logs_unit_id", "visitor_logs", ["unit_id"])
    op.create_index("ix_visitor_logs_checked_in_at", "visitor_logs", ["checked_in_at"])

    # --- co-tenant support (US-107) ---
    op.add_column("tenants", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "tenancy_co_tenants",
        sa.Column("tenancy_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("added_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenancy_id", "tenant_id", name="uq_co_tenant_per_tenancy"),
    )
    op.create_index("ix_tenancy_co_tenants_organization_id", "tenancy_co_tenants", ["organization_id"])
    op.create_index("ix_tenancy_co_tenants_tenancy_id", "tenancy_co_tenants", ["tenancy_id"])
    op.create_index("ix_tenancy_co_tenants_tenant_id", "tenancy_co_tenants", ["tenant_id"])

    # --- data subject access & erasure requests (US-106) ---
    data_request_type = postgresql.ENUM("EXPORT", "ERASURE", name="data_request_type")
    data_request_status = postgresql.ENUM("COMPLETED", "FAILED", name="data_request_status")
    op.create_table(
        "data_requests",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("request_type", data_request_type, nullable=False),
        sa.Column("status", data_request_status, nullable=False, server_default="COMPLETED"),
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
        sa.Column("export_file_id", sa.UUID(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["export_file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_requests_organization_id", "data_requests", ["organization_id"])
    op.create_index("ix_data_requests_tenant_id", "data_requests", ["tenant_id"])

    # --- WebAuthn / passkey login (US-108) ---
    op.create_table(
        "webauthn_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.String(512), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_name", sa.String(255), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id", name="uq_webauthn_credential_id"),
    )
    op.create_index("ix_webauthn_credentials_organization_id", "webauthn_credentials", ["organization_id"])
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])
    op.create_index("ix_webauthn_credentials_credential_id", "webauthn_credentials", ["credential_id"])

    for statement in enable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("webauthn_credentials")

    op.drop_table("data_requests")
    op.execute("DROP TYPE IF EXISTS data_request_status")
    op.execute("DROP TYPE IF EXISTS data_request_type")

    op.drop_table("tenancy_co_tenants")
    op.drop_column("tenants", "erased_at")

    op.drop_table("visitor_logs")

    op.drop_column("stored_files", "scan_detail")
    op.drop_column("stored_files", "scanned_at")
    op.drop_column("stored_files", "scan_status")
    op.execute("DROP TYPE IF EXISTS scan_status")
