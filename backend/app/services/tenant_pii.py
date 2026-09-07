"""Encrypt/decrypt helpers for `Tenant`'s field-level-encrypted PII (Sprint 26A).

National ID is the first field to go through this — the single most sensitive
identifier the platform stores, and the one a security questionnaire asks
about by name. Kept in its own module (rather than inline in
`tenant_service.py`) because the callers span several services that would
otherwise have to import `tenant_service` itself and create a cycle
(`tenant_service` already imports `lease_service`, which needs
`decrypt_national_id` too).

The pattern: `national_id_encrypted` is ciphertext under the organization's
own key (`app.core.crypto.encrypt_for_org`); `national_id_blind_index` is a
deterministic HMAC (`crypto.blind_index`) so `find_duplicates` can still do an
exact-match lookup without decrypting anything; `national_id_last4` is a
plaintext display hint, same idea as `crypto.mask()`. All three are set and
cleared together — there is no valid state where only one of them is populated.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.models.tenant import Tenant


async def set_national_id(db: AsyncSession, tenant: Tenant, value: str | None) -> None:
    """Encrypt `value` onto `tenant`'s three national-ID columns, or clear all three.

    Does not flush or commit — matches every other setter in this codebase,
    which leaves the transaction to its caller.
    """
    if not value:
        tenant.national_id_encrypted = None
        tenant.national_id_blind_index = None
        tenant.national_id_last4 = None
        return
    tenant.national_id_encrypted = await crypto.encrypt_for_org(db, tenant.organization_id, value)
    tenant.national_id_blind_index = crypto.blind_index(tenant.organization_id, value)
    tenant.national_id_last4 = crypto.last_n(value)


async def decrypt_national_id(db: AsyncSession, tenant: Tenant) -> str | None:
    """The full plaintext national ID — an intentional, single-record reveal.

    Callers that render many tenants at once (list/search views) should use
    `national_id_last4` instead of calling this per row; each call does a key
    lookup and is meant for the "one tenant, on purpose" case (a detail view,
    a PDF, an export, an already-authorized data-subject export) not a loop.
    """
    return await crypto.decrypt_for_org(db, tenant.organization_id, tenant.national_id_encrypted)


def masked_national_id(tenant: Tenant) -> str | None:
    """A display-safe hint (`•••••1234`) built from the last-4 column alone — no decrypt, no db."""
    if not tenant.national_id_last4:
        return None
    return f"{'•' * 5}{tenant.national_id_last4}"
