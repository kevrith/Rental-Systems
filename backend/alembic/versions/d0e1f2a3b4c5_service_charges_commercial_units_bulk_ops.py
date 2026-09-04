"""service charges, commercial unit fields and bulk operations

Sprint 15. A service charge is not the landlord's income, so it gets three
separate tables — what was budgeted, what was spent, and the reserve held back —
rather than one number on the property. Bulk operations get a table because
"who put everyone's rent up in March" must have an answer.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPRINT_15_TABLES = (
    "service_charge_schemes",
    "service_charge_budgets",
    "service_charge_expenses",
    "sinking_fund_entries",
    "bulk_operations",
)

ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "unit_use_class",
        ("OFFICE", "RETAIL", "WAREHOUSE", "INDUSTRIAL", "RESTAURANT", "MEDICAL", "OTHER"),
    ),
    (
        "service_charge_apportionment",
        ("FIXED_PER_UNIT", "BY_FLOOR_AREA", "BY_OCCUPIED_UNIT"),
    ),
    (
        "service_charge_category",
        (
            "SECURITY",
            "CLEANING",
            "COMMON_AREA_MAINTENANCE",
            "GENERATOR",
            "LIFT",
            "WATER",
            "LANDSCAPING",
            "INSURANCE",
            "MANAGEMENT",
            "OTHER",
        ),
    ),
    ("sinking_fund_movement", ("CONTRIBUTION", "WITHDRAWAL")),
    (
        "bulk_operation_kind",
        (
            "RENT_INCREASE",
            "PAYMENT_REMINDER",
            "ANNOUNCEMENT",
            "GENERATE_INVOICES",
            "RENEWAL_NOTICES",
            "DOCUMENT_DISTRIBUTION",
            "TENANT_IMPORT",
        ),
    ),
    (
        "bulk_operation_status",
        ("PREVIEWED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED"),
    ),
)

NEW_NOTIFICATION_TYPES = ("RENT_INCREASE", "ANNOUNCEMENT")


def _enum(name: str) -> postgresql.ENUM:
    """Reference a type this migration already created, without re-creating it."""
    values = next(values for enum_name, values in ENUMS if enum_name == name)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS:
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    # --- commercial unit fields (US-069) ---
    op.add_column("units", sa.Column("use_class", _enum("unit_use_class"), nullable=True))
    op.add_column("units", sa.Column("car_bays", sa.Integer(), nullable=False, server_default="0"))

    # --- service charge scheme (US-070) ---
    op.create_table(
        "service_charge_schemes",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default="Service charge"),
        sa.Column(
            "apportionment",
            _enum("service_charge_apportionment"),
            nullable=False,
            server_default="FIXED_PER_UNIT",
        ),
        sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("monthly_pool", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("sinking_fund_percent", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bill_with_rent", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", name="uq_service_charge_scheme_per_property"),
    )
    op.create_index(
        "ix_service_charge_schemes_organization_id", "service_charge_schemes", ["organization_id"]
    )
    op.create_index("ix_service_charge_schemes_property_id", "service_charge_schemes", ["property_id"])

    op.create_table(
        "service_charge_budgets",
        sa.Column("scheme_id", sa.UUID(), nullable=False),
        sa.Column("category", _enum("service_charge_category"), nullable=False),
        sa.Column("monthly_budget", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["service_charge_schemes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme_id", "category", name="uq_budget_per_category_per_scheme"),
    )
    op.create_index(
        "ix_service_charge_budgets_organization_id", "service_charge_budgets", ["organization_id"]
    )
    op.create_index("ix_service_charge_budgets_scheme_id", "service_charge_budgets", ["scheme_id"])

    op.create_table(
        "service_charge_expenses",
        sa.Column("scheme_id", sa.UUID(), nullable=False),
        sa.Column("category", _enum("service_charge_category"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("vendor_id", sa.UUID(), nullable=True),
        sa.Column("receipt_file_id", sa.UUID(), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["service_charge_schemes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["receipt_file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_charge_expenses_organization_id", "service_charge_expenses", ["organization_id"]
    )
    op.create_index("ix_service_charge_expenses_scheme_id", "service_charge_expenses", ["scheme_id"])
    op.create_index("ix_service_charge_expenses_incurred_on", "service_charge_expenses", ["incurred_on"])

    op.create_table(
        "sinking_fund_entries",
        sa.Column("scheme_id", sa.UUID(), nullable=False),
        sa.Column("movement", _enum("sinking_fund_movement"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("billing_period", sa.Date(), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["service_charge_schemes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sinking_fund_entries_organization_id", "sinking_fund_entries", ["organization_id"])
    op.create_index("ix_sinking_fund_entries_scheme_id", "sinking_fund_entries", ["scheme_id"])
    op.create_index("ix_sinking_fund_entries_entry_date", "sinking_fund_entries", ["entry_date"])

    # --- bulk operations (US-071 to US-073) ---
    op.create_table(
        "bulk_operations",
        sa.Column("kind", _enum("bulk_operation_kind"), nullable=False),
        sa.Column("status", _enum("bulk_operation_status"), nullable=False, server_default="PREVIEWED"),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "targets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "failures",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("property_id", sa.UUID(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("summary", sa.String(512), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bulk_operations_organization_id", "bulk_operations", ["organization_id"])
    op.create_index("ix_bulk_operations_kind", "bulk_operations", ["kind"])
    op.create_index("ix_bulk_operations_status", "bulk_operations", ["status"])

    for statement in enable_table_statements(SPRINT_15_TABLES):
        op.execute(statement)

    for value in NEW_NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    for statement in disable_table_statements(SPRINT_15_TABLES):
        op.execute(statement)

    op.drop_table("bulk_operations")
    op.drop_table("sinking_fund_entries")
    op.drop_table("service_charge_expenses")
    op.drop_table("service_charge_budgets")
    op.drop_table("service_charge_schemes")

    op.drop_column("units", "car_bays")
    op.drop_column("units", "use_class")

    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
