# OWASP Top 10 (2021) Checklist — RentFlow Kenya

Sprint 24, US-102. A code-level review of the current tree against each
OWASP category, with what's actually implemented and where. This is a
security *review*, not a penetration test — nothing here substitutes for a
real external pentest before production launch, which stays on the Sprint 24
production-launch list alongside the credentials and infrastructure Kelvin
still needs to provision himself.

## A01:2021 — Broken Access Control

- Every endpoint declares a `Permission` and goes through `require(...)` in
  `app/api/deps.py`, resolved against the fixed matrix in
  `app/core/permissions.py`. A caretaker's property scoping is enforced
  separately from the permission check (`PROPERTY_SCOPED_ROLES`).
- Cross-tenant access answers `403`, never `404` — verified by
  `tests/test_regression.py::test_organizations_cannot_read_each_others_records`
  and `::test_list_endpoints_never_return_another_organizations_rows`.
- Defense in depth: PostgreSQL Row Level Security (`app/core/rls.py`, 26
  org-scoped tables) enforces the same isolation at the database layer, so a
  bug in a query's `WHERE org_id = ...` clause still can't leak another
  organization's rows. Covered by `tests/test_rls.py` and
  `tests/test_migrations.py`.
- Read-only roles (`OWNER_PORTAL_USER`) are blocked from every write at the
  dependency layer (`READ_ONLY_ROLES`), not just by omitting permissions —
  `tests/test_regression.py::test_a_read_only_trial_cannot_write` covers the
  equivalent trial-expiry case.
- Public, unauthenticated links (signing links, guarantor links, renewal
  links, portal webhooks) are scoped to a single resource by an unguessable
  signed token, never by a guessable sequential id — see A07 below for the
  actual signing-request cross-org bug this caught in Sprint 9.

## A02:2021 — Cryptographic Failures

