"""google sign-in

`users.google_sub` — Google's stable per-account "sub" claim, set when an
account is created or linked via Sign in with Google. Nullable and unique:
most users never touch it, and no two users may ever claim the same Google
account.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "321b29763079"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
