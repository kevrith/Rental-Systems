"""disbursement approval workflow and M-Pesa B2C payout correlation

Adds the two review states an agency admin moves a payout through before any
money leaves (APPROVED / REJECTED), the columns recording who reviewed it, and
the Daraja B2C conversation ids the result callback arrives with.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Postgres cannot drop a value from an enum, and `ALTER TYPE ... ADD VALUE` is
# not reversible, so both directions rebuild the type from scratch.
OLD_STATUSES = ("PENDING", "PROCESSING", "COMPLETED", "FAILED")
NEW_STATUSES = ("PENDING", "APPROVED", "REJECTED", "PROCESSING", "COMPLETED", "FAILED")


def _retype_status(labels: Sequence[str]) -> None:
    op.execute("ALTER TYPE disbursement_status RENAME TO disbursement_status_old")
    op.execute(
        "CREATE TYPE disbursement_status AS ENUM (" + ", ".join(f"'{label}'" for label in labels) + ")"
    )
    op.execute("ALTER TABLE disbursements ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE disbursements ALTER COLUMN status "
        "TYPE disbursement_status USING status::text::disbursement_status"
    )
    op.execute("ALTER TABLE disbursements ALTER COLUMN status SET DEFAULT 'PENDING'")
    op.execute("DROP TYPE disbursement_status_old")


def upgrade() -> None:
    _retype_status(NEW_STATUSES)

    op.add_column("disbursements", sa.Column("approved_by_id", sa.UUID(), nullable=True))
    op.add_column("disbursements", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("disbursements", sa.Column("rejection_reason", sa.String(512), nullable=True))
    op.add_column("disbursements", sa.Column("payout_conversation_id", sa.String(128), nullable=True))
    op.add_column("disbursements", sa.Column("payout_originator_id", sa.String(128), nullable=True))
    op.add_column(
        "disbursements", sa.Column("payout_requested_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_foreign_key(
        "fk_disbursements_approved_by_id_users",
        "disbursements",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_disbursements_payout_conversation_id", "disbursements", ["payout_conversation_id"])
    op.create_index("ix_disbursements_payout_originator_id", "disbursements", ["payout_originator_id"])


def downgrade() -> None:
    op.drop_index("ix_disbursements_payout_originator_id", table_name="disbursements")
    op.drop_index("ix_disbursements_payout_conversation_id", table_name="disbursements")
    op.drop_constraint("fk_disbursements_approved_by_id_users", "disbursements", type_="foreignkey")

    op.drop_column("disbursements", "payout_requested_at")
    op.drop_column("disbursements", "payout_originator_id")
    op.drop_column("disbursements", "payout_conversation_id")
    op.drop_column("disbursements", "rejection_reason")
    op.drop_column("disbursements", "approved_at")
    op.drop_column("disbursements", "approved_by_id")

    # Fold the states the old enum has no room for back onto ones it does.
    op.execute("UPDATE disbursements SET status = 'PENDING' WHERE status = 'APPROVED'")
    op.execute("UPDATE disbursements SET status = 'FAILED' WHERE status = 'REJECTED'")
    _retype_status(OLD_STATUSES)
