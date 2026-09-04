"""row level security policies for the phase 2 agency tables

The first RLS migration ran before `owner_profiles`, `disbursements`,
`inspection_reports` and `digital_signatures` existed, so those four tables were
created without policies — application-layer scoping was the only thing standing
between one agency's owner clients and another's. This closes that gap.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-03

"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import (
    PHASE_2_ORG_SCOPED_TABLES,
    disable_table_statements,
    enable_table_statements,
)

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for statement in enable_table_statements(PHASE_2_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(PHASE_2_ORG_SCOPED_TABLES):
        op.execute(statement)
