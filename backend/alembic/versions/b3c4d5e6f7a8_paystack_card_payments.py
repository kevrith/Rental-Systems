"""paystack card payments

Adds the CARD payment method and the Paystack transaction reference it is
matched on. The enum label is the uppercase member *name*, not the lowercase
value: SQLAlchemy's `Enum(PaymentMethod, name="payment_method")` binds members
by `.name` because nothing here passes `values_callable`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "321b29763079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'CARD'")
    op.add_column("payments", sa.Column("paystack_reference", sa.String(length=64), nullable=True))
    op.create_index("ix_payments_paystack_reference", "payments", ["paystack_reference"], unique=True)


def downgrade() -> None:
    # Postgres cannot drop a single enum label, so CARD stays behind; any
    # payment still carrying it would be unreadable if it were removed.
    op.drop_index("ix_payments_paystack_reference", table_name="payments")
    op.drop_column("payments", "paystack_reference")
