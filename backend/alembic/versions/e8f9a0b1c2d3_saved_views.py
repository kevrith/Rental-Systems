"""saved views

Sprint 26A, item 11: `saved_views` — a named, reusable filter set for one
list screen. See `app/models/saved_view.py` for the shape; RLS is enabled
the same way every other organisation-scoped table gets it
(`PHASE_11_ORG_SCOPED_TABLES` in `app.core.rls`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import PHASE_11_ORG_SCOPED_TABLES, disable_table_statements, enable_table_statements

revision: str = "e8f9a0b1c2d3"
down_revision: str | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "entity_type", "name", name="uq_saved_view_user_entity_name"),
    )
    op.create_index("ix_saved_views_organization_id", "saved_views", ["organization_id"])
    op.create_index("ix_saved_views_user_id", "saved_views", ["user_id"])
    op.create_index("ix_saved_views_entity_type", "saved_views", ["entity_type"])

    for statement in enable_table_statements(PHASE_11_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(PHASE_11_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_index("ix_saved_views_entity_type", table_name="saved_views")
    op.drop_index("ix_saved_views_user_id", table_name="saved_views")
    op.drop_index("ix_saved_views_organization_id", table_name="saved_views")
    op.drop_table("saved_views")
