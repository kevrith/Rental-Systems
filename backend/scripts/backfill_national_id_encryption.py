"""One-off: encrypt every tenant's existing plaintext national ID (Sprint 26A).

The migration that added `tenants.national_id_encrypted` /
`_blind_index` / `_last4` is additive on purpose — it does not touch the old
plaintext `national_id` column, so this script is what actually moves data
across. Run it once per environment, after the migration and before relying
on national-ID search/duplicate-detection to have picked up existing tenants
(new tenants created after the migration are encrypted automatically by
`tenant_service.create_tenant`; this script only backfills what came before).

Safe to run more than once — it only touches rows that still have plaintext
`national_id` set but no `national_id_encrypted` yet, so a partial or re-run
picks up where it left off rather than double-encrypting.

Usage (from `backend/`, with the venv active and `DATABASE_URL` pointing at
the target environment):

    python -m scripts.backfill_national_id_encryption

Once this has been run everywhere that matters and confirmed (spot-check a
few rows, or watch for zero remaining rows on a re-run), the old plaintext
`national_id` column can be dropped in a follow-up migration — deliberately
not part of this script, since dropping a column is one-way and should be its
own reviewed change once every environment is confirmed backfilled.
"""

import asyncio

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.tenant import Tenant
from app.services import tenant_pii


async def main() -> None:
    async with AsyncSessionLocal() as db:
        pending = (
            (
                await db.execute(
                    text(
                        "SELECT id FROM tenants "
                        "WHERE national_id IS NOT NULL AND national_id_encrypted IS NULL"
                    )
                )
            )
            .scalars()
            .all()
        )

        print(f"{len(pending)} tenant(s) to backfill")

        for tenant_id in pending:
            plaintext = await db.scalar(
                text("SELECT national_id FROM tenants WHERE id = :id"), {"id": tenant_id}
            )
            if not plaintext:
                continue
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                continue
            await tenant_pii.set_national_id(db, tenant, plaintext)

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
