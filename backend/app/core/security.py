import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Portal invitees and Google-only accounts carry the unusable "!"
        # sentinel until they set a real password — bcrypt rejects it as a
        # malformed hash rather than just failing the comparison.
        return False


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: Literal["access", "refresh"],
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, org_id: str, role: str, session_id: str | None = None) -> str:
    claims: dict[str, Any] = {"org_id": org_id, "role": role}
    if session_id:
        claims["sid"] = session_id
    return _create_token(
        subject=user_id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
        extra_claims=claims,
    )


def create_refresh_token(user_id: str, session_id: str | None = None) -> str:
    claims: dict[str, Any] = {"jti": secrets.token_urlsafe(16)}
    if session_id:
        claims["sid"] = session_id
    return _create_token(
        subject=user_id,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
        extra_claims=claims,
    )


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def hash_token(token: str) -> str:
    """Store only a digest of long-lived tokens (refresh, email links, invites) so a
    database leak yields nothing usable."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_url_token() -> str:
    """A single-use secret for an emailed or SMS'd link."""
    return secrets.token_urlsafe(32)


def generate_api_key() -> tuple[str, str, str]:
    """A public API key (US-086): `(full_key, prefix, hash)`.

    Only `hash` is stored — like a refresh token, the raw value is shown to the
    caller exactly once. `prefix` is stored alongside it in the clear so a
    lookup can find the candidate row without hashing every key in the table,
    and so the owner can tell keys apart in a list without ever seeing the
    secret again.
    """
    secret = secrets.token_urlsafe(32)
    prefix = f"rf_live_{secrets.token_hex(4)}"
    full_key = f"{prefix}_{secret}"
    return full_key, prefix, hash_token(full_key)


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(32)


def sign_payload(*parts: str) -> str:
    """Short HMAC used to make generated receipts tamper-evident (US-023)."""
    message = "|".join(parts).encode("utf-8")
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return digest[:32].upper()


def verify_signature(signature: str, *parts: str) -> bool:
    return hmac.compare_digest(signature, sign_payload(*parts))


def device_fingerprint(user_agent: str | None, client_hint: str | None) -> str:
    """Stable per-device id.

    The client supplies a random, locally-persisted value (`X-Device-Id`); mixing
    in the user agent means a copied id from a different browser won't match.
    """
    raw = f"{client_hint or ''}|{user_agent or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
