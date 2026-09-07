"""hash-chained audit log

Sprint 26A, item 8 of the enterprise-readiness pass: `audit_logs.prev_hash`
and `.entry_hash`, filled in after the fact by the scheduled
`rentflow.chain_audit_log_entries` task — see
`app/services/audit_chain_service.py` for why this is not computed at write
time. Both nullable and additive: every existing row is simply unchained
until the scheduled task catches up, which it does on its own.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("prev_hash", sa.String(length=32), nullable=True))
    op.add_column("audit_logs", sa.Column("entry_hash", sa.String(length=32), nullable=True))
    op.create_index("ix_audit_logs_entry_hash", "audit_logs", ["entry_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entry_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "entry_hash")
    op.drop_column("audit_logs", "prev_hash")
