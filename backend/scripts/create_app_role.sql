-- Creates the restricted database role the application connects as.
--
-- Why this exists: PostgreSQL row-level security is bypassed by the role that
-- *owns* the tables. If the app connects as the owner, every policy in
-- `app/core/rls.py` evaluates to nothing and tenant isolation rests entirely on
-- the application remembering its WHERE clauses. This role does not own
-- anything, so the policies actually bind.
--
-- Two roles by design:
--   owner (e.g. `rentflow`)  — migrations, Celery workers, the M-Pesa callback.
--                              These legitimately read across organisations, so
--                              they keep the RLS bypass that ownership gives.
--   app   (`rentflow_app`)   — the API. Sees only the organisation that
--                              `get_org_context` bound to the transaction.
--
-- Run as the owner, against the application database:
--
--   psql "$DATABASE_URL" \
--     -v app_password="$(printf %s "$APP_DB_PASSWORD" | sed "s/'/''/g")" \
--     -f scripts/create_app_role.sql
--
-- APP_DB_PASSWORD comes from the environment. Never commit it, and never put a
-- literal password in this file — it is in version control.

-- `\gexec` rather than a DO block: psql does not substitute :variables inside
-- dollar-quoted strings, so the password would arrive as the literal text
-- ":'app_password'". `format(%L)` quotes and escapes it properly.
SELECT format('CREATE ROLE rentflow_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rentflow_app')
\gexec

-- Idempotent: re-running rotates the password rather than failing.
SELECT format('ALTER ROLE rentflow_app WITH LOGIN PASSWORD %L', :'app_password')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO rentflow_app', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO rentflow_app;

-- DML only. No DDL, no ownership: the point is that this role cannot escape
-- the policies, and an ALTER TABLE would let it.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rentflow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rentflow_app;

-- Tables created by future migrations must be reachable too, or the next
-- Alembic run silently locks the API out of a new table.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rentflow_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO rentflow_app;

-- Explicitly *not* granted: BYPASSRLS, SUPERUSER, CREATEDB, CREATEROLE.
-- Granting BYPASSRLS here would undo the entire point of the role.
