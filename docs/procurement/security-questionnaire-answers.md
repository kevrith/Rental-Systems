# Security questionnaire — pre-written answers

**Last reviewed:** 2026-09-07 (Sprint 26A) · **Owner:** Kelvin

A standard reference for filling out a customer's vendor security
questionnaire (SIG Lite, CAIQ, or a bespoke procurement form) without
re-deriving every answer from the codebase each time. Organised by the
categories these forms almost always ask about. Every answer states what is
actually true today — where something is not yet in place, that is stated
plainly rather than answered around, consistent with `docs/owasp-top-10-checklist.md`'s
own convention of naming gaps rather than hiding them.

Cross-referenced source files are given so an answer can be re-verified
against the code rather than trusted blind.

---

## Company & compliance

**Q: Are you SOC 2 certified?**
Not yet. See `docs/procurement/soc2-readiness.md` for our control mapping and
timeline. [Fill in target date once an auditor is engaged.]

**Q: Have you had a third-party penetration test?**
Not yet. See `docs/procurement/penetration-testing-policy.md` for our policy
and scope. [Fill in date once scheduled/completed.]

**Q: Do you have a written information security policy?**
Partial — see the SOC 2 readiness gap list. A formal, employee-signed policy
is one of the named gaps to close before a SOC 2 Type I audit.

**Q: Who is your Data Protection Officer / privacy contact?**
[FILL IN — the Kenya DPA 2019 requires a designated contact for larger
processing operations; confirm whether this company currently meets that
threshold and, if so, appoint one.]

---

## Data handling

**Q: What personal data do you process, and why?**
Tenant and property-owner PII (name, phone, national ID, email, address),
payment and lease records, and operational data (maintenance requests,
inspection reports, meter readings) needed to run a rental management
platform. Full detail: `docs/legal/data-processing-agreement-template.md`,
§3.

**Q: Is data encrypted in transit?**
Yes — TLS on every public endpoint (enforced at the reverse proxy in
production).

**Q: Is data encrypted at rest?**
- **Database** — at the storage layer, via the managed Postgres provider's
  disk encryption (a hosting-provider control, not application code — confirm
  this is enabled on whichever provider is actually used in production).
- **Third-party credentials held on a customer's behalf** (eTIMS device keys,
  property-portal API keys, accounting OAuth tokens, webhook signing
  secrets) — encrypted at the **application layer**, per-organisation, so
  that decrypting one customer's stored credential requires that customer's
  own key, not a platform-wide master key (`app/core/crypto.py`,
  `encrypt_for_org`/`decrypt_for_org`). A leaked database export cannot be
  used to decrypt every customer's credentials with one key.
- **General PII fields** (a tenant's phone number, address) are not
  field-level encrypted beyond the database's own at-rest encryption — see
  the field-level PII encryption note below.

**Q: Do you support field-level encryption of sensitive data?**
Yes, for the highest-sensitivity identifier: a tenant's national ID number is
encrypted at the application layer with a per-organisation key, with a
one-way HMAC "blind index" maintained alongside it so exact-match duplicate
detection still works without ever decrypting the stored value for that
comparison (`app/models/tenant.py`, `national_id_encrypted` /
`national_id_blind_index` — see `docs/data-model.md`, "Sprint 26A" for the
detail, including the deliberate tradeoff this makes against partial-text
search). The same mechanism is available for other fields; national ID was
prioritised as the single most sensitive identifier the platform stores.

**Q: How is data isolated between customers (multi-tenancy)?**
Two independent layers: application-level scoping on every query
(`app/api/deps.OrgContext`), and PostgreSQL Row Level Security as a second,
database-enforced lock — so a missed `WHERE` clause in application code
still cannot return another tenant's rows (`app/core/rls.py`; full detail in
`docs/data-model.md`, "Multi-tenant isolation strategy"). A cross-tenant
access attempt returns 403, never 404, so a caller also cannot use response
codes to enumerate whether another tenant's record exists.

