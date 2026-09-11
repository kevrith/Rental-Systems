"""merge walk-in hirers and saved signatures branches

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4, b9c0d1e2f3a4
Create Date: 2026-01-02 00:00:00.000000

"""

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: tuple[str, str] = ("e9f0a1b2c3d4", "b9c0d1e2f3a4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
