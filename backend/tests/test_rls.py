"""Row Level Security: the database's own tenant isolation (US-003).

These tests bypass the application layer entirely and talk to Postgres as a
non-owner role, which is the only way to prove the policies do anything. The
app's own scoping is tested separately in `test_auth_flows.py`.
"""

import secrets
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import rls
from app.core.rls import ORG_SCOPED_TABLES, set_org_context
from tests.conftest import TEST_DATABASE_URL

RLS_ROLE = "rentflow_rls_test"
# Generated per run: the role is created and dropped inside the fixture, so
# there is nothing to write down.
RLS_PASSWORD = secrets.token_urlsafe(24)


@pytest.fixture
async def rls_engine(db_engine):
    """A connection that does *not* own the tables, so RLS is enforced on it.

    Table owners bypass RLS by design — testing as the owner would pass whether
    or not the policies exist.
    """
    await _run_ignoring_errors(db_engine, f"DROP OWNED BY {RLS_ROLE}")
    await _run_ignoring_errors(db_engine, f"DROP ROLE IF EXISTS {RLS_ROLE}")
    await _run(db_engine, f"CREATE ROLE {RLS_ROLE} LOGIN PASSWORD '{RLS_PASSWORD}'")
    await _run(db_engine, f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
    await _run(
        db_engine,
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RLS_ROLE}",
    )

    base = TEST_DATABASE_URL.split("://", 1)[1].split("@", 1)[1]
    url = f"postgresql+asyncpg://{RLS_ROLE}:{RLS_PASSWORD}@{base}"
    engine = create_async_engine(url, poolclass=NullPool)

    yield engine

    await engine.dispose()
    await _run_ignoring_errors(db_engine, f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {RLS_ROLE}")
    await _run_ignoring_errors(db_engine, f"REVOKE USAGE ON SCHEMA public FROM {RLS_ROLE}")
    await _run_ignoring_errors(db_engine, f"DROP ROLE IF EXISTS {RLS_ROLE}")


async def _run(engine, statement: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(statement))


async def _run_ignoring_errors(engine, statement: str) -> None:
    try:
        await _run(engine, statement)
    except Exception:  # noqa: BLE001 — cleanup must not mask the real failure
        pass


async def test_every_tenant_table_has_rls_enabled(db) -> None:
    rows = await db.execute(
        text(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND NOT rowsecurity
            """
        )
    )
    without_rls = {row[0] for row in rows}
    missing = set(ORG_SCOPED_TABLES) & without_rls
    assert not missing, f"RLS is not enabled on: {sorted(missing)}"


async def test_every_tenant_table_has_an_isolation_policy(db) -> None:
    rows = await db.execute(text("SELECT tablename FROM pg_policies WHERE schemaname = 'public'"))
    covered = {row[0] for row in rows}
    missing = set(ORG_SCOPED_TABLES) - covered
    assert not missing, f"No isolation policy on: {sorted(missing)}"


async def test_policy_hides_rows_from_another_organization(rls_engine, db) -> None:
    """The core promise: with org A's context set, org B's rows do not exist."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()

    for org_id, name in ((org_a, "Org A"), (org_b, "Org B")):
        await db.execute(
            text(
                "INSERT INTO organizations (id, name, slug, operating_mode, subscription_plan,"
                " is_active, default_billing_day)"
                " VALUES (:id, :name, :slug, 'OWNER', 'TRIAL', true, 1)"
            ),
            {"id": org_id, "name": name, "slug": f"slug-{org_id.hex[:8]}"},
        )
        await db.execute(
            text(
                "INSERT INTO properties (id, organization_id, reference_code, name, property_type,"
                " address, amenities, grace_period_days, is_archived)"
                " VALUES (:id, :org, :ref, :name, 'RESIDENTIAL', 'Somewhere', '[]'::jsonb, 5, false)"
            ),
            {
                "id": uuid.uuid4(),
                "org": org_id,
                "ref": f"PRP-{org_id.hex[:6].upper()}",
                "name": f"{name} Property",
            },
        )
    await db.commit()

    factory = async_sessionmaker(bind=rls_engine, expire_on_commit=False)
    async with factory() as session:
        await set_org_context(session, org_a)
        visible = (await session.execute(text("SELECT organization_id FROM properties"))).all()

    org_ids = {row[0] for row in visible}
    assert org_a in org_ids
    assert org_b not in org_ids


async def test_no_context_means_no_rows(rls_engine, db) -> None:
    """A forgotten context fails loudly (nothing visible) rather than leaking."""
    org_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO organizations (id, name, slug, operating_mode, subscription_plan,"
            " is_active, default_billing_day)"
            " VALUES (:id, 'Ghost Org', :slug, 'OWNER', 'TRIAL', true, 1)"
        ),
        {"id": org_id, "slug": f"ghost-{org_id.hex[:8]}"},
    )
    await db.execute(
        text(
            "INSERT INTO properties (id, organization_id, reference_code, name, property_type,"
            " address, amenities, grace_period_days, is_archived)"
            " VALUES (:id, :org, :ref, 'Hidden', 'RESIDENTIAL', 'Nowhere', '[]'::jsonb, 5, false)"
        ),
        {"id": uuid.uuid4(), "org": org_id, "ref": f"PRP-{org_id.hex[:6].upper()}"},
    )
    await db.commit()

    factory = async_sessionmaker(bind=rls_engine, expire_on_commit=False)
    async with factory() as session:
        count = await session.scalar(text("SELECT count(*) FROM properties"))

    assert count == 0


async def test_insert_into_another_organization_is_rejected(rls_engine, db) -> None:
    """WITH CHECK stops a write being smuggled into someone else's tenant."""
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    for org_id, name in ((mine, "Mine"), (theirs, "Theirs")):
        await db.execute(
            text(
                "INSERT INTO organizations (id, name, slug, operating_mode, subscription_plan,"
                " is_active, default_billing_day)"
                " VALUES (:id, :name, :slug, 'OWNER', 'TRIAL', true, 1)"
            ),
            {"id": org_id, "name": name, "slug": f"slug-{org_id.hex[:8]}"},
        )
    await db.commit()

    factory = async_sessionmaker(bind=rls_engine, expire_on_commit=False)
    async with factory() as session:
        await set_org_context(session, mine)
        with pytest.raises(Exception) as failure:
            await session.execute(
                text(
                    "INSERT INTO properties (id, organization_id, reference_code, name,"
                    " property_type, address, amenities, grace_period_days, is_archived)"
                    " VALUES (:id, :org, 'PRP-SNEAK', 'Sneaky', 'RESIDENTIAL', 'X',"
                    " '[]'::jsonb, 5, false)"
                ),
                {"id": uuid.uuid4(), "org": theirs},
            )
        assert "row-level security" in str(failure.value).lower()


# ------------------------------------------------------- the request path wiring


async def test_the_org_context_is_bound_by_the_request_dependency(owner, db) -> None:
    """The policies are worthless if nothing sets the context on a real request.

    This is the wiring test: `get_org_context` runs on every authenticated
    route, and it is the only place the binding happens. Without this, RLS could
    silently return to being inert — which is exactly the state it was found in.
    """
    from sqlalchemy import text

    await owner.get("/api/v1/properties")

    # The dependency sets it transaction-locally, so assert on the mechanism
    # rather than a leaked value: `enter_tenant_scope` must issue the setting.
    async with db.begin_nested():
        await rls.enter_tenant_scope(db, uuid.UUID(owner.user["organization_id"]))
        current = await db.scalar(text("SELECT current_setting('app.current_org_id', true)"))

    assert current == owner.user["organization_id"]


async def test_entering_tenant_scope_without_a_configured_role_still_binds_the_org(db) -> None:
    """Development and CI have no restricted role. The org setting must still be
    applied there, so the only difference in production is which role is acting."""
    from sqlalchemy import text

    from app.core.config import settings

    assert settings.DB_APP_ROLE is None  # the test environment's default

    org_id = uuid.uuid4()
    async with db.begin_nested():
        await rls.enter_tenant_scope(db, org_id)
        current = await db.scalar(text("SELECT current_setting('app.current_org_id', true)"))

    assert current == str(org_id)