- Passwords hashed with bcrypt, cost factor 12 (`app/core/security.py`).
- JWTs signed with `SECRET_KEY` (required env var, no default — the app
  won't start without one), HS256, 15-minute access / 7-day refresh expiry.
- Refresh tokens, email-verification links, and invite links are stored only
  as a SHA-256 hash (`hash_token`) — a database leak yields nothing usable.
- API keys and webhook secrets: shown to the caller exactly once at creation,
  stored hashed (API keys) or as a signing secret used only for HMAC
  (webhooks), never stored or logged in the clear.
- Receipts are HMAC-signed (`sign_payload`/`verify_signature`) so a receipt
  PDF can't be edited and re-presented as genuine.
- File download URLs (R2 and the local-disk fallback) are signed with a
  60-minute expiry (`storage_service.py`) — fixed in Phase 2 after the local
  backend was found serving any object to anyone who guessed a key; R2 and
  local now get the same treatment.
- Gap: no field-level encryption for KYC documents (ID photos, passport
  photos) at rest beyond R2's own bucket-level encryption. Acceptable for
  now since access is gated by signed URLs, not public buckets, but worth
  revisiting if a real pentest flags it.

## A03:2021 — Injection

- All database access goes through SQLAlchemy's async ORM with parameterized
  queries; no raw string-interpolated SQL in application code. The one place
  raw SQL runs (`app/core/rls.py`'s policy-creation statements) is static
  DDL executed at migration/test-setup time, not built from request input.
- Pydantic schemas validate and coerce every request body before it reaches
  a service function — reject-by-default on unexpected fields.
- WeasyPrint template rendering (leases, receipts, statements) uses Jinja2
  autoescaping; the one place user-supplied rich text is injected verbatim
  (AI lease-suggestion acceptance, `lease_service` appending to
  `body_html`) is explicitly HTML-escaped before insertion (Sprint 22 note).

## A04:2021 — Insecure Design

- Money-moving flows are built idempotent by design, not bolted on: M-Pesa
  STK and B2C callbacks, and the payment-confirmation path generally, are
  gated by Redis `SET NX` locks (`mpesa_service.py:216,373`) so a duplicate
  webhook delivery can't double-settle a payment or disbursement.
- Disbursements can't be paid without review: a payout moves
  `PENDING → APPROVED → PROCESSING → COMPLETED`, and approval refuses a zero
  or negative net (Phase 2 fix).
- Fraud detection (`fraud_detection_service.py`) runs inline on every
  confirmed payment — rapid cash, off-hours activity, unusual amount,
  velocity — rather than as a batch job that reports a problem after the
  fact.
- Every third-party integration degrades gracefully with no credentials
  configured (clear `503`, never a stack trace) rather than the design
  assuming credentials always exist — consistent from Phase 1's M-Pesa
  simulation through Sprint 22's AI service and Sprint 23's OAuth connectors.

## A05:2021 — Security Misconfiguration

- Fixed this sprint: `Settings.DEBUG` defaulted to `True`
  (`app/core/config.py`) — a production deployment that forgot to set
  `DEBUG=false` explicitly would have run FastAPI in debug mode, leaking
  stack traces in error responses. Now defaults to `False`; local dev's own
  `.env` sets `DEBUG=true` explicitly, so nothing changes for Kelvin's
  day-to-day dev loop.
- Fixed this sprint: no security response headers were set at all. Added
  `SecurityHeadersMiddleware` (`app/main.py`) — `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
  strict-origin-when-cross-origin`, a conservative `Permissions-Policy`.
  HSTS is left for the production Nginx config (Sprint 24, US-104) once a
  real TLS-terminating domain exists to pin it to — setting it here would be
  premature on a plain HTTP dev server.
- CORS is an explicit origin allowlist (`CORS_ORIGINS`), not a wildcard, with
  credentials allowed only for those listed origins.
- Dependency pinning: every backend dependency in `requirements.txt` is
  pinned to an exact version (`fastapi==0.115.6`, etc.) — no floating
  version ranges to drift under an unreviewed transitive update.
- Dependabot is configured (`.github/dependabot.yml`) but only takes effect
  once switched on in the GitHub repo's own settings — same account-level
  gap Sprint 0 already flags for branch protection.
- **Closed in Sprint 26A** (was the largest documented gap here): the
  authenticated app API is now rate-limited per user, and per IP for anything
  unauthenticated — `app/core/rate_limit.py`, a fixed one-minute Redis window
  with three tiers. Expensive endpoints (anything that sends an SMS, renders a
  PDF or calls a model) get a much lower ceiling than ordinary reads, because
  those cost real money per call rather than just load. The external
  developer API keeps its own per-key meter and is exempt here, so a
  customer's paid quota is not silently halved. Redis being unreachable fails
  **open** — a limiter that takes the API down with its cache has done more
  damage than the abuse it prevented. Covered by `tests/test_rate_limit.py`,
  including the fail-open path and the per-user bucket isolation.

## A06:2021 — Vulnerable and Outdated Components

- Frontend: `npm audit --omit=dev` — **0 vulnerabilities**.
- Backend: `pip-audit` against the pinned `requirements.txt` found 28
  advisories across 8 packages. Two were fixed this pass:
  - `python-jose` 3.3.0 → 3.4.0 — the package this app's own JWT
    encode/decode goes through (`app/core/security.py`). The advisories are
    algorithm-confusion issues in JWKS-based verification; this app never
    fetches a JWKS or accepts a caller-chosen algorithm (`jwt.decode(...,
    algorithms=[settings.JWT_ALGORITHM])` pins it to the one configured
    algorithm), so it wasn't exploitable here — bumped anyway since a fix
    version exists and costs nothing.
  - `jinja2` 3.1.5 → 3.1.6 — patch release, used for lease/receipt/statement
    PDF templates (autoescaping already covers the injection risk in A03).
  - Both re-verified against `test_auth_flows.py`, `test_regression.py`,
    `test_security.py`, `test_phase3_security.py`, and the signing/lease/PDF
    subset of `test_billing.py`/`test_phase2.py` — all pass.
  - Deferred rather than bumped blind: `starlette` (transitive via
    `fastapi==0.115.6`; every fix version is a `fastapi` major-version jump,
    not a drop-in patch — needs its own dedicated upgrade pass, not one
    folded into launch prep), `weasyprint` 63.1 (fix is a major version jump
    that could change PDF rendering output across every generated document —
    needs visual regression checking, not just the test suite passing),
    `python-multipart` (transitively pinned by FastAPI's own supported
    range), and `black`/`pytest`/`ecdsa` (dev tooling and a transitive
    `python-jose` dependency, not runtime attack surface). None of the four
    are exploitable through any code path this app actually exercises today;
    all four are named explicitly here rather than silently left off the
    list.
- Dependabot (`.github/dependabot.yml`) is what gives this ongoing coverage
  once switched on in the GitHub repo's own settings.

## A07:2021 — Identification and Authentication Failures

- Login: password + 2FA (SMS OTP), 5 failed attempts → 15-minute lockout,
  device fingerprinting, "remember this device" opt-in, suspicious-login
  WhatsApp alert.
- Session policy is configurable per role (`role_session_timeouts`,
  Sprint 22) and IP whitelisting (`ip_allowed`, `auth_service.py:260`) is
  available to every account, not gated behind a plan.
- A real, previously-fixed bug in this category: a signing request could
  target another organization's document because the signing link is public
  and unauthenticated — nothing downstream could catch it. `create_signing_
  request` now proves ownership of both the document and the tenancy before
  issuing a link, answering `404` rather than letting a cross-org signature
  through (Phase 2 fix, still enforced — covered by
  `tests/test_phase2.py::test_signing_flow_end_to_end` and the security
  suite).
- API keys and webhook secrets are shown once, then only ever compared by
  hash; failed API key attempts are logged and alert after 10 consecutive
  failures.

## A08:2021 — Software and Data Integrity Failures

- Receipts are HMAC-signed and therefore tamper-evident (A02 above).
- CI runs lint → typecheck → test → build before anything merges (GitHub
  Actions, Sprint 0) — nothing reaches `main` without passing the same
  gates this checklist was verified against.
- Webhook deliveries to *external* systems (Sprint 19) are themselves
  HMAC-signed, so a receiving system can verify a payload actually came from
  RentFlow.

## A09:2021 — Security Logging and Monitoring Failures

- `AuditLog` (`app/models/audit.py`) records every data-modifying action
  with actor, timestamp, and org — used as the audit trail for maintenance
  lifecycle transitions, disbursement approvals, and document access.
- `SecurityEvent` (Sprint 22) is a separate, durable log specifically for
  failed logins — distinct from `AuditLog`, which only ever recorded
  privileged successes — summarized to owners daily.
- Audit log export (CSV/PDF) is available for compliance review
  (`security_service.py`'s `export_audit_log`).
- Gap, documented rather than fixed: logging is structured
  (`app/core/logging.py`) but nothing ships those logs to a centralized,
  alertable system yet — that's Sentry (errors) and Grafana (performance),
  both blocked on Kelvin creating the accounts, same as every earlier
  phase's status block already notes.

## A10:2021 — Server-Side Request Forgery (SSRF)

- The two places this app makes outbound requests to a caller-influenced
  URL are webhook delivery (Sprint 19) and the property-portal/accounting
  OAuth integrations (Sprint 23). Webhook URLs are validated to be HTTPS
  (`test_developer_platform.py::test_webhook_rejects_non_https_url`) but are
  not currently checked against private/internal IP ranges (a webhook URL
  pointing at `169.254.169.254` or an internal service would not be
  rejected). Documented as a gap to close before opening webhook
  configuration to untrusted enterprise customers at scale — the fix is a
  DNS-resolve-then-check-range guard in the delivery service, not a
  structural redesign.

## Summary

Nine of ten categories have real, tested controls already in place, with two
concrete fixes made in this pass (secure-by-default `DEBUG`, security
response headers) and three gaps documented rather than silently left
implicit: no general API rate limiting, logs not yet centralized, and
webhook URLs not checked against private IP ranges. None of the three gaps
block a first launch on their own; all three are reasonable next-sprint or
pre-scale work, and are called out explicitly rather than checked off.

### Sprint 26A update

Two of those three gaps are now closed, and one new control was added:

- **API rate limiting** — done, see A05 above.
- **Supply-chain scanning is now enforced in CI**, not left to Dependabot's
  own schedule: `pip-audit` against the pinned requirements, `npm audit` on
  production dependencies, and CodeQL on both languages, all failing the
  build rather than filing a notification (A06).
- **Error tracking** — Sentry is wired in (`app/core/observability.py`) with
  `send_default_pii` off and an explicit `before_send` scrub of request
  bodies and credential-bearing headers. This application handles Kenyan
  tenants' national ID numbers and payment history, and the Data Protection
  Act does not stop applying because the data ended up in an error tracker.
- **Per-organisation encryption keys** (A02) — every stored third-party
  credential is now sealed under a key belonging to that one customer rather
  than one platform-wide key. Ciphertext lifted from one tenant is inert
  against another, and one customer's key can be rotated without every other
  customer having to re-enter their credentials.
- **Breach notification** (A09) — the Kenya DPA s.43 72-hour clock is now a
  tracked, escalating obligation rather than an intention:
  `app/services/breach_service.py`.

Logs are still not centralized, and webhook URLs are still not checked
against private IP ranges. Both remain open.
