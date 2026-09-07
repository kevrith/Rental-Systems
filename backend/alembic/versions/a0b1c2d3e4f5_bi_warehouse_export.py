"""BI/warehouse export

Sprint 26A, item 14: `export_format` gains a `PARQUET` label (Postgres
cannot drop an enum value, so — same as every other enum extension in this
history — this only ever adds one), and `organizations.bi_export_enabled`
opts an organisation into the scheduled Parquet drop
(`app/services/export_service.run_bi_exports`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "f9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE export_format ADD VALUE IF NOT EXISTS 'PARQUET'")
    op.add_column(
        "organizations",
        sa.Column("bi_export_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("organizations", "bi_export_enabled")
    # `export_format`'s new PARQUET label is not removed — Postgres cannot
    # drop an enum value, same as every other enum extension in this history.
