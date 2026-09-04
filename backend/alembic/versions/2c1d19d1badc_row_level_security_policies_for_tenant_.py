"""row level security policies for tenant tables

Defence in depth behind the application's `organization_id` scoping. Every
tenant-owned table gets a policy comparing its `organization_id` against the
per-transaction setting `app.current_org_id`, which `app.core.rls` sets.

Two deliberate choices:

* Policies carry a `WITH CHECK` matching their `USING` clause, so a row can
  neither be read from nor written into another tenant.
* With `app.current_org_id` unset, the policy matches nothing rather than
  everything. A forgotten context is then a visible failure (empty results),
  never a silent cross-tenant leak.

The table owner bypasses RLS, which is what lets Celery tasks and the M-Pesa
callback work across organizations. Grant day-to-day access to a separate,
non-owner role to make the policies bite in production.

The DDL itself lives in `app.core.rls` so this migration and the test database
build identical policies.

Revision ID: 2c1d19d1badc
Revises: becdc2a16b45
Create Date: 2026-09-03

"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import PHASE_1_ORG_SCOPED_TABLES, disable_statements, enable_statements

revision: str = "2c1d19d1badc"
down_revision: str | None = "becdc2a16b45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for statement in enable_statements(PHASE_1_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_statements(PHASE_1_ORG_SCOPED_TABLES):
        op.execute(statement)
