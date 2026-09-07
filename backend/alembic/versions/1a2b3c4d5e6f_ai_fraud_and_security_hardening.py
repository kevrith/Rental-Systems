"""AI lease analysis, fraud detection and security hardening

Sprint 22 (Phase 4): AI lease document intelligence (US-096), fraud pattern
detection (US-097) and enterprise security hardening (US-098).

`lease_analyses`/`lease_suggestions` hold one Claude review per request and
its individual findings, each accepted or dismissed on its own. `fraud_alerts`
is one flagged pattern on one payment event; `fraud_suppressions` is an
owner's standing "this is legitimate" decision keyed by the same
`pattern_key`, so a suppressed pattern never re-alerts. `security_events` is
the durable record of authentication noise (a failed password, a login
blocked by the IP whitelist) that `AuditLog` never captured, feeding the
daily failed-login digest.

Also extends `organizations` with the IP whitelist, per-role session timeout
policy and fraud detection thresholds (all configured from Settings ->
Security), and `api_keys` with `rotation_reminder_sent_at`.

Every enum label below is the Python enum member's *name*, not its lowercase
`.value` — see the Sprint 20 migration's docstring for why that distinction
matters here.

Revision ID: 1a2b3c4d5e6f
Revises: 0b6a961c2b8d
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "1a2b3c4d5e6f"
down_revision: str | None = "0b6a961c2b8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ORG_SCOPED_TABLES = (
    "lease_analyses",
    "lease_suggestions",
    "security_events",
    "fraud_alerts",
    "fraud_suppressions",
)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'LEASE_ANALYSIS_READY'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'FRAUD_ALERT'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'SECURITY_LOGIN_BLOCKED'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'FAILED_LOGIN_DIGEST'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'API_KEY_ROTATION_DUE'")

    # --- organizations: IP whitelist, per-role session policy, fraud thresholds ---
    op.add_column(
        "organizations",
        sa.Column("ip_whitelist", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "organizations",
        sa.Column("role_session_timeouts", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "organizations",
        sa.Column("fraud_max_cash_payments_per_window", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "organizations",
        sa.Column("fraud_cash_window_minutes", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "fraud_unusual_amount_multiplier",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="3.00",
        ),
    )

    # --- api_keys: rotation reminder tracking ---
    op.add_column(
        "api_keys", sa.Column("rotation_reminder_sent_at", sa.DateTime(timezone=True), nullable=True)
    )

    # --- lease_analyses / lease_suggestions (US-096) ---
    op.create_table(
        "lease_analyses",
        sa.Column("lease_template_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lease_template_id"], ["lease_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lease_analyses_organization_id", "lease_analyses", ["organization_id"])
    op.create_index("ix_lease_analyses_lease_template_id", "lease_analyses", ["lease_template_id"])

    lease_suggestion_category = postgresql.ENUM(
        "MISSING_CLAUSE", "PROBLEMATIC_TERM", "UNCLEAR_LANGUAGE", name="lease_suggestion_category"
    )
    lease_suggestion_status = postgresql.ENUM(
        "PENDING", "ACCEPTED", "DISMISSED", name="lease_suggestion_status"
    )
    op.create_table(
        "lease_suggestions",
        sa.Column("lease_analysis_id", sa.UUID(), nullable=False),
        sa.Column("category", lease_suggestion_category, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("issue", sa.Text(), nullable=False),
        sa.Column("suggested_text", sa.Text(), nullable=True),
        sa.Column("status", lease_suggestion_status, nullable=False, server_default="PENDING"),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lease_analysis_id"], ["lease_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lease_suggestions_organization_id", "lease_suggestions", ["organization_id"])
    op.create_index("ix_lease_suggestions_lease_analysis_id", "lease_suggestions", ["lease_analysis_id"])
    op.create_index("ix_lease_suggestions_status", "lease_suggestions", ["status"])

    # --- security_events (US-098) ---
    security_event_type = postgresql.ENUM("LOGIN_FAILED", "LOGIN_BLOCKED_IP", name="security_event_type")
    op.create_table(
        "security_events",
        sa.Column("event_type", security_event_type, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_events_organization_id", "security_events", ["organization_id"])
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_user_id", "security_events", ["user_id"])

    # --- fraud_alerts / fraud_suppressions (US-097) ---
    fraud_alert_type = postgresql.ENUM(
        "RAPID_CASH_PAYMENTS",
        "OFF_HOURS_ACTIVITY",
        "UNUSUAL_AMOUNT",
        "VELOCITY_DUPLICATE",
        name="fraud_alert_type",
    )
    fraud_alert_status = postgresql.ENUM("OPEN", "SUPPRESSED", "RESOLVED", name="fraud_alert_status")
    op.create_table(
        "fraud_alerts",
        sa.Column("alert_type", fraud_alert_type, nullable=False),
        sa.Column("pattern_key", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", fraud_alert_status, nullable=False, server_default="OPEN"),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fraud_alerts_organization_id", "fraud_alerts", ["organization_id"])
    op.create_index("ix_fraud_alerts_alert_type", "fraud_alerts", ["alert_type"])
    op.create_index("ix_fraud_alerts_pattern_key", "fraud_alerts", ["pattern_key"])
    op.create_index("ix_fraud_alerts_status", "fraud_alerts", ["status"])

    op.create_table(
        "fraud_suppressions",
        sa.Column("pattern_key", sa.String(255), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "pattern_key", name="uq_fraud_suppression_org_pattern"),
    )
    op.create_index("ix_fraud_suppressions_organization_id", "fraud_suppressions", ["organization_id"])

    for statement in enable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("fraud_suppressions")
    op.drop_table("fraud_alerts")
    op.execute("DROP TYPE IF EXISTS fraud_alert_status")
    op.execute("DROP TYPE IF EXISTS fraud_alert_type")

    op.drop_table("security_events")
    op.execute("DROP TYPE IF EXISTS security_event_type")

    op.drop_table("lease_suggestions")
    op.execute("DROP TYPE IF EXISTS lease_suggestion_status")
    op.execute("DROP TYPE IF EXISTS lease_suggestion_category")
    op.drop_table("lease_analyses")

    op.drop_column("api_keys", "rotation_reminder_sent_at")

    op.drop_column("organizations", "fraud_unusual_amount_multiplier")
    op.drop_column("organizations", "fraud_cash_window_minutes")
    op.drop_column("organizations", "fraud_max_cash_payments_per_window")
    op.drop_column("organizations", "role_session_timeouts")
    op.drop_column("organizations", "ip_whitelist")
