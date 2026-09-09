# Database roles: making row-level security actually bind

**Status:** required for production. Optional in development and CI.

## The problem this solves

`backend/app/core/rls.py` defines row-level security policies on every
tenant-owned table. They are correct, and `tests/test_rls.py` proves it.

They were also, until this was wired up, doing nothing in the running
application — because **a table's owner bypasses RLS**. The API connected as
`rentflow`, which owns the tables, so every policy evaluated to nothing:

```
app connects as:        rentflow
payments table owner:   rentflow          ← the same role
rowsecurity: t, forced: f                 ← owners bypass unless FORCED
rows visible with no org context:  663    ← every organisation's payments
```

Tenant isolation rested entirely on the application remembering an
`organization_id` filter in every query. That is tested and was not found
leaking, but it is a single layer: one missed `WHERE` clause in future work
becomes a cross-tenant data leak with nothing behind it.

## How it works now

Authenticated requests drop to an unprivileged role **for the duration of the
transaction**, in `get_org_context` — the one dependency every authenticated
route passes through:

```python
await rls.enter_tenant_scope(db, organization.id)
#   SELECT set_config('app.current_org_id', <org>, true)
#   SET LOCAL ROLE rentflow_app
```

`SET LOCAL` unwinds when the transaction ends, so a pooled connection is never
handed to the next request still wearing the restricted role.

### Why not a second connection pool

Because a great deal of legitimate work is cross-organisation and never passes
through `get_org_context`:

- **logging in** — the user is found by email before any organisation is known
- **Safaricom's M-Pesa callback** — unauthenticated, matched on checkout id
- **Paystack's webhook** — likewise
- **Celery sweeps** — invoicing, reminders, the subscription biller, retention
- **platform staff routes** — `require_platform_staff` reads across every tenant
  by design

All of those keep the owner connection and its reach, with no second engine and
no rewrite of every `Depends(get_db)`.

## Setting it up

Once per environment, as the owner:

```bash
export APP_DB_PASSWORD="$(openssl rand -base64 32)"   # store it in your secret manager

psql "$DATABASE_URL" \
  -v app_password="$APP_DB_PASSWORD" \
  -f backend/scripts/create_app_role.sql

# Let the owner switch into it for the duration of a request transaction.
psql "$DATABASE_URL" -c "GRANT rentflow_app TO rentflow;"
```

Then set in the backend environment:

```
DB_APP_ROLE=rentflow_app
```

`DATABASE_URL` stays pointed at the **owner** — the role switch happens
per transaction, not per connection.

Leaving `DB_APP_ROLE` unset (the default) skips the switch entirely, which is
what development and CI want: `SET ROLE` to a role that does not exist would
turn every authenticated request into a 500.

## Verifying it

After deploying, confirm the policies bite:

```sql
-- As the app role, with no context: must be 0.
SET ROLE rentflow_app;
SELECT count(*) FROM payments;

-- With a context: only that organisation's rows.
SELECT set_config('app.current_org_id', '<some-org-uuid>', false);
SELECT count(*) FROM payments;
RESET ROLE;
```

If the first query returns rows, the role owns the tables or holds `BYPASSRLS`,
and isolation is not being enforced.

## After every migration

New tables are covered by `ALTER DEFAULT PRIVILEGES` in the setup script, so
`rentflow_app` can read and write them automatically. But a new tenant-owned
table still needs its **policy**, which is the migration's job — add it to the
right `PHASE_*_ORG_SCOPED_TABLES` tuple in `rls.py` and call
`enable_table_statements` in the migration, as the existing ones do.

A table left out of that list has no policy, which means the restricted role can
read every organisation's rows in it.
