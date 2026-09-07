"""Symmetric encryption for third-party credentials held on behalf of a customer.

Four things go through here: a landlord's KRA eTIMS credentials (US-053),
their property-portal API keys and accounting OAuth tokens (US-099, US-100),
and the signing secret for their outbound webhooks (US-097). All four belong
to the customer, not to us, and a database dump must not hand anyone the
ability to file tax documents, list property or forge a webhook in their name.

Two layers, and the distinction matters:

  * `encrypt`/`decrypt` seal under one key derived from `SECRET_KEY`. This is
    the original scheme and is kept only so ciphertext written before envelope
    encryption existed can still be read.
  * `encrypt_for_org`/`decrypt_for_org` seal under a key belonging to that one
    organisation, itself wrapped by a master key also derived from
    `SECRET_KEY`. Every write takes this path. What it buys is blast radius:
    one customer's key can be rotated after a suspected compromise without
    every other customer having to re-enter their credentials, and ciphertext
    lifted from one tenant is inert against another.

There is no KMS in this deployment, so both derive from `SECRET_KEY` in the
end. Rotating `SECRET_KEY` therefore still invalidates everything; both
`decrypt` paths return None rather than raising so the caller can ask the
landlord to re-enter them.
"""

import base64
import hashlib
import logging
import uuid
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("rentflow.crypto")

_INFO = b"rentflow-credential-encryption-v1"


def _fernet() -> Fernet:
    # Fernet wants 32 url-safe base64 bytes; SECRET_KEY is an arbitrary string.
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8") + _INFO).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    """Returns None for anything this key cannot open, rather than raising."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        logger.warning("Stored credential could not be decrypted — the signing key may have rotated")
        return None


def mask(value: str | None, *, keep: int = 4) -> str | None:
    """`ABC123456` -> `•••••3456`. For showing that something is set without showing it."""
    if not value:
        return None
    if len(value) <= keep:
        return "•" * len(value)
    return "•" * (len(value) - keep) + value[-keep:]


# --------------------------------------------------- per-organization keys


_ORG_INFO = b"rentflow-organization-key-wrapping-v1"
# Ciphertext written through `encrypt_for_org` carries the key version it was
# sealed under, so rotation can leave older rows readable until they are
# re-encrypted rather than breaking them the moment a new key is issued.
_ORG_PREFIX = "orgk"


def _wrapping_fernet() -> Fernet:
    """The master key, used only to wrap and unwrap per-organization keys.

    Derived from a different info string than `_fernet()` above, so the key
    that protects other keys is not the same key that encrypts data directly —
    a wrapped key leaking tells an attacker nothing about legacy ciphertext,
    and vice versa.
    """
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8") + _ORG_INFO).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


async def _key_row(db: "AsyncSession", organization_id: "uuid.UUID", version: int | None):
    from sqlalchemy import select

    from app.models.organization import OrganizationEncryptionKey

    query = select(OrganizationEncryptionKey).where(
        OrganizationEncryptionKey.organization_id == organization_id
    )
    if version is None:
        query = query.where(OrganizationEncryptionKey.is_active.is_(True))
    else:
        query = query.where(OrganizationEncryptionKey.version == version)
    return await db.scalar(query.order_by(OrganizationEncryptionKey.version.desc()).limit(1))


async def ensure_org_key(db: "AsyncSession", organization_id: "uuid.UUID"):
    """The organization's active key, minting one on first use.

    Added to the caller's session but not committed — the caller owns the
    transaction, the same contract every other service here follows.
    """
    from app.models.organization import OrganizationEncryptionKey

    existing = await _key_row(db, organization_id, None)
    if existing is not None:
        return existing

    record = OrganizationEncryptionKey(
        organization_id=organization_id,
        version=1,
        wrapped_key=_wrapping_fernet().encrypt(Fernet.generate_key()).decode("ascii"),
        is_active=True,
    )
    db.add(record)
    await db.flush()
    return record


async def encrypt_for_org(db: "AsyncSession", organization_id: "uuid.UUID", plaintext: str) -> str:
    """Encrypt under the organization's own key. Returns `orgk:<version>:<token>`."""
    record = await ensure_org_key(db, organization_id)
    key = _wrapping_fernet().decrypt(record.wrapped_key.encode("ascii"))
    token = Fernet(key).encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_ORG_PREFIX}:{record.version}:{token}"


async def decrypt_for_org(
    db: "AsyncSession", organization_id: "uuid.UUID", ciphertext: str | None
) -> str | None:
    """Open a per-organization ciphertext, falling back to the legacy master key.

    Anything without the `orgk:` prefix predates envelope encryption and was
    sealed with `encrypt()` directly. Reading it here rather than migrating the
    rows means an existing deployment keeps working through the changeover and
    each credential moves across the next time it is saved.
    """
    if not ciphertext:
        return None
    if not ciphertext.startswith(f"{_ORG_PREFIX}:"):
        return decrypt(ciphertext)

    try:
        _, raw_version, token = ciphertext.split(":", 2)
        version = int(raw_version)
    except ValueError:
        logger.warning("Malformed per-organization ciphertext for %s", organization_id)
        return None

    record = await _key_row(db, organization_id, version)
    if record is None:
        logger.warning("No version %s encryption key for organization %s", version, organization_id)
        return None

    try:
        key = _wrapping_fernet().decrypt(record.wrapped_key.encode("ascii"))
        return Fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        logger.warning("Stored credential could not be decrypted for organization %s", organization_id)
        return None


async def rotate_org_key(db: "AsyncSession", organization_id: "uuid.UUID"):
    """Issue the next key version and retire the current one.

    Existing ciphertext stays readable — the retired key row is kept, only its
    `is_active` flag drops — so rotation is safe to run without a coordinated
    re-encryption pass. Anything written afterwards uses the new version.
    """
    from datetime import UTC, datetime

    from app.models.organization import OrganizationEncryptionKey

    current = await _key_row(db, organization_id, None)
    next_version = (current.version + 1) if current is not None else 1
    if current is not None:
        current.is_active = False
        current.rotated_at = datetime.now(UTC)

    record = OrganizationEncryptionKey(
        organization_id=organization_id,
        version=next_version,
        wrapped_key=_wrapping_fernet().encrypt(Fernet.generate_key()).decode("ascii"),
        is_active=True,
    )
    db.add(record)
    await db.flush()
    return record
