"""saved_signature on users and tenants

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-09-11 19:06:00.000000

Adds a `saved_signature` column (nullable Text, base64 PNG data URL) to both
`users` and `tenants` so that owners/managers and tenants can draw their
signature once and have it automatically pre-filled in every document signing
flow thereafter.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("saved_signature", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("saved_signature", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "saved_signature")
    op.drop_column("users", "saved_signature")
