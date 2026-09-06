"""customer success platform

Sprint 20 (Phase 4): onboarding (US-089), contextual help (US-090), weekly
customer health scoring with at-risk alerts (US-091), referrals, NPS,
milestones, the feature-voting board and the in-app changelog (US-092).

`help_articles`, `feature_requests`, `feature_votes` and `changelog_entries`
carry no `organization_id` — they are the same content for every tenant, the
same treatment `task_runs` already gets, so they are excluded from the RLS
policy set. Everything else here is scoped to one organisation.

Also adds `users.is_platform_staff` (RentFlow's own team, not a tenant role —
gates the new cross-organization `/internal` surface) and
`organizations.credit_months` (the referral-credit ledger).

Every Postgres enum label below is the Python enum member's *name*
(`PENDING`, `SIGNED_UP`, ...), not its lowercase `.value` — SQLAlchemy's
`Enum` type binds a `(str, Enum)` member via `.name` by default, so the
stored labels have to match that or every insert/query against the column
fails with "invalid input value for enum". (The Sprint 19 migration got
this wrong for `webhook_delivery_status`; fixed alongside this one.)

Revision ID: e2f3a4b5c6d7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ORG_SCOPED_TABLES = (
    "onboarding_progress",
    "organization_health_scores",
    "customer_success_alerts",
    "referral_codes",
    "referrals",
    "support_requests",
    "nps_survey_prompts",
    "milestone_events",
)


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_platform_staff", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "organizations", sa.Column("credit_months", sa.Integer(), nullable=False, server_default="0")
    )

    # --- onboarding_progress (US-089) ---
    op.create_table(
        "onboarding_progress",
        sa.Column("added_property", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_units", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("invited_caretaker", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_tenant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("setup_payment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_onboarding_progress_organization"),
    )
    op.create_index("ix_onboarding_progress_organization_id", "onboarding_progress", ["organization_id"])

    # --- help_articles (US-090) — platform-wide, no organization_id ---
    op.create_table(
        "help_articles",
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_help_articles_slug"),
    )
    op.create_index("ix_help_articles_slug", "help_articles", ["slug"], unique=True)
    op.create_index("ix_help_articles_is_published", "help_articles", ["is_published"])

    # --- organization_health_scores (US-091) ---
    trend = postgresql.ENUM("IMPROVING", "DECLINING", "STABLE", name="health_trend")
    op.create_table(
        "organization_health_scores",
        sa.Column("week_of", sa.Date(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("login_score", sa.Integer(), nullable=False),
        sa.Column("payment_score", sa.Integer(), nullable=False),
        sa.Column("adoption_score", sa.Integer(), nullable=False),
        sa.Column("caretaker_score", sa.Integer(), nullable=False),
        sa.Column("portal_score", sa.Integer(), nullable=False),
        sa.Column("support_score", sa.Integer(), nullable=False),
        sa.Column("trend", trend, nullable=False, server_default="STABLE"),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "week_of", name="uq_health_score_organization_week"),
    )
    op.create_index(
        "ix_organization_health_scores_organization_id", "organization_health_scores", ["organization_id"]
    )
    op.create_index("ix_organization_health_scores_week_of", "organization_health_scores", ["week_of"])

    # --- customer_success_alerts (US-091) ---
    op.create_table(
        "customer_success_alerts",
        sa.Column("health_score_id", sa.UUID(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["health_score_id"], ["organization_health_scores.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_success_alerts_organization_id", "customer_success_alerts", ["organization_id"]
    )

    # --- referral_codes / referrals (US-092) ---
    op.create_table(
        "referral_codes",
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_referral_codes_code"),
        sa.UniqueConstraint("organization_id", name="uq_referral_code_organization"),
    )
    op.create_index("ix_referral_codes_organization_id", "referral_codes", ["organization_id"])
    op.create_index("ix_referral_codes_code", "referral_codes", ["code"], unique=True)

    referral_status = postgresql.ENUM("PENDING", "SIGNED_UP", "CONVERTED", name="referral_status")
    op.create_table(
        "referrals",
        sa.Column("referral_code_id", sa.UUID(), nullable=False),
        sa.Column("referred_email", sa.String(255), nullable=False),
        sa.Column("referred_organization_id", sa.UUID(), nullable=True),
        sa.Column("status", referral_status, nullable=False, server_default="PENDING"),
        sa.Column("credit_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referral_code_id"], ["referral_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referrals_organization_id", "referrals", ["organization_id"])
    op.create_index("ix_referrals_referred_email", "referrals", ["referred_email"])

    # --- support_requests (US-090) ---
    support_status = postgresql.ENUM("OPEN", "RESOLVED", name="support_request_status")
    op.create_table(
        "support_requests",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", support_status, nullable=False, server_default="OPEN"),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_requests_organization_id", "support_requests", ["organization_id"])

    # --- nps_survey_prompts (US-092) ---
    nps_trigger = postgresql.ENUM("FIRST_PAYMENT", "FIRST_INSPECTION", "FIRST_MONTH", name="nps_trigger")
    op.create_table(
        "nps_survey_prompts",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("trigger_event", nps_trigger, nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", "trigger_event", name="uq_nps_prompt_user_trigger"),
    )
    op.create_index("ix_nps_survey_prompts_organization_id", "nps_survey_prompts", ["organization_id"])

    # --- milestone_events (US-092) ---
    milestone_key = postgresql.ENUM("PAYMENTS_100", "TENANTS_50", "FIRST_ETIMS_RECEIPT", name="milestone_key")
    op.create_table(
        "milestone_events",
        sa.Column("milestone_key", milestone_key, nullable=False),
        sa.Column("reached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "milestone_key", name="uq_milestone_organization_key"),
    )
    op.create_index("ix_milestone_events_organization_id", "milestone_events", ["organization_id"])

    # --- feature_requests / feature_votes (US-092) — platform-wide ---
    feature_status = postgresql.ENUM("OPEN", "PLANNED", "SHIPPED", "DECLINED", name="feature_request_status")
    op.create_table(
        "feature_requests",
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("submitted_by_id", sa.UUID(), nullable=True),
        sa.Column("status", feature_status, nullable=False, server_default="OPEN"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "feature_votes",
        sa.Column("feature_request_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["feature_request_id"], ["feature_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_request_id", "user_id", name="uq_feature_vote_user"),
    )

    # --- changelog_entries (US-092) — platform-wide ---
    op.create_table(
        "changelog_entries",
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_changelog_entries_is_published", "changelog_entries", ["is_published"])

    for statement in enable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("changelog_entries")
    op.drop_table("feature_votes")
    op.drop_table("feature_requests")
    op.execute("DROP TYPE IF EXISTS feature_request_status")
    op.drop_table("milestone_events")
    op.execute("DROP TYPE IF EXISTS milestone_key")
    op.drop_table("nps_survey_prompts")
    op.execute("DROP TYPE IF EXISTS nps_trigger")
    op.drop_table("support_requests")
    op.execute("DROP TYPE IF EXISTS support_request_status")
    op.drop_table("referrals")
    op.execute("DROP TYPE IF EXISTS referral_status")
    op.drop_table("referral_codes")
    op.drop_table("customer_success_alerts")
    op.drop_table("organization_health_scores")
    op.execute("DROP TYPE IF EXISTS health_trend")
    op.drop_table("help_articles")
    op.drop_table("onboarding_progress")

    op.drop_column("organizations", "credit_months")
    op.drop_column("users", "is_platform_staff")
