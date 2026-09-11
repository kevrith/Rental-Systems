"""walk-in hirers on rental agreements

Revision ID: e9f0a1b2c3d4
Revises: a3b4c5d6e7f8
Create Date: 2026-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "e9f0a1b2c3d4"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make tenant_id nullable — existing rows keep their FK, walk-ins have NULL.
    op.alter_column("rental_agreements", "tenant_id", nullable=True)
    op.drop_constraint("rental_agreements_tenant_id_fkey", "rental_agreements", type_="foreignkey")
    op.create_foreign_key(
        "rental_agreements_tenant_id_fkey",
        "rental_agreements",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("rental_agreements", sa.Column("hirer_name", sa.String(255), nullable=True))
    op.add_column("rental_agreements", sa.Column("hirer_phone", sa.String(32), nullable=True))
    op.add_column("rental_agreements", sa.Column("hirer_id_number", sa.String(64), nullable=True))

    # Back-fill hirer_name/phone from the linked tenant for existing rows.
    op.execute(
        """
        UPDATE rental_agreements ra
        SET hirer_name  = t.full_name,
            hirer_phone = t.phone_number
        FROM tenants t
        WHERE ra.tenant_id = t.id
          AND ra.hirer_name IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("rental_agreements", "hirer_id_number")
    op.drop_column("rental_agreements", "hirer_phone")
    op.drop_column("rental_agreements", "hirer_name")

    op.drop_constraint("rental_agreements_tenant_id_fkey", "rental_agreements", type_="foreignkey")
    op.create_foreign_key(
        "rental_agreements_tenant_id_fkey",
        "rental_agreements",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("rental_agreements", "tenant_id", nullable=False)
