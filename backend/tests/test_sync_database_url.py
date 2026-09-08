"""
`sync_database_url` is what Alembic connects with, and both URLs behind it are
typed by hand into the Render dashboard. Pasting the asyncpg URL into
DATABASE_URL_SYNC used to hand Alembic an async engine, which failed at boot
with `MissingGreenlet: greenlet_spawn has not been called` — an error that
names neither the setting nor the URL.
"""

import pytest

from app.core.config import Settings


def _settings(**overrides: str | None) -> Settings:
    # DATABASE_URL_SYNC is pinned to None rather than left out: pydantic-settings
    # would otherwise read it from the real environment, and the fallback case
    # would quietly test whatever the developer or CI happened to export.
    base: dict[str, str | None] = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@db:5432/rentflow",
        "DATABASE_URL_SYNC": None,
        "SECRET_KEY": "x" * 32,
        "REDIS_URL": "redis://localhost:6379/0",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "sync_url",
    [
        "postgresql+asyncpg://u:p@db:5432/rentflow",
        "postgresql://u:p@db:5432/rentflow",
        "postgres://u:p@db:5432/rentflow",
        "postgresql+psycopg2://u:p@db:5432/rentflow",
    ],
)
def test_always_yields_a_sync_driver(sync_url: str) -> None:
    """Whatever driver was supplied, Alembic must get psycopg2."""
    assert _settings(DATABASE_URL_SYNC=sync_url).sync_database_url.startswith("postgresql+psycopg2://")


def test_falls_back_to_the_async_url_with_the_driver_swapped() -> None:
    assert _settings().sync_database_url == "postgresql+psycopg2://u:p@db:5432/rentflow"


def test_leaves_a_percent_encoded_password_byte_for_byte_alone() -> None:
    """
    Supabase passwords routinely contain characters that arrive percent-encoded.
    Only the scheme is rewritten, so the credentials survive untouched.
    """
    settings = _settings(DATABASE_URL_SYNC="postgresql+asyncpg://u:p%40ss%2Fword@db:5432/rentflow")

    assert settings.sync_database_url == ("postgresql+psycopg2://u:p%40ss%2Fword@db:5432/rentflow")


def test_preserves_query_parameters() -> None:
    settings = _settings(DATABASE_URL_SYNC="postgresql+asyncpg://u:p@db:5432/rentflow?sslmode=require")

    assert settings.sync_database_url.endswith("/rentflow?sslmode=require")


def test_leaves_a_non_postgres_url_untouched() -> None:
    """Nothing to rewrite, and guessing would be worse than passing it through."""
    assert _settings(DATABASE_URL_SYNC="sqlite:///./test.db").sync_database_url == ("sqlite:///./test.db")
