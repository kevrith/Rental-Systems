# BI / warehouse export

**Status: built and real for the object-storage delivery path (Parquet
files, generated on a schedule, filed the same way every other generated
document is). Direct warehouse-native delivery (a scheduled load straight
into a customer's own BigQuery or Snowflake) is a documented extension
point, not built — it needs that customer's own warehouse credentials,
which this environment has no way to obtain or test against.**

## What exists

- **`ExportFormat.PARQUET`** — a third format alongside the existing CSV and
  Excel, on the same `POST /api/v1/vacancies/exports` endpoint every export
  already goes through. Nothing about the request/response shape is new;
  `export_format: "parquet"` is simply a value that was not previously
  accepted.
- **`app/services/export_service.to_parquet`** — columnar, Snappy-compressed.
  Deliberately *not* reusing the same cell-normalisation the CSV/Excel export
  uses (`_cell`, which turns `None` into `""` for a spreadsheet's benefit) —
  a warehouse needs a real null, not an empty string that turns a numeric
  column into a broken mixed-type one. Decimals become floats and UUIDs
  become strings (Arrow has no native type for either); real `date`/
  `datetime` values are left alone so Arrow infers a proper timestamp column
  a BI tool can filter and sort on natively, rather than a string it would
  have to re-parse first.
- **`Organization.bi_export_enabled`** — opt-in, off by default. Most
  customers have no data team to hand a Parquet file to; this avoids paying
  the cost of a weekly multi-dataset export job for every organisation on
  the platform when only a handful will ever use it. Settable through the
  existing `PATCH /api/v1/organizations/me` route (`ORG_MANAGE`-gated, same
  as every other organisation-wide setting).
- **`rentflow.run_bi_exports`** — a weekly scheduled task (Monday, after the
  existing monthly-export job's own slot) that, for every organisation with
  `bi_export_enabled`, builds and stores a Parquet file for **every**
  `ExportKind` (tenants, tenancies, payments, properties, units, invoices) —
  not just one curated dataset, since a warehouse team wants the same tables
  a person exporting a spreadsheet gets. Each run notifies the organisation's
  owner once, in-app and by email, rather than once per dataset.
- **Delivery today**: the generated files land in `StoredFile` — the exact
  same mechanism every other generated document (a lease, a receipt, an
  export a person requested by hand) already uses — and are listed at
  `GET /api/v1/vacancies/exports`, each with a signed, time-limited download
  URL. A customer's own scheduled job (a nightly cron, an Airflow DAG, a
  Fivetran/Airbyte connector configured to pull a URL) can poll that
  endpoint and pick up new files on its own cadence.

## What is not built, and why

**Direct delivery into a customer's own warehouse** — a scheduled `COPY
INTO` for Snowflake, a BigQuery load job, a write straight into an S3
bucket the customer controls — needs that customer's own credentials
(a Snowflake account + role, a BigQuery service account key, an S3 bucket
policy). This deployment does not hold any customer's warehouse
credentials today, has no UI for a customer to submit them, and — correctly
— should not invent a plausible-looking integration that has never been
exercised against a real warehouse. Building the object-storage delivery
path first, and pointing a customer's own ingestion tooling at the signed
URLs it already produces, is the same pattern `docs/procurement/email-deliverability.md`
uses for SPF/DKIM (real code for the part this environment can build and
test; a documented runbook, not fabricated code, for the part that needs
someone else's live credentials).

**The path to add native warehouse delivery, when a specific customer needs
it:**

1. Add per-organisation destination config (a new table or JSONB column —
   Snowflake account/role/warehouse, or a BigQuery dataset + service account
   key, or a destination S3 ARN) — encrypted the same way eTIMS credentials
   and other customer-owned secrets already are
   (`app/core/crypto.encrypt_for_org`).
2. Extend `run_bi_exports` with a per-organisation destination branch that
   loads the Parquet bytes into that destination instead of (or in addition
   to) `StoredFile`, using the vendor's own client library
   (`snowflake-connector-python`, `google-cloud-bigquery`, `boto3` for S3).
3. Test against that customer's actual sandbox/trial account before
   depending on it in production — there is no way to validate a warehouse
   integration without one.

## Verifying the object-storage path

```bash
# From backend/, against a running stack:
curl -X POST /api/v1/vacancies/exports \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"kind": "payments", "export_format": "parquet"}' \
  --output payments.parquet

python3 -c "import pyarrow.parquet as pq; print(pq.read_table('payments.parquet').schema)"
```

A schema listing real column types (`double`, `timestamp[us]`, `string`) —
not everything collapsed to `string` — is what confirms the null- and
type-preserving normalisation in `to_parquet` is working as intended, rather
than silently falling back to the CSV/Excel behaviour.
