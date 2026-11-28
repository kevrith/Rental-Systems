"""How long a sign-in lasts: a week for staff, thirty days for tenants."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.models.session import UserSession
from tests.conftest import Actor, unique_phone
from tests.test_sprint25 import accept_portal_invite
from tests.test_tenancy import make_tenant


async def _session_of(db: AsyncSession, refresh_token: str) -> UserSession:
    claims = decode_token(refresh_token)
    assert claims is not None
    session = await db.get(UserSession, uuid.UUID(claims["sid"]))
    assert session is not None
    return session


def _days_from_now(moment: datetime) -> float:
    return (moment - datetime.now(UTC)).total_seconds() / 86400


async def test_a_tenant_stays_signed_in_for_thirty_days(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    tenant = await make_tenant(owner, phone_number=unique_phone())
    portal = await accept_portal_invite(owner, client, db, tenant["id"])

    session = await _session_of(db, portal.tokens["refresh_token"])
    assert abs(_days_from_now(session.expires_at) - settings.TENANT_SESSION_DAYS) < 0.01

    # The refresh token itself agrees, and so does the next one after a refresh.
    claims = decode_token(portal.tokens["refresh_token"])
    assert abs(_days_from_now(datetime.fromtimestamp(claims["exp"], UTC)) - 30) < 0.01
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": portal.tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    again = decode_token(refreshed.json()["refresh_token"])
    assert abs(_days_from_now(datetime.fromtimestamp(again["exp"], UTC)) - 30) < 0.01

    # The thirty days run from sign-in; refreshing does not stretch the session.
    await db.refresh(session)
    assert abs(_days_from_now(session.expires_at) - settings.TENANT_SESSION_DAYS) < 0.01


async def test_staff_sessions_still_last_a_week(owner: Actor, db: AsyncSession) -> None:
    session = await _session_of(db, owner.tokens["refresh_token"])
    assert abs(_days_from_now(session.expires_at) - settings.REFRESH_TOKEN_EXPIRE_DAYS) < 0.01
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7


async def test_a_tenant_session_ends_when_its_thirty_days_are_up(
    client: AsyncClient, owner: Actor, db: AsyncSession
) -> None:
    tenant = await make_tenant(owner, phone_number=unique_phone())
    portal = await accept_portal_invite(owner, client, db, tenant["id"])
    session = await _session_of(db, portal.tokens["refresh_token"])

    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    expired = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": portal.tokens["refresh_token"]}
    )
    assert expired.status_code == 401
