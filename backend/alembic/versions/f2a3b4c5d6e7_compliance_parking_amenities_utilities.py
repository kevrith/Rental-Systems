"""compliance calendar, parking bays, shared amenities and utility accounts

Sprint 17. Four things that share a shape: obligations attached to a building
rather than to a tenancy. An expired lift certificate is not a paperwork problem
— it is the day the insurer refuses a claim — so expiry is a first-class,
indexed date with its own reminder ladder.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPRINT_17_TABLES = (
    "compliance_items",
    "parking_bays",
    "parking_allocations",
    "amenities",
    "amenity_bookings",
    "utility_accounts",
)

ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "compliance_type",
        (
            "FIRE_SAFETY",
            "HEALTH_INSPECTION",
            "NEMA",
            "LIFT_INSPECTION",
            "ELECTRICAL_INSPECTION",
            "WATER_SAFETY",
            "INSURANCE",
            "BUSINESS_PERMIT",
            "STRUCTURAL_SURVEY",
            "OTHER",
        ),
    ),
    ("bay_type", ("COVERED", "OPEN", "RESERVED", "VISITOR", "DISABLED")),
    (
        "amenity_kind",
        ("GYM", "MEETING_ROOM", "ROOFTOP", "POOL", "CLUBHOUSE", "PLAYGROUND", "LAUNDRY", "OTHER"),
    ),
    ("booking_status", ("CONFIRMED", "CANCELLED", "BLOCKED")),
    ("utility_account_type", ("KPLC", "WATER", "INTERNET", "GARBAGE", "OTHER")),
    ("utility_payment_status", ("PAID", "UNPAID", "UNKNOWN")),
)

NEW_NOTIFICATION_TYPES = ("COMPLIANCE_EXPIRY", "AMENITY_BOOKING", "UTILITY_OVERDUE")


def _enum(name: str) -> postgresql.ENUM:
    values = next(values for enum_name, values in ENUMS if enum_name == name)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS:
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.create_table(
        "compliance_items",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("compliance_type", _enum("compliance_type"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("reference_number", sa.String(128), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("issuing_authority", sa.String(255), nullable=True),
        sa.Column("responsible_party", sa.String(255), nullable=True),
        sa.Column("responsible_phone", sa.String(32), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("insurer_name", sa.String(255), nullable=True),
        sa.Column("insurer_contact", sa.String(64), nullable=True),
        sa.Column("coverage_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("premium_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("premium_due_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_reminder_days", sa.Integer(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_items_organization_id", "compliance_items", ["organization_id"])
    op.create_index("ix_compliance_items_property_id", "compliance_items", ["property_id"])
    op.create_index("ix_compliance_items_expires_on", "compliance_items", ["expires_on"])

    op.create_table(
        "parking_bays",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("bay_number", sa.String(32), nullable=False),
        sa.Column("bay_type", _enum("bay_type"), nullable=False, server_default="OPEN"),
        sa.Column("level", sa.String(32), nullable=True),
        sa.Column("monthly_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "bay_number", name="uq_bay_number_per_property"),
    )
    op.create_index("ix_parking_bays_organization_id", "parking_bays", ["organization_id"])
    op.create_index("ix_parking_bays_property_id", "parking_bays", ["property_id"])

    op.create_table(
        "parking_allocations",
        sa.Column("bay_id", sa.UUID(), nullable=False),
        sa.Column("tenancy_id", sa.UUID(), nullable=True),
        sa.Column("guest_name", sa.String(255), nullable=True),
        sa.Column("guest_phone", sa.String(32), nullable=True),
        sa.Column("vehicle_registration", sa.String(32), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("monthly_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("bill_monthly", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bay_id"], ["parking_bays.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parking_allocations_organization_id", "parking_allocations", ["organization_id"])
    op.create_index("ix_parking_allocations_bay_id", "parking_allocations", ["bay_id"])
    op.create_index("ix_parking_allocations_tenancy_id", "parking_allocations", ["tenancy_id"])

    op.create_table(
        "amenities",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", _enum("amenity_kind"), nullable=False, server_default="OTHER"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("max_hours_per_booking", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("min_notice_hours", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_bookings_per_week", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("opens_at_hour", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("closes_at_hour", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("is_bookable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("booking_fee", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "name", name="uq_amenity_name_per_property"),
    )
    op.create_index("ix_amenities_organization_id", "amenities", ["organization_id"])
    op.create_index("ix_amenities_property_id", "amenities", ["property_id"])

    op.create_table(
        "amenity_bookings",
        sa.Column("amenity_id", sa.UUID(), nullable=False),
        sa.Column("tenancy_id", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _enum("booking_status"), nullable=False, server_default="CONFIRMED"),
        sa.Column("purpose", sa.String(255), nullable=True),
        sa.Column("guests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amenity_id"], ["amenities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_amenity_bookings_organization_id", "amenity_bookings", ["organization_id"])
    op.create_index("ix_amenity_bookings_amenity_id", "amenity_bookings", ["amenity_id"])
    op.create_index("ix_amenity_bookings_tenancy_id", "amenity_bookings", ["tenancy_id"])
    # The conflict check is always "this amenity, overlapping this window".
    op.create_index("ix_amenity_bookings_amenity_window", "amenity_bookings", ["amenity_id", "starts_at"])

    op.create_table(
        "utility_accounts",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("account_type", _enum("utility_account_type"), nullable=False),
        sa.Column("account_number", sa.String(64), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column(
            "payment_status",
            _enum("utility_payment_status"),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("last_paid_on", sa.Date(), nullable=True),
        sa.Column("last_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("next_due_on", sa.Date(), nullable=True),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_updated_by_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["status_updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "property_id", "account_type", "account_number", name="uq_utility_account_per_property"
        ),
    )
    op.create_index("ix_utility_accounts_organization_id", "utility_accounts", ["organization_id"])
    op.create_index("ix_utility_accounts_property_id", "utility_accounts", ["property_id"])
    op.create_index("ix_utility_accounts_next_due_on", "utility_accounts", ["next_due_on"])

    for statement in enable_table_statements(SPRINT_17_TABLES):
        op.execute(statement)

    for value in NEW_NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    for statement in disable_table_statements(SPRINT_17_TABLES):
        op.execute(statement)

    op.drop_table("utility_accounts")
    op.drop_table("amenity_bookings")
    op.drop_table("amenities")
    op.drop_table("parking_allocations")
    op.drop_table("parking_bays")
    op.drop_table("compliance_items")

    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
