"""vacancy listings, the lead pipeline and data exports

Sprint 16. A listing carries its own opaque slug rather than reusing the unit id:
the link is meant to be pasted into WhatsApp groups, and an over-shared one has to
be rotatable without touching the unit it advertises.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SPRINT_16_TABLES = ("vacancy_listings", "inquiries", "data_exports")

ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("listing_status", ("DRAFT", "PUBLISHED", "CLOSED")),
    (
        "lead_stage",
        ("INQUIRED", "APPLIED", "UNDER_REVIEW", "APPROVED", "REJECTED", "LOST"),
    ),
    ("export_format", ("CSV", "EXCEL")),
    (
        "export_kind",
        ("TENANTS", "TENANCIES", "PAYMENTS", "PROPERTIES", "UNITS", "INVOICES"),
    ),
)

NEW_NOTIFICATION_TYPES = ("INQUIRY_RECEIVED", "EXPORT_READY")


def _enum(name: str) -> postgresql.ENUM:
    values = next(values for enum_name, values in ENUMS if enum_name == name)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS:
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.create_table(
        "vacancy_listings",
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("headline", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        sa.Column("status", _enum("listing_status"), nullable=False, server_default="PUBLISHED"),
        sa.Column("vacant_since", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_vacancy_listings_organization_id", "vacancy_listings", ["organization_id"])
    op.create_index("ix_vacancy_listings_slug", "vacancy_listings", ["slug"])
    op.create_index("ix_vacancy_listings_status", "vacancy_listings", ["status"])

    op.create_table(
        "inquiries",
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("stage", _enum("lead_stage"), nullable=False, server_default="INQUIRED"),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["vacancy_listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["tenant_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inquiries_organization_id", "inquiries", ["organization_id"])
    op.create_index("ix_inquiries_listing_id", "inquiries", ["listing_id"])
    op.create_index("ix_inquiries_unit_id", "inquiries", ["unit_id"])
    op.create_index("ix_inquiries_phone_number", "inquiries", ["phone_number"])
    op.create_index("ix_inquiries_stage", "inquiries", ["stage"])

    op.create_table(
        "data_exports",
        sa.Column("kind", _enum("export_kind"), nullable=False),
        sa.Column("export_format", _enum("export_format"), nullable=False, server_default="CSV"),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("is_scheduled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_exports_organization_id", "data_exports", ["organization_id"])

    for statement in enable_table_statements(SPRINT_16_TABLES):
        op.execute(statement)

    for value in NEW_NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    for statement in disable_table_statements(SPRINT_16_TABLES):
        op.execute(statement)

    op.drop_table("data_exports")
    op.drop_table("inquiries")
    op.drop_table("vacancy_listings")

    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
