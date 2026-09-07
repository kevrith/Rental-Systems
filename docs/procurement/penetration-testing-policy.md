# Penetration testing policy

**Status: no third-party penetration test has been performed.** This document
is the policy and runbook for commissioning one — it is not, and cannot be,
a substitute for an actual engagement. A security questionnaire that asks
"do you conduct regular penetration testing" gets an honest "not yet; here is
our policy and the date the first one is scheduled" from this document, not a
fabricated summary of a test that never happened.

## Policy

- **Cadence.** An external penetration test annually, and after any material
  architectural change (a new payment flow, a new authentication mechanism,
  the introduction of a new sub-processor with access to Personal Data).
- **Scope.** The production API, the tenant and operator web applications,
  and the authentication/authorization boundary between organisations
  (multi-tenant isolation is the single highest-value thing to have an
  outside party try to break, given the whole business model depends on one
  landlord never seeing another's tenants).
- **Method.** Grey-box — the tester is given a standard operator account and
  a standard tenant account, matching what a real attacker who obtained one
  set of legitimate low-privilege credentials (a phished caretaker, a leaked
  tenant password) would have. Full black-box testing understates the risk
  that actually matters for this product; full white-box (source access)
  overstates the tester's time budget relative to what it buys.
- **Out of scope by default:** denial-of-service testing against production
  infrastructure, social engineering against staff, and physical security —
  each is a separate, explicitly-scoped engagement if ever needed, not a
  default inclusion that could take the production system down mid-test.

## Selecting a tester

A tester engaged for this platform should be independent (no prior
relationship that could bias the report), and should be told upfront about
the specific things worth trying — a generic web-app scan misses what
actually matters here:

- **Cross-tenant data access** — Row Level Security (`app/core/rls.py`) is
  the second lock behind application-layer scoping (`app/api/deps.py`); a
  tester should try to find a code path that reaches the database with the
  RLS session variable unset or wrong, not just try SQL injection against
  form fields.
- **The M-Pesa payment and disbursement flow** — `app/services/payment_service.py`
  and the B2C disbursement path (`app/services/bank_transfer_service.py` and
  related) are where a logic flaw is worth real money, not just a data leak.
- **The dual-approval / maker-checker controls** — can the same person who
  recorded a large cash payment also approve it, through any path other than
  the one `_assert_approvable` explicitly blocks?
- **The tenant portal's authentication boundary** — the magic-link flow
  (`app/api/v1/endpoints/portal.py`) is new (Sprint 26A) and is exactly the
  kind of surface a first pen test should focus fresh attention on, since it
  is public and unauthenticated by design (a tenant has no session yet when
  requesting a link).
- **The public developer API** (`app/api/v1/endpoints/external.py`) — a
  different trust boundary from the session-based app, with its own rate
  limiting and scoping that has never been externally attacked.

## Runbook — how to actually commission one

1. **Get sign-off on scope and timing** from whoever owns the decision
   (today: Kelvin). A test scheduled during a customer's own critical period
   (month-end billing, say) is a bad time regardless of how solid the system
   is.
2. **Provision test accounts** — a fresh organisation with the demo dataset
   (`POST /api/v1/organizations/demo-data`, built in Sprint 26A) is exactly
   the right size and shape of test data: real enough to attack, fabricated
   enough that nothing sensitive is at risk if the tester finds a hole.
3. **Set a rules-of-engagement document** with the tester: scope, timing
   window, an emergency contact if something in production looks like it is
   actually breaking (vs. the test working as intended), and confirmation
   the test environment is isolated from real customer data.
4. **Receive the report**, triage findings by severity, and track remediation
   to closure — a finding with no remediation date is not actually
   "addressed," and a report an auditor or customer later asks to see should
   show closed findings, not just a list.
5. **Publish a summary** (not the full report, which typically contains
   exploit detail) to `docs/procurement/` for use in customer due diligence —
   overall risk rating, scope, date, and a statement that findings were
   remediated, with critical/high findings itemised by category (not by
   exploit detail) and their remediation status.

## What to hand a customer today, honestly

> RentFlow has not yet completed an external penetration test. A test is
> scoped and policy-defined (see our penetration testing policy) and is
> planned for **[DATE, once actually scheduled]**. In the interim, the
> platform is covered by continuous automated security scanning (dependency
> vulnerability scanning and static analysis on every code change — see our
> security questionnaire answers) and a documented OWASP Top 10 self-review.

That is a true statement today. Do not represent otherwise.
