"""caretaker sign-in PIN

Revision ID: 78d3dba53bbd
Revises: f0a1b2c3d4e5
Create Date: 2026-11-28 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str = "78d3dba53bbd"
down_revision: str = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pin_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "pin_hash")
