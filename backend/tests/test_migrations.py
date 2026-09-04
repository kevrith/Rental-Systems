"""Guards that the Alembic migrations actually produce the schema the models expect.

Every other test builds its database with `Base.metadata.create_all`, which means
the migrations are never exercised. Two production-only breakages got through that
gap: the Phase 2 tables were created by a migration that forked off the same parent
as the RLS migration (so `alembic upgrade head` was ambiguous and never ran it), and
its enum types were declared with lowercase *values* while SQLAlchemy stores enum
*names*. Both are invisible to a create_all schema.

These tests run the real migration chain against a scratch database and compare the
result with the models.
"""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import settings
from app.core.database import Base
from app.core.rls import ORG_SCOPED_TABLES

# Enum columns whose Postgres type must accept exactly the Python member names.
ENUM_TYPES = {
    "disbursement_status": "app.models.agency:DisbursementStatus",
    "inspection_type": "app.models.inspection:InspectionType",
    "inspection_status": "app.models.inspection:InspectionStatus",
    "signature_status": "app.models.signature:SignatureStatus",
    "invoice_status": "app.models.billing:InvoiceStatus",
    "etims_status": "app.models.etims:EtimsStatus",
    "late_fee_type": "app.models.property:LateFeeType",
    "file_category": "app.models.file:FileCategory",
    "renewal_status": "app.models.renewal:RenewalStatus",
    "task_run_status": "app.models.task_run:TaskRunStatus",
}


def _sync_url(database: str) -> str:
    base, _, _ = settings.sync_database_url.rpartition("/")
    return f"{base}/{database}"


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@contextmanager
def _pointed_at(url: str):
    """Point Alembic at `url` for the duration of the block.

    `alembic/env.py` overwrites `sqlalchemy.url` from the app settings on every
    run, so setting it on the Config alone would silently migrate the developer's
    own database instead of the scratch one.
    """
    original = settings.DATABASE_URL_SYNC
    settings.DATABASE_URL_SYNC = url
    try:
        yield
    finally:
        settings.DATABASE_URL_SYNC = original


@pytest.fixture(scope="module")
def migrated_engine():
    """A scratch database built by running `alembic upgrade head`."""
    name = f"rentflow_mig_{uuid.uuid4().hex[:8]}"
    admin = create_engine(_sync_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')

    url = _sync_url(name)
    try:
        with _pointed_at(url):
            command.upgrade(_alembic_config(url), "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{name}' AND pid <> pg_backend_pid()"
            )
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
        admin.dispose()


def test_migrations_have_exactly_one_head():
    """A fork makes `alembic upgrade head` ambiguous, so a branch silently never runs."""
    script = ScriptDirectory.from_config(_alembic_config(_sync_url("postgres")))
    heads = script.get_heads()
    assert len(heads) == 1, f"Migration history has forked into {len(heads)} heads: {heads}"


def test_every_model_table_exists_after_migrating(migrated_engine):
    """A model with no migration works in tests and 500s in production."""
    migrated = set(inspect(migrated_engine).get_table_names())
    expected = set(Base.metadata.tables)
    missing = expected - migrated
    assert not missing, f"Models define tables no migration creates: {sorted(missing)}"


def test_enum_types_accept_the_python_member_names(migrated_engine):
    """SQLAlchemy stores enum *names*; a type built from values rejects every write."""
    import importlib

    with migrated_engine.connect() as conn:
        for type_name, target in ENUM_TYPES.items():
            module_path, _, attr = target.partition(":")
            enum_cls = getattr(importlib.import_module(module_path), attr)
            rows = conn.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = :name"
                ),
                {"name": type_name},
            )
            labels = {row[0] for row in rows}
            assert labels, f"Enum type {type_name} does not exist after migrating"

            expected = {member.name for member in enum_cls}
            assert labels == expected, (
                f"Enum {type_name} has labels {sorted(labels)} but SQLAlchemy writes " f"{sorted(expected)}"
            )


def test_every_org_scoped_table_has_rls_after_migrating(migrated_engine):
    """RLS added by a later migration must cover the tables added since."""
    with migrated_engine.connect() as conn:
        rows = conn.execute(text("SELECT tablename FROM pg_policies WHERE schemaname = 'public'"))
        covered = {row[0] for row in rows}
    missing = set(ORG_SCOPED_TABLES) - covered
    assert not missing, f"Migrated schema has no isolation policy on: {sorted(missing)}"
