"""meter_reading: add photo_reading_used column

Revision ID: a8b9c0d1e2f3
Revises: 75ec8623e8cf
Create Date: 2026-09-11 16:56:00.000000

When a high-confidence OCR reading from the meter photo differs from the value
the caretaker typed, the service now uses the photo reading as the authoritative
figure. `photo_reading_used` records that override so it is auditable:
  - NULL  → no OCR was run (photo taken without read-photo call, or offline)
  - False → OCR ran but the values agreed, or confidence was below the threshold
  - True  → the photo's OCR value replaced what the caretaker typed
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "75ec8623e8cf"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "meter_readings",
        sa.Column("photo_reading_used", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meter_readings", "photo_reading_used")