**Q: What is your data retention policy?**
See `docs/legal/data-retention-policy.md`. [Confirm this exists and is
current before answering further than the reference — Sprint 26A adds
scheduled retention and legal hold; verify the sweep is actually running in
production before claiming enforcement.]

**Q: Can a customer export or delete their data?**
Yes. Tenant-initiated export and erasure exist today (`app/services/privacy_service.py`)
— export bundles a tenant's full record with signed, time-limited document
links; erasure redacts personal fields while retaining financial and audit
records Kenyan tax and accounting law require be kept. An organisation-level
full export/deletion path (for offboarding a whole customer) should be
confirmed against the current `internal.py`/organization endpoints before
this answer is given as unqualified.

---

## Access control & authentication

**Q: What authentication methods do you support?**
Password + mandatory SMS OTP second factor for new devices, with optional
WebAuthn/passkey as an alternative second factor
(`app/services/webauthn_service.py`). Refresh tokens rotate on every use with
reuse detection — presenting a superseded refresh token revokes every
session for that user, on the assumption the token leaked
(`app/services/session_service.py`).

**Q: Do you support single sign-on (SSO/SAML)?**
Not yet. Scoped for a future sprint (masterplan Phase 5, "Enterprise Identity
& Access"). [Update once built.]

**Q: How is access controlled internally (role-based access control)?**
Yes — a fixed role-permission matrix (`app/core/permissions.py`), enforced on
every endpoint via a dependency (`app.api.deps.require`). Caretaker roles are
additionally scoped to their assigned properties only. Platform staff access
(RentFlow's own team reading across every customer) is a distinct gate
(`require_platform_staff`), separate from any customer's own role system.

**Q: Do you enforce multi-factor authentication?**
Yes, for staff/operator accounts, by default (SMS OTP unless a device is
explicitly trusted, or WebAuthn). Not currently enforced for the tenant
portal, which authenticates by password or a single-use magic link rather
than a persistent account a tenant manages day-to-day.

**Q: Do you limit concurrent sessions?**
Yes — a configurable per-organisation cap; the oldest session is revoked when
a new login would exceed it (`app/services/session_service.py`,
`enforce_session_cap`, Sprint 26A).

**Q: What happens when an employee/user is offboarded?**
Account deactivation and session revocation are supported per-user
(`app/api/v1/endpoints/team.py`). [Confirm whether a documented internal
offboarding checklist exists for RentFlow's own staff — this is one of the
SOC 2 readiness gaps.]

---

## Application security

**Q: Do you conduct static analysis / dependency vulnerability scanning?**
Yes, on every code change: `pip-audit` and `npm audit` against pinned
dependencies, a Trivy scan of both container images for known OS and
dependency CVEs, and CodeQL static analysis across both languages
(`.github/workflows/ci.yml`, the `supply-chain`, `trivy` and `codeql` jobs),
each failing the build — rather than only filing a notification — on a
critical or high-severity finding with a known fix.

**Q: What is your test coverage?**
Backend: [current measured %, see `backend/pyproject.toml`'s coverage
report] with an enforced CI floor that ratchets upward as coverage improves.
Frontend: [current measured %, see `frontend/vitest.config.ts`] over the
logic layer (formatting, the API client, the offline queue, shared UI
primitives), plus a Playwright end-to-end suite covering account
registration and the payment-recording flow against a real backend
(`frontend/e2e/`). State the actual current numbers here rather than a fixed
figure — they change every sprint; do not let this document go stale by
hardcoding a percentage.

**Q: Do you rate-limit your API?**
Yes — per authenticated user and per IP for unauthenticated traffic, with a
tighter ceiling on endpoints that cost real money per call (SMS, PDF
rendering, AI model calls) (`app/core/rate_limit.py`). The public developer
API is separately metered against each customer's own quota.

**Q: How do you handle secrets (API keys, credentials) in your codebase?**
Never committed — every secret is an environment variable, `.env` files are
git-ignored, and the codebase's own development standards explicitly forbid
hardcoded credentials in source, docs, or test fixtures.

**Q: Do you have a responsible disclosure / bug bounty program?**
Not formally established. [If a security contact email exists, name it here;
otherwise this is a gap worth closing cheaply — a `security.txt` and a
monitored inbox cost little and are commonly asked about.]

---

## Logging & monitoring

**Q: Do you have centralized logging?**
Structured JSON logging with a correlation id (`request_id`) on every log
line, tying together an API request, its downstream database queries, and
any Celery task it triggers (`app/core/logging.py`,
`app/core/request_context.py`, Sprint 26A). Whether logs are actually
shipped to a centralized aggregator (vs. read from the host) is an
infrastructure/deployment decision — confirm the production log destination
before answering this as fully satisfied.

**Q: Do you have distributed tracing / APM?**
Yes — OpenTelemetry instrumentation across the API, the database layer and
outbound HTTP calls, exportable to any OTLP-compatible backend
(`app/core/observability.py`, Sprint 26A). Inert until an OTLP endpoint is
configured in production.

**Q: Is your audit trail tamper-evident?**
Yes — every audit log entry is hash-chained per organisation
(`audit_logs.prev_hash` / `.entry_hash`, Sprint 26A), using the same HMAC
construction that already signs payment receipts
(`app/core/security.sign_payload`, keyed by a server-side secret, not derived
from the row data alone). Altering or deleting any row breaks every hash
after it, and doing so undetectably would require the signing key, not just
database write access. `GET /api/v1/security/audit-log/verify` recomputes the
chain from the stored rows on demand; see `app/services/audit_chain_service.py`.

**Q: Do you monitor for security incidents?**
Yes — error tracking via Sentry with PII scrubbing on every event
(`send_default_pii=False` plus an explicit request-body/header scrub,
`app/core/observability.py`), and an automated breach-candidate detector
(credential-stuffing patterns, abnormal data-export volume) that raises a
tracked incident for human review (`app/services/breach_service.py`, Sprint
26A). Automated detection covers known patterns; it is not a substitute for
a SOC or managed detection service, which this company does not currently
operate.

---

## Incident response & breach notification

**Q: What is your data breach notification process and timeline?**
A tracked breach register with a 72-hour notification clock, matching the
Kenya Data Protection Act 2019 section 43 standard, with automatic
escalation to platform staff at 48 and 72 hours if the Data Commissioner has
not yet been notified (`app/services/breach_service.py`). Affected customers
are notified within 48 hours internally (see the DPA template, §7), giving
them time within the 72-hour window to prepare their own notification to
their tenants, since they — not RentFlow — are the Controller responsible
for that notification.

**Q: Do you have a documented incident response plan for non-breach
incidents (outage, data corruption)?**
Partial. Backup and a tested restore drill exist (`infra/backup/`). A
general incident-response runbook beyond the breach-specific process is a
named gap — see `docs/procurement/soc2-readiness.md`, CC7.

---

## Business continuity & disaster recovery

**Q: What are your RPO and RTO?**
See `docs/procurement/disaster-recovery.md`. [Confirm this document exists
and states real, tested figures before quoting numbers here — do not restate
a target as if it were a measured result.]

**Q: How often do you test your backups?**
A scheduled, automated weekly restore drill runs the latest backup into a
throwaway database and verifies it (`infra/backup/restore.sh`,
`rentflow-restore-check.timer`).

---

## Keeping this document honest

Anything in brackets above is a placeholder that must be filled in with a
real, current answer before this document leaves the building. An answer
that was true in Sprint 26A and is false by Sprint 30 is worse than no answer
at all — review this file whenever a security-relevant capability is added,
removed, or changed, the same discipline `sub-processors.md` already keeps.
