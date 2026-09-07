"""email suppression and bounce/complaint delivery statuses

Sprint 26A, item 16 of the enterprise-readiness pass: `email_suppressions`
(platform-level — see `PHASE_10_ORG_SCOPED_TABLES`'s note in `app.core.rls`
for why this table is deliberately not organisation-scoped), and two new
`delivery_status` labels (`BOUNCED`, `COMPLAINED`) that Resend's webhook
(`app.services.email_service`) sets on the `Notification` row a bounce or
complaint was about. Postgres cannot drop an enum value, so — same as every
other enum extension in this history — this only ever adds labels.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "c6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE delivery_status ADD VALUE IF NOT EXISTS 'BOUNCED'")
    op.execute("ALTER TYPE delivery_status ADD VALUE IF NOT EXISTS 'COMPLAINED'")

    op.create_table(
        "email_suppressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "reason",
            postgresql.ENUM("BOUNCED", "COMPLAINED", "MANUAL", name="email_suppression_reason"),
            nullable=False,
        ),
        sa.Column("detail", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_email_suppressions_email", "email_suppressions", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_email_suppressions_email", table_name="email_suppressions")
    op.drop_table("email_suppressions")
    op.execute("DROP TYPE IF EXISTS email_suppression_reason")
    # `delivery_status`'s new labels (BOUNCED, COMPLAINED) are not removed —
    # Postgres cannot drop an enum value, same as every other enum extension
    # in this history.
