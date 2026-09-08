"""document vault storage limit

`organizations.storage_limit_bytes` — nullable; null means "use the plan
default" (see `app/services/vault_service.PLAN_STORAGE_LIMITS_GB`). This
column only ever holds Enterprise's negotiated custom figure, set by
platform staff via `PATCH /internal/organizations/{id}/plan` — never
exposed on the customer-facing organization settings update.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("storage_limit_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "storage_limit_bytes")
