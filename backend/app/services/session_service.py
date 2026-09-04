"""Login sessions, refresh-token rotation and trusted devices (US-002, US-005).

Refresh tokens rotate on every use. The session row stores only a hash of the
token currently valid for it, so presenting an *old* refresh token is
unambiguous evidence of theft — the response to that is to revoke every session
the user has, not just the one replayed.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    device_fingerprint,
    hash_token,
)
from app.models.session import TrustedDevice, UserSession
from app.models.user import DEFAULT_INACTIVITY_TIMEOUT_MINUTES, User
from app.schemas.auth import TokenResponse


def describe_device(user_agent: str | None) -> str:
    """A recognisable label for the active-sessions list, from the user agent."""
    if not user_agent:
        return "Unknown device"
    ua = user_agent.lower()
    if "android" in ua:
        platform = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        platform = "iPhone/iPad"
    elif "windows" in ua:
        platform = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        platform = "Mac"
    elif "linux" in ua:
        platform = "Linux"
    else:
        platform = "Unknown platform"

    if "edg/" in ua:
        browser = "Edge"
    elif "chrome" in ua and "chromium" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    return f"{browser} on {platform}"


def request_fingerprint(request: Request | None) -> str | None:
    if request is None:
        return None
    client_hint = request.headers.get("x-device-id")
    if not client_hint:
        return None
    return device_fingerprint(request.headers.get("user-agent"), client_hint)


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def create_session(
    db: AsyncSession, user: User, request: Request | None = None
) -> tuple[UserSession, TokenResponse]:
    """Open a session and mint its first token pair."""
    now = datetime.now(UTC)
    user_agent = request.headers.get("user-agent") if request else None

    session = UserSession(
        organization_id=user.organization_id,
        user_id=user.id,
        refresh_token_hash="",  # replaced below, once we know the session id
        device_fingerprint=request_fingerprint(request),
        device_name=describe_device(user_agent),
        user_agent=(user_agent or "")[:512] or None,
        ip_address=client_ip(request),
        location=request.headers.get("x-client-location") if request else None,
        last_active_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    await db.flush()

    tokens = _mint(user, session)
    return session, tokens


def _mint(user: User, session: UserSession) -> TokenResponse:
    refresh_token = create_refresh_token(str(user.id), str(session.id))
    session.refresh_token_hash = hash_token(refresh_token)
    return TokenResponse(
        access_token=create_access_token(
            str(user.id), str(user.organization_id), user.role.value, str(session.id)
        ),
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        inactivity_timeout_minutes=user.inactivity_timeout_minutes
        or DEFAULT_INACTIVITY_TIMEOUT_MINUTES.get(user.role, 30),
    )


async def rotate(db: AsyncSession, refresh_token: str, request: Request | None = None) -> TokenResponse:
    """Exchange a refresh token for a fresh pair, invalidating the one presented."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )

    session_id = payload.get("sid")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is not bound to a session"
        )

    session = await db.get(UserSession, uuid.UUID(session_id))
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    now = datetime.now(UTC)
    if session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired")

    if session.refresh_token_hash != hash_token(refresh_token):
        # A superseded token was replayed — assume it leaked and cut every session.
        await revoke_all(db, session.user_id)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions were signed out — please log in again.",
        )

    user = await db.get(User, session.user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    session.last_active_at = now
    if request is not None:
        session.ip_address = client_ip(request) or session.ip_address

    tokens = _mint(user, session)
    await db.commit()
    return tokens


async def touch(db: AsyncSession, session_id: uuid.UUID) -> None:
    session = await db.get(UserSession, session_id)
    if session and session.revoked_at is None:
        session.last_active_at = datetime.now(UTC)


async def list_sessions(db: AsyncSession, user: User) -> list[UserSession]:
    rows = await db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_active_at.desc())
    )
    return list(rows)


async def revoke(db: AsyncSession, user: User, session_id: uuid.UUID) -> None:
    session = await db.get(UserSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.revoked_at = datetime.now(UTC)


async def revoke_all(db: AsyncSession, user_id: uuid.UUID, except_session_id: uuid.UUID | None = None) -> int:
    query = select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id:
        query = query.where(UserSession.id != except_session_id)

    now = datetime.now(UTC)
    revoked = 0
    for session in await db.scalars(query):
        session.revoked_at = now
        revoked += 1
    return revoked


# --------------------------------------------------------------- trusted devices


async def is_trusted_device(db: AsyncSession, user: User, fingerprint: str | None) -> bool:
    """True when this device completed 2FA recently and the user allows the skip."""
    if not fingerprint or user.always_require_2fa:
        return False
    device = await db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user.id,
            TrustedDevice.device_fingerprint == fingerprint,
            TrustedDevice.revoked_at.is_(None),
        )
    )
    if device is None:
        return False
    if device.expires_at <= datetime.now(UTC):
        return False

    device.last_used_at = datetime.now(UTC)
    return True


async def trust_device(
    db: AsyncSession, user: User, fingerprint: str | None, user_agent: str | None
) -> TrustedDevice | None:
    if not fingerprint:
        return None

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.TRUSTED_DEVICE_DAYS)

    device = await db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user.id, TrustedDevice.device_fingerprint == fingerprint
        )
    )
    if device is None:
        device = TrustedDevice(
            organization_id=user.organization_id,
            user_id=user.id,
            device_fingerprint=fingerprint,
            device_name=describe_device(user_agent),
            last_used_at=now,
            expires_at=expires_at,
        )
        db.add(device)
    else:
        device.revoked_at = None
        device.last_used_at = now
        device.expires_at = expires_at
    return device


async def is_known_device(db: AsyncSession, user: User, fingerprint: str | None) -> bool:
    """Whether we have ever seen this device sign in — drives the new-device alert."""
    if not fingerprint:
        return False
    seen = await db.scalar(
        select(UserSession.id).where(
            UserSession.user_id == user.id, UserSession.device_fingerprint == fingerprint
        )
    )
    return seen is not None
