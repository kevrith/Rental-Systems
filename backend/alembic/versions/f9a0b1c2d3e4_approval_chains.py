"""configurable approval chains

Sprint 26A, item 13: `approval_rules`, `approval_requests`, `approval_actions`
— see `app/models/approval.py` for the shape and why the two existing
bespoke maker-checker flows (cash payments, maintenance cost) are not
migrated onto this in the same change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import PHASE_12_ORG_SCOPED_TABLES, disable_table_statements, enable_table_statements

revision: str = "f9a0b1c2d3e4"
down_revision: str | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("threshold", sa.Numeric(14, 2), nullable=True),
        sa.Column("required_approver_roles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_approval_rules_organization_id", "approval_rules", ["organization_id"])
    op.create_index("ix_approval_rules_entity_type", "approval_rules", ["entity_type"])

    # Created implicitly by `op.create_table` below, the first time this type
    # object is used as a column type — same as every other new enum type in
    # this history. Calling `.create()` here too would double-create it.
    approval_request_status = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", "CANCELLED", name="approval_request_status"
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_name", sa.String(length=255), nullable=True),
        sa.Column("trigger_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("required_approver_roles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", approval_request_status, nullable=False, server_default="PENDING"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["approval_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_approval_requests_organization_id", "approval_requests", ["organization_id"])
    op.create_index("ix_approval_requests_entity_type", "approval_requests", ["entity_type"])
    op.create_index("ix_approval_requests_entity_id", "approval_requests", ["entity_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    approval_action_type = postgresql.ENUM("APPROVE", "REJECT", name="approval_action_type")

    op.create_table(
        "approval_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("action", approval_action_type, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["approval_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_approval_actions_organization_id", "approval_actions", ["organization_id"])
    op.create_index("ix_approval_actions_request_id", "approval_actions", ["request_id"])

    for statement in enable_table_statements(PHASE_12_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(PHASE_12_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_index("ix_approval_actions_request_id", table_name="approval_actions")
    op.drop_index("ix_approval_actions_organization_id", table_name="approval_actions")
    op.drop_table("approval_actions")
    op.execute("DROP TYPE IF EXISTS approval_action_type")

    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_entity_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_entity_type", table_name="approval_requests")
    op.drop_index("ix_approval_requests_organization_id", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.execute("DROP TYPE IF EXISTS approval_request_status")

    op.drop_index("ix_approval_rules_entity_type", table_name="approval_rules")
    op.drop_index("ix_approval_rules_organization_id", table_name="approval_rules")
    op.drop_table("approval_rules")
