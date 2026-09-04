"""document vault: tags, descriptions and the vault file categories

Adds the free-form `tags` and `description` a vault needs to stay searchable, and
the five categories Phase 2 files into it — title deeds, insurance and compliance
certificates, demand letters and renewal agreements.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_CATEGORIES = (
    "TITLE_DEED",
    "INSURANCE_CERTIFICATE",
    "COMPLIANCE_CERTIFICATE",
    "DEMAND_LETTER",
    "RENEWAL_AGREEMENT",
)


def upgrade() -> None:
    op.add_column(
        "stored_files",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("stored_files", sa.Column("description", sa.Text(), nullable=True))

    # `ALTER TYPE ... ADD VALUE` needs its own transaction on some Postgres
    # versions; Alembic runs each migration in one, so commit before adding.
    op.execute("COMMIT")
    for label in NEW_CATEGORIES:
        op.execute(f"ALTER TYPE file_category ADD VALUE IF NOT EXISTS '{label}'")


def downgrade() -> None:
    # Postgres cannot drop an enum value, so fold anything using a new category
    # back onto OTHER and rebuild the type without them.
    op.execute(
        "UPDATE stored_files SET category = 'OTHER' WHERE category::text IN ("
        + ", ".join(f"'{label}'" for label in NEW_CATEGORIES)
        + ")"
    )
    op.execute("ALTER TYPE file_category RENAME TO file_category_old")
    op.execute(
        "CREATE TYPE file_category AS ENUM ("
        "'PROPERTY_PHOTO', 'UNIT_PHOTO', 'TENANT_ID', 'TENANT_PASSPORT_PHOTO', 'LEASE', "
        "'RECEIPT', 'INVOICE', 'METER_READING', 'MAINTENANCE', 'NOTICE', 'ORG_LOGO', "
        "'PROFILE_PHOTO', 'OTHER', 'INSPECTION_PHOTO', 'INSPECTION_REPORT', "
        "'OWNER_STATEMENT', 'SIGNED_DOCUMENT', 'SIGNATURE_IMAGE')"
    )
    op.execute("ALTER TABLE stored_files ALTER COLUMN category DROP DEFAULT")
    op.execute(
        "ALTER TABLE stored_files ALTER COLUMN category "
        "TYPE file_category USING category::text::file_category"
    )
    op.execute("ALTER TABLE stored_files ALTER COLUMN category SET DEFAULT 'OTHER'")
    op.execute("DROP TYPE file_category_old")

    op.drop_column("stored_files", "description")
    op.drop_column("stored_files", "tags")
