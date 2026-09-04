"""Symmetric encryption for third-party credentials held on behalf of a customer.

Only one thing goes through here today: a landlord's KRA eTIMS credentials
(US-053). They belong to the landlord, not to us, and a database dump must not
hand anyone the ability to file tax documents in their name — so they are stored
encrypted and only decrypted in the moment a submission is made.

The key is derived from `SECRET_KEY` rather than configured separately, so an
existing deployment gains this without a new secret to distribute. Rotating
`SECRET_KEY` therefore invalidates stored credentials; `decrypt` returns None
rather than raising so the caller can ask the landlord to re-enter them.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

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
