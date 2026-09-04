"""tenant applications, guarantors and landlord reference checks

Sprint 14. Screening lives in its own tables rather than as extra columns on
`tenants` because most applicants never become tenants — folding them in would
poison every duplicate check and every count in the product.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_table_statements, enable_table_statements

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCREENING_TABLES = ("tenant_applications", "guarantors", "reference_checks")

NEW_NOTIFICATION_TYPES = (
    "APPLICATION_RECEIVED",
    "APPLICATION_APPROVED",
    "APPLICATION_REJECTED",
    "GUARANTOR_REQUEST",
    "REFERENCE_REQUEST",
)


def upgrade() -> None:
    application_status = postgresql.ENUM(
        "SUBMITTED",
        "UNDER_REVIEW",
        "INTERVIEW_SCHEDULED",
        "APPROVED",
        "REJECTED",
        "WITHDRAWN",
        name="application_status",
        create_type=False,
    )
    employment_status = postgresql.ENUM(
        "EMPLOYED",
        "SELF_EMPLOYED",
        "BUSINESS_OWNER",
        "STUDENT",
        "RETIRED",
        "UNEMPLOYED",
        name="employment_status",
        create_type=False,
    )
    rejection_reason = postgresql.ENUM(
        "INSUFFICIENT_INCOME",
        "FAILED_REFERENCE_CHECK",
        "INCOMPLETE_APPLICATION",
        "NO_GUARANTOR",
        "UNIT_TAKEN",
        "OTHER",
        name="application_rejection_reason",
        create_type=False,
    )
    guarantor_status = postgresql.ENUM(
        "PENDING", "ACKNOWLEDGED", "DECLINED", "EXPIRED", name="guarantor_status", create_type=False
    )
    reference_status = postgresql.ENUM(
        "SENT", "POSITIVE", "NEGATIVE", "NO_RESPONSE", name="reference_status", create_type=False
    )
    # `create_type=False` above stops `create_table` emitting a second CREATE TYPE
    # per column, so the types are made here, once, and reused.
    for name, values in (
        (
            "application_status",
            ("SUBMITTED", "UNDER_REVIEW", "INTERVIEW_SCHEDULED", "APPROVED", "REJECTED", "WITHDRAWN"),
        ),
        (
            "employment_status",
            ("EMPLOYED", "SELF_EMPLOYED", "BUSINESS_OWNER", "STUDENT", "RETIRED", "UNEMPLOYED"),
        ),
        (
            "application_rejection_reason",
            (
                "INSUFFICIENT_INCOME",
                "FAILED_REFERENCE_CHECK",
                "INCOMPLETE_APPLICATION",
                "NO_GUARANTOR",
                "UNIT_TAKEN",
                "OTHER",
            ),
        ),
        ("guarantor_status", ("PENDING", "ACKNOWLEDGED", "DECLINED", "EXPIRED")),
        ("reference_status", ("SENT", "POSITIVE", "NEGATIVE", "NO_RESPONSE")),
    ):
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.create_table(
        "tenant_applications",
        sa.Column("reference_code", sa.String(32), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("national_id", sa.String(64), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("current_address", sa.String(512), nullable=True),
        sa.Column("current_landlord_name", sa.String(255), nullable=True),
        sa.Column("current_landlord_phone", sa.String(32), nullable=True),
        sa.Column("years_at_current_address", sa.Numeric(4, 1), nullable=True),
        sa.Column("reason_for_moving", sa.Text(), nullable=True),
        sa.Column("employment_status", employment_status, nullable=False, server_default="EMPLOYED"),
        sa.Column("employer_name", sa.String(255), nullable=True),
        sa.Column("employer_phone", sa.String(32), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("monthly_income", sa.Numeric(12, 2), nullable=True),
        sa.Column("months_in_employment", sa.Integer(), nullable=True),
        sa.Column("occupants", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("intended_move_in", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id_document_id", sa.UUID(), nullable=True),
        sa.Column("passport_photo_id", sa.UUID(), nullable=True),
        sa.Column(
            "payslip_file_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "score_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", application_status, nullable=False, server_default="SUBMITTED"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interview_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interview_notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("rejection_reason", rejection_reason, nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("tenancy_id", sa.UUID(), nullable=True),
        sa.Column("submitted_online", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["passport_photo_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenancy_id"], ["tenancies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "reference_code", name="uq_application_ref_per_org"),
    )
    for column in (
        "organization_id",
        "unit_id",
        "reference_code",
        "full_name",
        "phone_number",
        "national_id",
        "status",
        "score",
    ):
        op.create_index(f"ix_tenant_applications_{column}", "tenant_applications", [column])

    op.create_table(
        "guarantors",
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("relationship_to_applicant", sa.String(64), nullable=False),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("national_id", sa.String(64), nullable=True),
        sa.Column("id_document_id", sa.UUID(), nullable=True),
        sa.Column("employer_name", sa.String(255), nullable=True),
        sa.Column("occupation", sa.String(255), nullable=True),
        sa.Column("monthly_income", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", guarantor_status, nullable=False, server_default="PENDING"),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_reason", sa.Text(), nullable=True),
        sa.Column("agreement_document_id", sa.UUID(), nullable=True),
        sa.Column("signature_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["tenant_applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agreement_document_id"], ["stored_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["signature_id"], ["digital_signatures.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_guarantors_organization_id", "guarantors", ["organization_id"])
    op.create_index("ix_guarantors_application_id", "guarantors", ["application_id"])
    op.create_index("ix_guarantors_token_hash", "guarantors", ["token_hash"])

    op.create_table(
        "reference_checks",
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("landlord_name", sa.String(255), nullable=False),
        sa.Column("landlord_phone", sa.String(32), nullable=False),
        sa.Column("property_reference", sa.String(255), nullable=True),
        sa.Column("status", reference_status, nullable=False, server_default="SENT"),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_on_time", sa.Boolean(), nullable=True),
        sa.Column("would_rent_again", sa.Boolean(), nullable=True),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["tenant_applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_reference_checks_organization_id", "reference_checks", ["organization_id"])
    op.create_index("ix_reference_checks_application_id", "reference_checks", ["application_id"])
    op.create_index("ix_reference_checks_token_hash", "reference_checks", ["token_hash"])

    for statement in enable_table_statements(SCREENING_TABLES):
        op.execute(statement)

    for value in NEW_NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")

    # The signed deed of guarantee needs somewhere to file itself.
    op.execute("ALTER TYPE file_category ADD VALUE IF NOT EXISTS 'GUARANTEE'")


def downgrade() -> None:
    for statement in disable_table_statements(SCREENING_TABLES):
        op.execute(statement)

    op.drop_table("reference_checks")
    op.drop_table("guarantors")
    op.drop_table("tenant_applications")

    for name in (
        "reference_status",
        "guarantor_status",
        "application_rejection_reason",
        "employment_status",
        "application_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
