"""add invite_link to invitations

Revision ID: 75ec8623e8cf
Revises: e6f7a8b9c0d1
Create Date: 2026-09-11 13:23:44.621074

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "75ec8623e8cf"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invitations", sa.Column("invite_link", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("invitations", "invite_link")
