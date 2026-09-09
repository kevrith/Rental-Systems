"""per-organisation mpesa collection

Rent stops passing through RentFlow. Each landlord collects into their own
M-Pesa — their paybill, their till, or their phone — and the platform's job is
to prompt, confirm, receipt and reconcile rather than to hold the money.

Three collection modes because that is what landlords in this market actually
have: a Daraja app (AUTOMATED), a shortcode but no API access (PAYBILL), or a
personal number and nothing else (MANUAL).

Also drops `payments.paystack_reference`: card rent collection is gone, and
Paystack now carries RentFlow's own subscription revenue only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    postgresql.ENUM("AUTOMATED", "PAYBILL", "MANUAL", name="mpesa_collection_mode").create(
        op.get_bind(), checkfirst=True
    )

    op.add_column(
        "organizations",
        sa.Column(
            "mpesa_collection_mode",
            postgresql.ENUM(name="mpesa_collection_mode", create_type=False),
            nullable=False,
            server_default="MANUAL",
        ),
    )
    op.add_column("organizations", sa.Column("mpesa_shortcode", sa.String(length=16), nullable=True))
    op.add_column("organizations", sa.Column("mpesa_phone_number", sa.String(length=32), nullable=True))
    op.add_column("organizations", sa.Column("mpesa_account_label", sa.String(length=64), nullable=True))
    op.add_column("organizations", sa.Column("daraja_consumer_key_encrypted", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("daraja_consumer_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("daraja_passkey_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("daraja_environment", sa.String(length=16), nullable=False, server_default="sandbox"),
    )
    op.add_column("organizations", sa.Column("mpesa_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("daraja_initiator_name_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "organizations", sa.Column("daraja_security_credential_encrypted", sa.Text(), nullable=True)
    )

    op.drop_index("ix_payments_paystack_reference", table_name="payments")
    op.drop_column("payments", "paystack_reference")


def downgrade() -> None:
    op.add_column("payments", sa.Column("paystack_reference", sa.String(length=64), nullable=True))
    op.create_index("ix_payments_paystack_reference", "payments", ["paystack_reference"], unique=True)

    for column in (
        "daraja_security_credential_encrypted",
        "daraja_initiator_name_encrypted",
        "mpesa_verified_at",
        "daraja_environment",
        "daraja_passkey_encrypted",
        "daraja_consumer_secret_encrypted",
        "daraja_consumer_key_encrypted",
        "mpesa_account_label",
        "mpesa_phone_number",
        "mpesa_shortcode",
        "mpesa_collection_mode",
    ):
        op.drop_column("organizations", column)

    op.execute("DROP TYPE IF EXISTS mpesa_collection_mode")
