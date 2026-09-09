"""daily auto disbursement

Per-owner opt-in to being settled the morning after rent clears, instead of once
a month on `disbursement_day`. Off by default because it is the only path that
moves an owner's money with no per-payout approval.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owner_profiles",
        sa.Column(
            "auto_disburse_daily",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "owner_profiles",
        sa.Column(
            "auto_disburse_minimum",
            sa.Numeric(12, 2),
            server_default=sa.text("1000.00"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_owner_profiles_auto_disburse_daily",
        "owner_profiles",
        ["auto_disburse_daily"],
    )


def downgrade() -> None:
    op.drop_index("ix_owner_profiles_auto_disburse_daily", table_name="owner_profiles")
    op.drop_column("owner_profiles", "auto_disburse_minimum")
    op.drop_column("owner_profiles", "auto_disburse_daily")
