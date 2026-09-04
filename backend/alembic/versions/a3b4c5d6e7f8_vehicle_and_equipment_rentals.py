"""vehicle and equipment rental assets and hire agreements

Sprint 18. A car and a generator are the same business — an asset that goes out,
comes back, and is worth less if it comes back worse — so both live in one table
with a `kind` discriminator, and one agreement covers the hire.

The condition snapshots (mileage, fuel and photos at check-out and again at
check-in) are the point: they turn "you scratched it" from an argument into a
comparison, which is what a deposit exists to settle.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPRINT_18_TABLES = ("rental_assets", "rental_agreements")

ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("asset_kind", ("VEHICLE", "EQUIPMENT")),
    ("asset_status", ("AVAILABLE", "ON_HIRE", "MAINTENANCE", "RETIRED")),
    ("fuel_policy", ("FULL_TO_FULL", "SAME_TO_SAME", "PREPAID")),
    ("rate_basis", ("DAILY", "WEEKLY", "MONTHLY")),
    ("agreement_status", ("BOOKED", "OUT", "RETURNED", "CANCELLED")),
)


def _enum(name: str) -> postgresql.ENUM:
    values = next(values for enum_name, values in ENUMS if enum_name == name)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS:
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.create_table(
        "rental_assets",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("kind", _enum("asset_kind"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=True),
        sa.Column("status", _enum("asset_status"), nullable=False, server_default="AVAILABLE"),
        sa.Column("daily_rate", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("weekly_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("deposit_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column(
            "photo_file_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        # Vehicles
        sa.Column("registration_number", sa.String(32), nullable=True),
        sa.Column("make", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("colour", sa.String(32), nullable=True),
        sa.Column("mileage", sa.Integer(), nullable=True),
        sa.Column("fuel_policy", _enum("fuel_policy"), nullable=False, server_default="FULL_TO_FULL"),
        sa.Column("daily_mileage_limit", sa.Integer(), nullable=True),
        sa.Column("excess_mileage_rate", sa.Numeric(10, 2), nullable=True),
        sa.Column("insurance_expiry", sa.Date(), nullable=True),
        sa.Column("inspection_expiry", sa.Date(), nullable=True),
        sa.Column("road_licence_expiry", sa.Date(), nullable=True),
        # Equipment
        sa.Column("serial_number", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("service_interval_days", sa.Integer(), nullable=True),
        sa.Column("last_serviced_on", sa.Date(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_asset_ref_per_org"),
    )
    for column in (
        "organization_id",
        "reference_code",
        "kind",
        "name",
        "status",
        "property_id",
        "registration_number",
        "serial_number",
        "insurance_expiry",
        "inspection_expiry",
        "road_licence_expiry",
        "is_archived",
    ):
        op.create_index(f"ix_rental_assets_{column}", "rental_assets", [column])

    op.create_table(
        "rental_agreements",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("rate_basis", _enum("rate_basis"), nullable=False, server_default="DAILY"),
        sa.Column("rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("deposit_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("deposit_refunded", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", _enum("agreement_status"), nullable=False, server_default="BOOKED"),
        # Check-out snapshot
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mileage_out", sa.Integer(), nullable=True),
        sa.Column("fuel_out_eighths", sa.Integer(), nullable=True),
        sa.Column("condition_out", sa.Text(), nullable=True),
        sa.Column(
            "photos_out",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("driver_licence_file_id", sa.UUID(), nullable=True),
        sa.Column("checked_out_by_id", sa.UUID(), nullable=True),
        # Check-in snapshot
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mileage_in", sa.Integer(), nullable=True),
        sa.Column("fuel_in_eighths", sa.Integer(), nullable=True),
        sa.Column("condition_in", sa.Text(), nullable=True),
        sa.Column(
            "photos_in",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("checked_in_by_id", sa.UUID(), nullable=True),
        # Money
        sa.Column("hire_charge", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("excess_mileage_charge", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("damage_charge", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("fuel_charge", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("late_charge", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("total_charge", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("agreement_document_id", sa.UUID(), nullable=True),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["rental_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_licence_file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agreement_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["checked_out_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["checked_in_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_agreement_ref_per_org"),
    )
    for column in (
        "organization_id",
        "reference_code",
        "asset_id",
        "tenant_id",
        "start_date",
        "end_date",
        "status",
    ):
        op.create_index(f"ix_rental_agreements_{column}", "rental_agreements", [column])

    # The overlap check is always "this asset, over this window".
    op.create_index(
        "ix_rental_agreements_asset_window",
        "rental_agreements",
        ["asset_id", "start_date", "end_date"],
    )

    for statement in enable_table_statements(SPRINT_18_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(SPRINT_18_TABLES):
        op.execute(statement)

    op.drop_table("rental_agreements")
    op.drop_table("rental_assets")

    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
