"""Verifies Google ID tokens from Sign In With Google (Identity Services).

The frontend gets a signed ID token straight from Google — there's no
authorization-code exchange and no client secret involved, only a check that
the token's signature, issuer and audience are legit. `google-auth` would
pull in a chunk of new dependencies for that; `python-jose`, already used for
RentFlow's own tokens (see app.core.security), does the same job with what's
already installed.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings

_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_JWKS_TTL_SECONDS = 3600

_jwks_cache: dict[str, Any] = {"keys": None, "expires_at": 0.0}


async def _fetch_jwks() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(_CERTS_URL)
        response.raise_for_status()
        return response.json()


async def _get_jwks(*, force_refresh: bool = False) -> dict[str, Any]:
    if force_refresh or _jwks_cache["keys"] is None or time.monotonic() >= _jwks_cache["expires_at"]:
        _jwks_cache["keys"] = await _fetch_jwks()
        _jwks_cache["expires_at"] = time.monotonic() + _JWKS_TTL_SECONDS
    return _jwks_cache["keys"]


@dataclass(slots=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    full_name: str


async def verify_google_credential(credential: str) -> GoogleIdentity:
    """Verify a Google Identity Services ID token and return the identity it carries.

    Raises HTTPException(401) for anything that fails to check out — an
    expired, forged, or wrong-audience token all look the same to the caller.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not configured")

    jwks = await _get_jwks()
    try:
        claims = jwt.decode(
            credential,
            jwks,
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
            issuer=list(_ISSUERS),
        )
    except JWTError:
        # The key Google signed this with may have rotated since the cache was
        # filled — refresh once and give it a second try before giving up.
        try:
            jwks = await _get_jwks(force_refresh=True)
            claims = jwt.decode(
                credential,
                jwks,
                algorithms=["RS256"],
                audience=settings.GOOGLE_CLIENT_ID,
                issuer=list(_ISSUERS),
            )
        except JWTError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired Google credential") from exc

    email = claims.get("email")
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google account has no email address")

    return GoogleIdentity(
        sub=claims["sub"],
        email=email,
        email_verified=bool(claims.get("email_verified")),
        full_name=claims.get("name") or email.split("@")[0],
    )
