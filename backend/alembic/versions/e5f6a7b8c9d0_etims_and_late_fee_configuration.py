"""KRA eTIMS tables and per-property late fee configuration

Two Phase 2 features were only half-built. The `properties.late_fee_type` and
`late_fee_amount` columns existed, but no model mapped them, so
`late_fee_service` read them through a `getattr` default that always returned
None and every late fee silently evaluated to nothing. This converts the loose
`String(16)` into a real enum, adds the cap the calculator needs, and maps them
on the model. eTIMS had no tables at all.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_table_statements

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ETIMS_TABLES = ("etims_credentials", "etims_submissions")


def upgrade() -> None:
    # --- per-property late fee configuration (US-055) ---
    # The column already exists as a free-text String(16). Convert it in place to
    # an enum carrying the Python member names, upper-casing whatever is stored;
    # anything unrecognised becomes NULL, which means "charge nothing".
    late_fee_type = postgresql.ENUM("FIXED", "PERCENT", "DAILY", name="late_fee_type")
    late_fee_type.create(op.get_bind(), checkfirst=True)

    op.execute(
        "UPDATE properties SET late_fee_type = upper(late_fee_type) " "WHERE late_fee_type IS NOT NULL"
    )
    op.execute(
        "UPDATE properties SET late_fee_type = NULL "
        "WHERE late_fee_type NOT IN ('FIXED', 'PERCENT', 'DAILY')"
    )
    op.execute(
        "ALTER TABLE properties ALTER COLUMN late_fee_type "
        "TYPE late_fee_type USING late_fee_type::late_fee_type"
    )
    op.add_column("properties", sa.Column("late_fee_cap", sa.Numeric(12, 2), nullable=True))

    # --- eTIMS ---
    op.create_table(
        "etims_credentials",
        sa.Column("kra_pin", sa.String(32), nullable=False),
        sa.Column("device_serial_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("branch_id", sa.String(16), nullable=False, server_default="00"),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_etims_credential_per_org"),
    )
    op.create_index("ix_etims_credentials_organization_id", "etims_credentials", ["organization_id"])

    op.create_table(
        "etims_submissions",
        sa.Column("receipt_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SUBMITTED", "FAILED", "ABANDONED", name="etims_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invoice_number", sa.String(64), nullable=True),
        sa.Column("control_unit_serial", sa.String(64), nullable=True),
        sa.Column("control_unit_signature", sa.String(128), nullable=True),
        sa.Column("verification_url", sa.String(512), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_id", name="uq_etims_submission_per_receipt"),
    )
    op.create_index("ix_etims_submissions_organization_id", "etims_submissions", ["organization_id"])
    op.create_index("ix_etims_submissions_receipt_id", "etims_submissions", ["receipt_id"])
    op.create_index("ix_etims_submissions_status", "etims_submissions", ["status"])
    op.create_index("ix_etims_submissions_next_attempt_at", "etims_submissions", ["next_attempt_at"])

    # Both tables hold one organisation's tax identity — RLS from the start.
    for statement in enable_table_statements(ETIMS_TABLES):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("etims_submissions")
    op.drop_table("etims_credentials")
    op.execute("DROP TYPE IF EXISTS etims_status")

    op.drop_column("properties", "late_fee_cap")
    op.execute("ALTER TABLE properties ALTER COLUMN late_fee_type TYPE VARCHAR(16)")
    op.execute("UPDATE properties SET late_fee_type = lower(late_fee_type) WHERE late_fee_type IS NOT NULL")
    op.execute("DROP TYPE IF EXISTS late_fee_type")
