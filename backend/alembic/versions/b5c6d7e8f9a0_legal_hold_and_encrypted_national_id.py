"""legal hold and encrypted national ID

Sprint 26A: two of the items from the enterprise-readiness pass.

  * `legal_holds` — an explicit, entity-scoped override that suspends both the
    retention sweep (`retention_service.py`) and tenant-initiated erasure
    (`privacy_service.py`) for whatever it names. See
    `docs/legal/data-retention-policy.md` for the policy this backs.
  * `tenants.national_id_encrypted` / `_blind_index` / `_last4` — the first
    field-level-encrypted PII column, per-organization (`app/core/crypto.py`,
    `encrypt_for_org`). Additive only: the old plaintext `national_id` column
    is left in place, unmapped, so existing data is not lost and a backfill
    (`scripts/backfill_national_id_encryption.py`) can run before it is
    dropped in a later, separate migration. Until that backfill runs, a
    tenant's existing plaintext `national_id` is simply invisible to the
    application — it is not read from anywhere any more.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import PHASE_10_ORG_SCOPED_TABLES, disable_table_statements, enable_table_statements

revision: str = "b5c6d7e8f9a0"
down_revision: str | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legal_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("placed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("placed_by_name", sa.String(length=255), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("released_by_name", sa.String(length=255), nullable=True),
        sa.Column("release_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["placed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["released_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_legal_holds_organization_id", "legal_holds", ["organization_id"])
    op.create_index("ix_legal_holds_entity_id", "legal_holds", ["entity_id"])
    op.create_index("ix_legal_holds_entity", "legal_holds", ["entity_type", "entity_id"])

    for statement in enable_table_statements(PHASE_10_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.add_column("tenants", sa.Column("national_id_encrypted", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("national_id_blind_index", sa.String(length=64), nullable=True))
    op.add_column("tenants", sa.Column("national_id_last4", sa.String(length=4), nullable=True))
    op.create_index("ix_tenants_national_id_blind_index", "tenants", ["national_id_blind_index"])
    # `tenants.national_id` (the old plaintext column) and its index are
    # deliberately left in place — see the module docstring.


def downgrade() -> None:
    op.drop_index("ix_tenants_national_id_blind_index", table_name="tenants")
    op.drop_column("tenants", "national_id_last4")
    op.drop_column("tenants", "national_id_blind_index")
    op.drop_column("tenants", "national_id_encrypted")

    for statement in disable_table_statements(PHASE_10_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_index("ix_legal_holds_entity", table_name="legal_holds")
    op.drop_index("ix_legal_holds_entity_id", table_name="legal_holds")
    op.drop_index("ix_legal_holds_organization_id", table_name="legal_holds")
    op.drop_table("legal_holds")
