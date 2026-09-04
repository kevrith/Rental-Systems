"""phase 2: agency mode, owner profiles, disbursements, inspections, signatures, late fees

Revision ID: a1b2c3d4e5f6
Revises: becdc2a16b45
Create Date: 2026-09-10 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2c1d19d1badc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- owner_profiles ---
    op.create_table(
        "owner_profiles",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("national_id", sa.String(64), nullable=True),
        sa.Column("kra_pin", sa.String(32), nullable=True),
        sa.Column("bank_name", sa.String(128), nullable=True),
        sa.Column("bank_account_number", sa.String(64), nullable=True),
        sa.Column("bank_account_name", sa.String(255), nullable=True),
        sa.Column("mpesa_phone", sa.String(32), nullable=True),
        sa.Column("management_fee_percent", sa.Numeric(5, 2), nullable=False, server_default="8.00"),
        sa.Column("disbursement_day", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "maintenance_auto_approve_limit", sa.Numeric(12, 2), nullable=False, server_default="5000.00"
        ),
        sa.Column("maintenance_notify_limit", sa.Numeric(12, 2), nullable=False, server_default="20000.00"),
        sa.Column("portal_user_id", sa.UUID(), nullable=True),
        sa.Column("portal_invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["portal_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_owner_profile_ref_per_org"),
        sa.UniqueConstraint("portal_user_id"),
    )
    op.create_index("ix_owner_profiles_organization_id", "owner_profiles", ["organization_id"])
    op.create_index("ix_owner_profiles_reference_code", "owner_profiles", ["reference_code"])

    # --- disbursements ---
    op.create_table(
        "disbursements",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("owner_profile_id", sa.UUID(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("gross_rent", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("management_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("maintenance_costs", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("other_deductions", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column(
            "status",
            sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="disbursement_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("payment_method", sa.String(32), nullable=True),
        sa.Column("payment_reference", sa.String(128), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(512), nullable=True),
        sa.Column("statement_document_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("initiated_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["owner_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_disbursement_ref_per_org"),
    )
    op.create_index("ix_disbursements_organization_id", "disbursements", ["organization_id"])
    op.create_index("ix_disbursements_owner_profile_id", "disbursements", ["owner_profile_id"])
    op.create_index("ix_disbursements_status", "disbursements", ["status"])
    op.create_index("ix_disbursements_reference_code", "disbursements", ["reference_code"])

    # --- inspection_reports ---
    op.create_table(
        "inspection_reports",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("tenancy_id", sa.UUID(), nullable=True),
        sa.Column(
            "inspection_type",
            sa.Enum("MOVE_IN", "MOVE_OUT", "ROUTINE", name="inspection_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "SUBMITTED", name="inspection_status"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("rooms_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("inspector_id", sa.UUID(), nullable=True),
        sa.Column("inspector_name", sa.String(255), nullable=True),
        sa.Column("gps_latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("gps_longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("report_document_id", sa.UUID(), nullable=True),
        sa.Column("comparison_document_id", sa.UUID(), nullable=True),
        sa.Column("move_in_report_id", sa.UUID(), nullable=True),
        sa.Column("deposit_deduction", sa.Numeric(12, 2), nullable=True),
        sa.Column("deduction_notes", sa.Text(), nullable=True),
        sa.Column("tenant_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tenant_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inspector_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["report_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["comparison_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["move_in_report_id"], ["inspection_reports.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_inspection_ref_per_org"),
    )
    op.create_index("ix_inspection_reports_organization_id", "inspection_reports", ["organization_id"])
    op.create_index("ix_inspection_reports_unit_id", "inspection_reports", ["unit_id"])
    op.create_index("ix_inspection_reports_tenancy_id", "inspection_reports", ["tenancy_id"])
    op.create_index("ix_inspection_reports_inspection_type", "inspection_reports", ["inspection_type"])
    op.create_index("ix_inspection_reports_reference_code", "inspection_reports", ["reference_code"])

    # --- digital_signatures ---
    op.create_table(
        "digital_signatures",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("tenancy_id", sa.UUID(), nullable=True),
        sa.Column("signer_name", sa.String(255), nullable=False),
        sa.Column("signer_phone", sa.String(32), nullable=False),
        sa.Column("signer_role", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SIGNED", "EXPIRED", "REVOKED", name="signature_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("gps_latitude", sa.String(32), nullable=True),
        sa.Column("gps_longitude", sa.String(32), nullable=True),
        sa.Column("otp_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_image", sa.Text(), nullable=True),
        sa.Column("signed_document_id", sa.UUID(), nullable=True),
        sa.Column("otp_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["stored_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["signed_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_digital_signatures_organization_id", "digital_signatures", ["organization_id"])
    op.create_index("ix_digital_signatures_document_id", "digital_signatures", ["document_id"])
    op.create_index("ix_digital_signatures_tenancy_id", "digital_signatures", ["tenancy_id"])
    op.create_index("ix_digital_signatures_token_hash", "digital_signatures", ["token_hash"], unique=True)
    op.create_index("ix_digital_signatures_status", "digital_signatures", ["status"])

    # --- add owner_profile_id to properties ---
    op.add_column("properties", sa.Column("owner_profile_id", sa.UUID(), nullable=True))
    op.create_index("ix_properties_owner_profile_id", "properties", ["owner_profile_id"])
    op.create_foreign_key(
        "fk_properties_owner_profile_id",
        "properties",
        "owner_profiles",
        ["owner_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- late fee config on properties (Phase 2 automation) ---
    op.add_column(
        "properties",
        sa.Column("late_fee_type", sa.String(16), nullable=True),  # "fixed", "percent", "daily"
    )
    op.add_column(
        "properties",
        sa.Column("late_fee_amount", sa.Numeric(12, 2), nullable=True),
    )

    # --- add new notification types for Phase 2 ---
    # Extend the enum by recreating it (PostgreSQL requires this)
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DISBURSEMENT_SENT'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'INSPECTION_COMPLETED'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'LATE_FEE_APPLIED'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'OWNER_PORTAL_INVITE'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'LEASE_RENEWAL'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'DOCUMENT_SIGNED'")

    # --- add new file categories for Phase 2 ---
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'INSPECTION_PHOTO'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'INSPECTION_REPORT'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'OWNER_STATEMENT'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'SIGNED_DOCUMENT'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'SIGNATURE_IMAGE'")


def downgrade() -> None:
    op.drop_constraint("fk_properties_owner_profile_id", "properties", type_="foreignkey")
    op.drop_index("ix_properties_owner_profile_id", table_name="properties")
    op.drop_column("properties", "owner_profile_id")
    op.drop_column("properties", "late_fee_type")
    op.drop_column("properties", "late_fee_amount")

    op.drop_index("ix_digital_signatures_status", table_name="digital_signatures")
    op.drop_index("ix_digital_signatures_token_hash", table_name="digital_signatures")
    op.drop_index("ix_digital_signatures_tenancy_id", table_name="digital_signatures")
    op.drop_index("ix_digital_signatures_document_id", table_name="digital_signatures")
    op.drop_index("ix_digital_signatures_organization_id", table_name="digital_signatures")
    op.drop_table("digital_signatures")

    op.drop_index("ix_inspection_reports_reference_code", table_name="inspection_reports")
    op.drop_index("ix_inspection_reports_inspection_type", table_name="inspection_reports")
    op.drop_index("ix_inspection_reports_tenancy_id", table_name="inspection_reports")
    op.drop_index("ix_inspection_reports_unit_id", table_name="inspection_reports")
    op.drop_index("ix_inspection_reports_organization_id", table_name="inspection_reports")
    op.drop_table("inspection_reports")

    op.drop_index("ix_disbursements_reference_code", table_name="disbursements")
    op.drop_index("ix_disbursements_status", table_name="disbursements")
    op.drop_index("ix_disbursements_owner_profile_id", table_name="disbursements")
    op.drop_index("ix_disbursements_organization_id", table_name="disbursements")
    op.drop_table("disbursements")

    op.drop_index("ix_owner_profiles_reference_code", table_name="owner_profiles")
    op.drop_index("ix_owner_profiles_organization_id", table_name="owner_profiles")
    op.drop_table("owner_profiles")

    # Postgres keeps enum types after their tables are gone, so a downgrade that
    # left them behind would make the next upgrade fail on "type already exists".
    for enum_name in (
        "disbursement_status",
        "inspection_type",
        "inspection_status",
        "signature_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
