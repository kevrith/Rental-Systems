"""masterplan gap closure

Sprint 26: the features the masterplan promised that no sprint had picked up.

  * `management_agreements` — the owner-agency contract as a legal instrument,
    with the terms frozen as signed. `owner_profiles` keeps the *operative*
    terms the disbursement run and maintenance approval actually read; this
    table is what both parties put their name to, so a later edit to the
    profile cannot rewrite history. Both signatures are ordinary
    `digital_signatures` rows, which is what makes the dual OTP flow reuse the
    signing pipeline rather than grow a second one.
  * `communication_templates` — an organisation's own wording for one
    notification type on one channel. Absent one, the hardcoded copy in the
    service that raised the notification still stands, so this is additive.
  * `demo_datasets` — the receipt for a sample-data seeding run, recording the
    exact ids created so teardown can never delete a real row.
  * `security_breaches` — Kenya DPA s.43's 72-hour notification clock.
    Platform-level, not organisation-scoped: one incident spans customers and
    it is RentFlow that has to notify the Data Commissioner.
  * `organization_encryption_keys` — envelope encryption, so a customer's
    stored third-party credentials are encrypted under a key of their own
    rather than one master key shared by the whole platform.

Plus column-level additions: OCR evidence on meter readings, dual approval on
payments, suspension/session/demo fields on organisations, and video tutorial
fields on help articles.

Every enum label below is the Python enum member's *name*, not its lowercase
`.value` — see the Sprint 20 migration's docstring for why that distinction
matters here.

Revision ID: a4b5c6d7e8f9
Revises: 9b1c2d3e4f5a
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "9b1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_ORG_SCOPED_TABLES = (
    "management_agreements",
    "communication_templates",
    "demo_datasets",
)

MANAGEMENT_AGREEMENT_STATUS = (
    "DRAFT",
    "PENDING_SIGNATURES",
    "ACTIVE",
    "TERMINATION_NOTICE",
    "TERMINATED",
    "EXPIRED",
    "CANCELLED",
)
TERMINATION_PARTY = ("OWNER", "AGENCY")
TEMPLATE_CHANNEL = ("ANY", "WHATSAPP", "SMS", "EMAIL", "IN_APP", "PUSH")
BREACH_CATEGORY = (
    "UNAUTHORISED_ACCESS",
    "CREDENTIAL_COMPROMISE",
    "DATA_EXFILTRATION",
    "ACCIDENTAL_DISCLOSURE",
    "SYSTEM_COMPROMISE",
    "LOST_DEVICE",
    "THIRD_PARTY_PROCESSOR",
)
BREACH_SEVERITY = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
BREACH_STATUS = ("DETECTED", "INVESTIGATING", "CONTAINED", "NOTIFIED", "CLOSED", "DISMISSED")


def _enum(values: Sequence[str], name: str) -> postgresql.ENUM:
    """The type is created by `create_table` on first use, so every later
    reference has to declare it already exists."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # A tenant who has forgotten their portal password signs in from a link.
    op.execute("ALTER TYPE token_purpose ADD VALUE IF NOT EXISTS 'TENANT_PORTAL_MAGIC_LINK'")
    # Raised to platform staff when a breach's 72-hour clock is running down,
    # and to a landlord when their management agreement needs signing.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'BREACH_NOTIFICATION'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'MANAGEMENT_AGREEMENT'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'PAYMENT_APPROVAL'")
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'MANAGEMENT_AGREEMENT'")

    # --- meter reading camera OCR (Module 5) ---
    op.add_column("meter_readings", sa.Column("ocr_reading", sa.Numeric(12, 2), nullable=True))
    op.add_column("meter_readings", sa.Column("ocr_confidence", sa.Numeric(5, 2), nullable=True))
    op.add_column("meter_readings", sa.Column("ocr_accepted", sa.Boolean(), nullable=True))

    # --- dual approval for large cash (masterplan, Fraud Prevention) ---
    op.add_column(
        "payments",
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("payments", sa.Column("approved_by_id", sa.UUID(), nullable=True))
    op.add_column("payments", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("approval_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_payments_approved_by_id_users",
        "payments",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_payments_requires_approval", "payments", ["requires_approval"])

    # --- organisation lifecycle, cash policy, session cap, demo flag ---
    op.add_column("organizations", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("suspension_reason", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("suspended_by_id", sa.UUID(), nullable=True))
    op.add_column("organizations", sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "organizations", sa.Column("cash_dual_approval_threshold", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column("organizations", sa.Column("max_concurrent_sessions", sa.Integer(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_foreign_key(
        "fk_organizations_suspended_by_id_users",
        "organizations",
        "users",
        ["suspended_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- video tutorials (Module 24) ---
    op.add_column("help_articles", sa.Column("video_url", sa.String(1024), nullable=True))
    op.add_column("help_articles", sa.Column("video_duration_seconds", sa.Integer(), nullable=True))
    op.add_column("help_articles", sa.Column("video_thumbnail_url", sa.String(1024), nullable=True))
    op.add_column("help_articles", sa.Column("video_provider", sa.String(32), nullable=True))

    # --- management agreements (masterplan, Management Agreement Module) ---
    op.create_table(
        "management_agreements",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("owner_profile_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(*MANAGEMENT_AGREEMENT_STATUS, name="management_agreement_status"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("management_fee_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("disbursement_day", sa.Integer(), nullable=False),
        sa.Column("maintenance_auto_approve_limit", sa.Numeric(12, 2), nullable=False),
        sa.Column("maintenance_notify_limit", sa.Numeric(12, 2), nullable=False),
        sa.Column("scope_of_management", sa.Text(), nullable=True),
        sa.Column("property_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("owner_signature_id", sa.UUID(), nullable=True),
        sa.Column("agency_signature_id", sa.UUID(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "termination_requested_by",
            postgresql.ENUM(*TERMINATION_PARTY, name="termination_party"),
            nullable=True,
        ),
        sa.Column("termination_requested_by_id", sa.UUID(), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        sa.Column("termination_effective_date", sa.Date(), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["owner_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_signature_id"], ["digital_signatures.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agency_signature_id"], ["digital_signatures.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["termination_requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_management_agreement_ref_per_org"),
    )
    op.create_index("ix_management_agreements_organization_id", "management_agreements", ["organization_id"])
    op.create_index("ix_management_agreements_reference_code", "management_agreements", ["reference_code"])
    op.create_index(
        "ix_management_agreements_owner_profile_id", "management_agreements", ["owner_profile_id"]
    )
    op.create_index("ix_management_agreements_status", "management_agreements", ["status"])
    op.create_index("ix_management_agreements_end_date", "management_agreements", ["end_date"])
    op.create_index(
        "ix_management_agreements_termination_effective_date",
        "management_agreements",
        ["termination_effective_date"],
    )

    # --- editable communication templates (Module 21) ---
    op.create_table(
        "communication_templates",
        sa.Column(
            "notification_type",
            postgresql.ENUM(name="notification_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "channel",
            postgresql.ENUM(*TEMPLATE_CHANNEL, name="template_channel"),
            nullable=False,
            server_default="ANY",
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "known_variables", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "notification_type",
            "channel",
            name="uq_communication_template_type_channel",
        ),
    )
    op.create_index(
        "ix_communication_templates_organization_id", "communication_templates", ["organization_id"]
    )
    op.create_index(
        "ix_communication_templates_notification_type", "communication_templates", ["notification_type"]
    )
    op.create_index("ix_communication_templates_is_active", "communication_templates", ["is_active"])

    # --- sample data / demo mode (Module 24) ---
    op.create_table(
        "demo_datasets",
        sa.Column("created_rows", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recipe", sa.String(64), nullable=False, server_default="starter_portfolio"),
        sa.Column("seeded_by_id", sa.UUID(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seeded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demo_datasets_organization_id", "demo_datasets", ["organization_id"])

    # --- breach register and the 72-hour clock (Kenya DPA s.43) ---
    op.create_table(
        "security_breaches",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("category", postgresql.ENUM(*BREACH_CATEGORY, name="breach_category"), nullable=False),
        sa.Column(
            "severity",
            postgresql.ENUM(*BREACH_SEVERITY, name="breach_severity"),
            nullable=False,
            server_default="MEDIUM",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*BREACH_STATUS, name="breach_status"),
            nullable=False,
            server_default="DETECTED",
        ),
        sa.Column("summary", sa.String(512), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "affected_organization_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("affected_subject_count", sa.Integer(), nullable=True),
        sa.Column(
            "data_categories", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("detector", sa.String(64), nullable=True),
        sa.Column("pattern_key", sa.String(128), nullable=True),
        sa.Column("reported_by_id", sa.UUID(), nullable=True),
        sa.Column("contained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("containment_notes", sa.Text(), nullable=True),
        sa.Column("regulator_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("regulator_reference", sa.String(128), nullable=True),
        sa.Column("customers_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subjects_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("no_notification_reason", sa.Text(), nullable=True),
        sa.Column("remediation_notes", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_id", sa.UUID(), nullable=True),
        sa.Column("escalation_sent_hours", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["reported_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_code", name="uq_security_breach_reference_code"),
        sa.UniqueConstraint("pattern_key", name="uq_security_breach_pattern_key"),
    )
    op.create_index("ix_security_breaches_reference_code", "security_breaches", ["reference_code"])
    op.create_index("ix_security_breaches_severity", "security_breaches", ["severity"])
    op.create_index("ix_security_breaches_status", "security_breaches", ["status"])
    op.create_index("ix_security_breaches_detected_at", "security_breaches", ["detected_at"])
    op.create_index("ix_security_breaches_notification_due_at", "security_breaches", ["notification_due_at"])

    # --- per-organisation encryption keys (Multi-Tenant Data Isolation) ---
    op.create_table(
        "organization_encryption_keys",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("wrapped_key", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "version", name="uq_org_encryption_key_version"),
    )
    op.create_index(
        "ix_organization_encryption_keys_organization_id",
        "organization_encryption_keys",
        ["organization_id"],
    )

    for statement in enable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_table_statements(NEW_ORG_SCOPED_TABLES):
        op.execute(statement)

    op.drop_table("organization_encryption_keys")

    op.drop_table("security_breaches")
    op.execute("DROP TYPE IF EXISTS breach_status")
    op.execute("DROP TYPE IF EXISTS breach_severity")
    op.execute("DROP TYPE IF EXISTS breach_category")

    op.drop_table("demo_datasets")

    op.drop_table("communication_templates")
    op.execute("DROP TYPE IF EXISTS template_channel")

    op.drop_table("management_agreements")
    op.execute("DROP TYPE IF EXISTS termination_party")
    op.execute("DROP TYPE IF EXISTS management_agreement_status")

    op.drop_column("help_articles", "video_provider")
    op.drop_column("help_articles", "video_thumbnail_url")
    op.drop_column("help_articles", "video_duration_seconds")
    op.drop_column("help_articles", "video_url")

    op.drop_constraint("fk_organizations_suspended_by_id_users", "organizations", type_="foreignkey")
    op.drop_column("organizations", "is_demo")
    op.drop_column("organizations", "max_concurrent_sessions")
    op.drop_column("organizations", "cash_dual_approval_threshold")
    op.drop_column("organizations", "reactivated_at")
    op.drop_column("organizations", "suspended_by_id")
    op.drop_column("organizations", "suspension_reason")
    op.drop_column("organizations", "suspended_at")

    op.drop_index("ix_payments_requires_approval", table_name="payments")
    op.drop_constraint("fk_payments_approved_by_id_users", "payments", type_="foreignkey")
    op.drop_column("payments", "approval_note")
    op.drop_column("payments", "approved_at")
    op.drop_column("payments", "approved_by_id")
    op.drop_column("payments", "requires_approval")

    op.drop_column("meter_readings", "ocr_accepted")
    op.drop_column("meter_readings", "ocr_confidence")
    op.drop_column("meter_readings", "ocr_reading")

    # `token_purpose`, `notification_type` and `file_category` keep their new
    # labels: Postgres cannot drop an enum value, and a label nothing
    # references is harmless.
