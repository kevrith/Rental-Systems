"""subscription billing

RentFlow's own billing (Sprint 27, US-113): one subscription per organisation
and the invoices it raises against a saved Paystack card. Enum labels are the
uppercase member *names*, matching how SQLAlchemy binds `(str, enum.Enum)`
members everywhere else in this codebase.

`subscription_plan` already exists as a type — the organisations table has used
it since Phase 1 — so it is reused rather than recreated.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import PHASE_13_ORG_SCOPED_TABLES, disable_table_statements, enable_table_statements

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("subscription_lapsed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Created explicitly, then referenced with `create_type=False` below:
    # letting `create_table` create them implicitly as well would issue a second
    # CREATE TYPE for the same name and fail.
    bind = op.get_bind()
    postgresql.ENUM("MONTHLY", "ANNUAL", name="billing_interval").create(bind, checkfirst=True)
    postgresql.ENUM("ACTIVE", "PAST_DUE", "LAPSED", "CANCELLED", name="subscription_status").create(
        bind, checkfirst=True
    )
    postgresql.ENUM("PENDING", "PAID", "FAILED", name="subscription_invoice_status").create(
        bind, checkfirst=True
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column(
            "plan",
            postgresql.ENUM(name="subscription_plan", create_type=False),
            nullable=False,
        ),
        sa.Column("interval", postgresql.ENUM(name="billing_interval", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="subscription_status", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_period_start", sa.Date(), nullable=False),
        sa.Column("current_period_end", sa.Date(), nullable=False),
        sa.Column("next_billing_date", sa.Date(), nullable=False),
        sa.Column("paystack_authorization_code", sa.String(length=128), nullable=True),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("card_brand", sa.String(length=32), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grace_ends_at", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        # One subscription per organisation: two would mean two answers to
        # "what does this account pay", and the biller would charge both.
        sa.UniqueConstraint("organization_id", name="uq_subscription_per_org"),
    )
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_next_billing_date", "subscriptions", ["next_billing_date"])

    op.create_table(
        "subscription_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
        sa.Column("reference_code", sa.String(length=32), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="subscription_invoice_status", create_type=False),
            nullable=False,
        ),
        sa.Column("paystack_reference", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_subscription_invoices_organization_id", "subscription_invoices", ["organization_id"])
    op.create_index("ix_subscription_invoices_subscription_id", "subscription_invoices", ["subscription_id"])
    op.create_index("ix_subscription_invoices_reference_code", "subscription_invoices", ["reference_code"])
    op.create_index("ix_subscription_invoices_status", "subscription_invoices", ["status"])
    op.create_index(
        "ix_subscription_invoices_paystack_reference",
        "subscription_invoices",
        ["paystack_reference"],
        unique=True,
    )

    for statement in enable_table_statements(PHASE_13_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(PHASE_13_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("subscription_invoices")
    op.drop_table("subscriptions")

    for name in ("subscription_invoice_status", "subscription_status", "billing_interval"):
        op.execute(f"DROP TYPE IF EXISTS {name}")

    op.drop_column("organizations", "subscription_lapsed_at")
