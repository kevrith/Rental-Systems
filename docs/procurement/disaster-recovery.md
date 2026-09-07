# Disaster recovery — RPO, RTO, and the runbook

**Status: backups and a weekly automated restore drill exist and run today
(`infra/backup/`). The figures below are honest current-state targets, not a
benchmarked SLA — the "how to confirm" column says what would upgrade a
figure from "target" to "measured."** A security questionnaire that asks for
RPO/RTO gets real numbers grounded in what actually runs, not aspirational
ones — see `docs/procurement/security-questionnaire-answers.md`'s own
discipline of naming a gap rather than answering around it.

## What this covers, and what it deliberately doesn't

Two different things sit behind "our data," with two different recovery
stories:

- **The Postgres database** — every tenant, tenancy, invoice, payment, audit
  log — is backed up **by RentFlow**, on a schedule RentFlow controls
  (`infra/backup/backup.sh`). This document's RPO/RTO figures are about this.
- **Uploaded documents** (KYC photos, signed leases, generated receipts) live
  in Cloudflare R2 in production, not on a RentFlow-run disk. Their durability
  is R2's own guarantee (Cloudflare states eleven nines), not something this
  document can add to — RentFlow's job here is only to *point at the right
  key*, which is what the database backup already protects (`StoredFile` rows
  hold the R2 object key; losing that database row would make an otherwise-
  intact R2 object unreachable, which is exactly why the database is the
  thing with an RPO/RTO at all). The local-disk storage backend
  (`LocalStorageBackend`) is a development-only fallback and is out of scope
  for this document entirely — it is never used in production.

## RPO — Recovery Point Objective

| | Target | Why | How to confirm it's real |
|---|---|---|---|
| Database | **24 hours** | `backup.sh` runs once nightly (`rentflow-backup.timer`, 02:15 UTC) — the worst case is losing everything written since the previous night's dump. | `systemctl list-timers 'rentflow-*'` on the production host, and check the newest object in the backup destination bucket is less than 24h old. |
| Uploaded documents | Effectively continuous | Each upload is written to R2 synchronously, on the request path — there is no batch/nightly step to lag behind. | N/A — this is R2's own durability guarantee, not a RentFlow process. |

**24 hours is a real, current gap, not a target this document is
pretending is smaller.** The honest next step, if a customer's contract needs
a tighter RPO than that, is continuous WAL archiving (Postgres point-in-time
recovery) rather than a nightlier `pg_dump` schedule — `pg_dump` more than
once or twice a day starts costing meaningful I/O on the primary for
diminishing benefit; WAL shipping is the standard answer once sub-hour RPO is
actually required by a customer, and is not built today. Naming this here
rather than quietly shipping a 24-hour RPO under a document that doesn't say
so is the point of this document existing.

## RTO — Recovery Time Objective

| Scenario | Target | Basis |
|---|---|---|
| Restore the database from the latest backup, from scratch | **Under 1 hour** | `restore.sh` decrypts, verifies the checksum, and restores a single `pg_dump` archive — mechanically a bounded, single-command operation. The weekly drill (`rentflow-restore-check.timer`) exercises exactly this path against a throwaway database every Sunday, so the mechanism itself is proven to work; what is not yet true is a *timed* run against production-scale data volume. |
| Full application recovery (database restored, app redeployed, DNS/traffic pointed at it) | **Under 4 hours** | Database restore (above) plus a from-scratch deploy of `backend`/`frontend` from their Dockerfiles, which is itself untimed against a cold environment today. |

**Both RTO figures are targets pending a timed drill, not measured
results.** The mechanism is proven weekly (the restore drill runs and is
verified); the *clock* has not been run end-to-end against a fresh
environment standing in for "production just disappeared." The concrete next
step — cheap, and worth doing before quoting these numbers to a customer as
anything firmer than a target — is timing one full drill: spin up a bare
Docker host, run `restore.sh --latest`, deploy both images, and record how
long it actually took. Until that has been done at least once, treat these as
engineering estimates, not commitments.

## Runbook — what actually happens

This is the piece `docs/procurement/soc2-readiness.md` (CC7) names as a gap:
a breach has its own 72-hour-clock process (`app/services/breach_service.py`),
but a plain operational disaster — the database host dies, a bad deploy
corrupts data, the hosting provider has an outage — had no written steps
before this document.

1. **Confirm it's real and get the scope.** Is the database unreachable,
   corrupted, or just slow? Check the app's own `/api/v1/health` endpoint and
   the hosting provider's status page before assuming the worst — a restore
   is not the right first move for a problem that isn't actually data loss.
2. **Stop writes.** Take the API out of rotation (or scale workers to zero)
   before restoring into the same database name — a restore racing against
   live traffic is how a recoverable incident becomes an unrecoverable one.
3. **Restore.** `./infra/backup/restore.sh --latest` against the target
   database. Use `--verify` first against a scratch database if there is any
   doubt about which backup is the right one, rather than restoring twice.
4. **Verify before reopening traffic**: Alembic head matches
   (`alembic current`), row counts on a couple of high-traffic tables look
   sane (`tenants`, `payments`), and a login actually works end-to-end.
5. **Reopen traffic**, then immediately:
6. **Assess data loss.** Compare the backup's timestamp against when the
   incident started — that gap is what was lost, and it needs to be stated
   plainly to affected customers, not discovered later. This is a distinct
   step from the Kenya DPA breach process (`breach_service.py`) unless the
   *cause* of the incident was itself a security breach, in which case both
   processes run together.
7. **Write it up.** What happened, what was lost, what changed to reduce the
   chance of a repeat — the same discipline the penetration-testing policy
   already asks for ("a finding with no remediation date is not actually
   addressed").

## Expand/contract migration discipline — zero-downtime deploys

The other half of "disaster recovery" that a mature buyer asks about is
routine: does a normal deploy risk taking the system down? RentFlow's
Alembic migrations already follow an expand/contract pattern for anything
that isn't purely additive — this section makes the convention explicit
rather than leaving it to be inferred from reading past migrations.

**The rule: a migration that runs at the same moment old and new application
code might both be live (any rolling or blue/green deploy) must never make a
change the *old* code cannot tolerate.** In practice:

- **Adding a column** — always additive: nullable, or with a server-side
  default, never `NOT NULL` with no default against an existing table with
  rows. The old code simply doesn't know the column exists yet, which is fine.
- **Renaming or changing the type of a column the app reads or writes** —
  never in one step. Add the new column, backfill it (a one-off script, not
  the migration itself — see `backend/scripts/backfill_national_id_encryption.py`
  for a worked example from Sprint 26A), deploy application code that reads
  the new column and writes both, then — in a **later, separate** migration,
  once every environment is confirmed backfilled — drop the old column. The
  encrypted-national-ID change and the earlier eTIMS credential migration both
  follow exactly this shape.
- **Dropping a column or table** — only after a deploy has shipped that no
  longer references it. Dropping it in the *same* migration that removes the
  application code's last reference means the old (still-running, during a
  rolling deploy) process instances break the moment the migration runs,
  before they've been replaced.
- **Renaming an enum label** — Postgres cannot drop an enum value, so this
  codebase's convention (see the Sprint 20 and Sprint 26 migration docstrings)
  is to add the new label and leave the old one in place, unreferenced, rather
  than attempt a rename. A label nothing writes any more is harmless; a failed
  attempt to remove one mid-deploy is not.

A migration that violates this is not a "will probably be fine" — a rolling
deploy runs old and new code against the same schema for a window measured in
minutes, and every migration in this codebase should be safe to leave that
window open indefinitely, not just survive it by luck.
