import asyncio
import os
import secrets
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.rls import enable_statements
from app.main import app
from app.models.user import UserRole

# Tests run against a scratch database created and dropped per session, so they
# never touch the developer's working data.
TEST_DB_NAME = f"rentflow_test_{uuid.uuid4().hex[:8]}"


def _swap_database(url: str, name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


TEST_DATABASE_URL = _swap_database(settings.DATABASE_URL, TEST_DB_NAME)
ADMIN_DATABASE_URL = _swap_database(settings.DATABASE_URL, "postgres")


async def _create_database() -> None:
    admin = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.exec_driver_sql(f'CREATE DATABASE "{TEST_DB_NAME}"')
    await admin.dispose()

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # The schema comes from the models, but the RLS policies come from the
        # same source the migration uses — otherwise the RLS tests would be
        # checking policies that only exist in tests.
        for statement in enable_statements():
            await conn.execute(text(statement))
    await engine.dispose()


async def _drop_database() -> None:
    admin = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.exec_driver_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
    await admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> Generator[None, None, None]:
    """Create the scratch database once per run.

    Deliberately a *sync* fixture driving its own throwaway loop: asyncpg
    connections cannot cross event loops, and every other async fixture and test
    shares the per-test function loop. Owning a private loop here keeps the two
    from ever meeting.
    """
    asyncio.run(_create_database())
    yield
    asyncio.run(_drop_database())


@pytest_asyncio.fixture
async def db_engine(_database):
    # NullPool: every connection is opened and closed within the test's own event
    # loop, so no asyncpg connection is ever handed to a loop that didn't create it.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeAsyncRedis:
    """One shared fake Redis per test, patched into every module that holds a
    reference to the real client."""
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    for module in (
        "app.core.redis",
        "app.services.otp_service",
        "app.services.auth_service",
        "app.services.mpesa_service",
        "app.services.api_key_service",
    ):
        monkeypatch.setattr(f"{module}.redis_client", client, raising=False)
    return client


@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point file storage at a temp directory and reset the cached backend."""
    from app.services import storage_service

    storage_service.get_storage.cache_clear()
    monkeypatch.setattr(settings, "LOCAL_STORAGE_DIR", str(tmp_path / "uploads"))
    yield
    storage_service.get_storage.cache_clear()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------- credentials

# Test credentials are generated per run, never written down. They exist only
# for a scratch database that is dropped when the run ends, and no literal
# password belongs in a committed file.
TEST_PASSWORD = os.environ.get("TEST_PASSWORD") or f"pw-{secrets.token_urlsafe(16)}"


def fresh_password() -> str:
    """A distinct password, for tests that need to change or compare one."""
    return f"pw-{secrets.token_urlsafe(16)}"


# ------------------------------------------------------------------------ helpers


class Actor:
    """A logged-in user plus a client pre-loaded with their bearer token."""

    def __init__(self, client: AsyncClient, tokens: dict[str, Any], user: dict[str, Any]):
        self.client = client
        self.tokens = tokens
        self.user = user

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    async def get(self, url: str, **kwargs):
        return await self.client.get(url, headers=self.headers, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.client.post(url, headers=self.headers, **kwargs)

    async def patch(self, url: str, **kwargs):
        return await self.client.patch(url, headers=self.headers, **kwargs)

    async def put(self, url: str, **kwargs):
        return await self.client.put(url, headers=self.headers, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self.client.delete(url, headers=self.headers, **kwargs)


_counter = 0


def unique_suffix() -> str:
    global _counter
    _counter += 1
    return f"{uuid.uuid4().hex[:6]}{_counter}"


def unique_phone() -> str:
    """A distinct, valid Kenyan mobile number per call.

    Phone numbers are globally unique in `users`, and the test database is shared
    across the whole run, so a counter — not randomness — is what guarantees no
    collision.
    """
    global _counter
    _counter += 1
    return f"+2547{_counter:08d}"


async def register_owner(client: AsyncClient, *, organization_name: str = "Acacia Rentals") -> Actor:
    suffix = unique_suffix()
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Wanjiru",
            "organization_name": f"{organization_name} {suffix}",
            "email": f"owner-{suffix}@example.com",
            "phone_number": unique_phone(),
            "password": TEST_PASSWORD,
            "account_type": "owner",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return Actor(client, data["tokens"], data["user"])


@pytest.fixture
async def owner(client: AsyncClient) -> Actor:
    return await register_owner(client)


@pytest.fixture
async def other_owner(client: AsyncClient) -> Actor:
    """A second, unrelated organization — the counterparty in isolation tests."""
    return await register_owner(client, organization_name="Rival Holdings")


@pytest.fixture
def owner_role() -> UserRole:
    return UserRole.OWNER
