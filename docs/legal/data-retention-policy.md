# Data retention policy

**Status:** policy defined here; enforcement built in Sprint 26A
(`app/services/retention_service.py`, the `sweep-data-retention` scheduled
task). See that service's own docstring for the mechanics; this document is
the *policy* the code enforces, and the place to change a retention period
without reading code first.

## Why retention needs a policy, not just erasure

`app/services/privacy_service.py` already lets a tenant request their
personal data be erased on demand — but "on demand" is not the same as "on
schedule." Nothing before Sprint 26A ever proactively removed old data on its
own, which means a landlord who stopped using the platform three years ago is
still, today, sitting on national ID numbers and phone numbers for tenants
who moved out in 2023. That is a real Kenya DPA 2019 exposure (data kept
longer than necessary for the purpose it was collected for), independent of
whether anyone ever asks for it to be deleted.

## Retention periods

| Data category | Retention period | Basis | Enforcement |
|---|---|---|---|
| **Financial records** — invoices, payments, receipts | **7 years** from the transaction date | Kenya Tax Procedures Act, 2015, s.23 — records supporting a tax return must be kept 5 years from the end of the relevant year; 7 years is used as a rounded, conservative floor covering the longest reasonably arguable limitation period | Never auto-purged. Financial records are the one category `privacy_service.py`'s own erasure explicitly refuses to touch, and the retention sweep does not touch them either. |
| **Audit logs** | **7 years** | Matches the financial record period — an audit log entry for a payment is only as useful as the payment record it explains | Never auto-purged within the window; see `docs/data-model.md` for the hash-chained audit log (Sprint 26A), which makes "delete inconvenient history" detectable even if attempted. |
| **Tenant personal data — active or recently-ended tenancy** | Kept for the life of the tenancy, plus **2 years** after it ends | A landlord defending or bringing a claim over a tenancy typically needs to reach the tenant or reference their record within this window; 2 years is a conservative alignment with the general contract limitation period under the Kenya Limitation of Actions Act | Automated sweep, monthly — see below. |
| **Screening/application data for a rejected or abandoned application** | **1 year** from the application decision | No ongoing relationship exists to justify longer retention; a year covers a reasonable dispute window | Automated sweep, monthly. |
| **Security events, failed-login records** | **1 year** | Long enough to investigate a pattern noticed months later; short enough not to become its own liability | Automated sweep, monthly. |
| **Uploaded documents (KYC photos, signed leases)** | Tied to the record they support — see above | A lease document is meaningless once its tenancy record is gone | Deleted alongside the tenant/tenancy record it belongs to, via `storage_service`. |
| **Sample/demo data** (Sprint 26A) | Deleted whenever the seeding organisation removes it, or automatically after **30 days** if never explicitly removed | Demo data is fabricated and has no retention justification at all | Existing `DemoDataset` teardown, plus a new sweep for abandoned demo datasets. |

## Legal hold

A landlord facing litigation, a regulatory inquiry, or a live dispute with a
specific tenant needs to be able to say "do not delete anything related to
this" — overriding the retention schedule above, including erasure requests
that would otherwise proceed. This is implemented as `LegalHold`
(`app/models/legal_hold.py`, Sprint 26A):

- A hold is placed against a specific entity (a tenant, a tenancy, or an
  entire organisation for a broader matter) with a required reason.
- While a hold is active, both the retention sweep and tenant-initiated
  erasure (`privacy_service.py`) refuse to act on anything the hold covers —
  the erasure endpoint returns a clear "this record is under legal hold and
  cannot be erased while it is active" rather than silently succeeding or
  silently failing.
- A hold must be explicitly released (with who released it and when
  recorded) before normal retention resumes. A hold does not expire on its
  own — an open legal matter does not have a schedule the software can know.

## What "automated sweep" actually does

The monthly `sweep-data-retention` task does not hard-delete rows the moment
a period lapses — it follows the same pattern `privacy_service.py`'s erasure
already established: personal fields are redacted (name, phone, national ID,
email, notes, uploaded documents), while the row itself and any financial or
audit trail it is linked to survive, because those are on their own,
independent 7-year clock. This means "retention ran" and "the tenant asked to
be erased" converge on the same end state, which is what makes both paths
safe to test against the same expectations.

## Reviewing this policy

Review whenever a new data category is added to the schema, and at minimum
annually. A retention period that was right when the company had ten
customers may not be right at a thousand — but changing a period here is a
policy decision, not a code change, and should be made by whoever owns
compliance at the time, informed by legal advice specific to that decision.
