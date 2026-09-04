"""Human-quotable reference codes.

Every business entity a tenant or landlord might mention on a phone call gets a
short code. They are random rather than sequential so a competitor cannot infer
portfolio size from a code, and unique per organization (enforced by a DB
constraint) — the loop here just avoids the collision round-trip.
"""

import secrets
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Excludes I, O, 0 and 1 — they get misread when a code is written down.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_MAX_ATTEMPTS = 10


def _random_part(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def generate_reference(
    db: AsyncSession,
    model: Any,
    organization_id: uuid.UUID,
    prefix: str,
    length: int = 6,
) -> str:
    """Return a code of the form `PRP-7K2M9Q` unused within this organization."""
    for _ in range(_MAX_ATTEMPTS):
        code = f"{prefix}-{_random_part(length)}"
        taken = await db.scalar(
            select(model.id).where(model.organization_id == organization_id, model.reference_code == code)
        )
        if not taken:
            return code
    raise RuntimeError(f"Could not allocate a unique {prefix} reference after {_MAX_ATTEMPTS} attempts")


async def generate_invoice_reference(
    db: AsyncSession, model: Any, organization_id: uuid.UUID, period: date
) -> str:
    """Invoice codes carry their billing period: `INV-2026-09-7K2M9`."""
    stem = f"INV-{period.year:04d}-{period.month:02d}"
    for _ in range(_MAX_ATTEMPTS):
        code = f"{stem}-{_random_part(5)}"
        taken = await db.scalar(
            select(model.id).where(model.organization_id == organization_id, model.reference_code == code)
        )
        if not taken:
            return code
    raise RuntimeError(f"Could not allocate a unique invoice reference after {_MAX_ATTEMPTS} attempts")
