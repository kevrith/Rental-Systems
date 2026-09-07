# Load testing

Sprint 24 (US-102) asks for load testing at 500 concurrent users across
10,000 units, with a 95th-percentile API response time under 800ms.
`k6-load-test.js` is the script for that — ramping virtual users through
login, the portfolio dashboard, and the payments/invoices lists, the
highest-traffic reads in the app.

## What this is, and isn't

This script has **not been run** against a real deployment. There isn't one
yet — RentFlow doesn't have a staging environment sized like production
(that's the DigitalOcean droplet from Sprint 0/24's own launch checklist),
and this sandbox has neither k6 installed nor 10,000 seeded units to point
it at. Treat this as the load-test harness ready for whoever stands up
staging next, not as a report of measured numbers.

## Running it for real

1. Install k6: https://k6.io/docs/get-started/installation/
2. Seed a staging database with representative data — roughly 10,000 units
   across enough organizations to look like a real multi-tenant load, not
   one giant account (RLS and per-org query plans behave differently at
   that shape).
3. Create one load-test account, log in normally through the UI once with
   "remember this device" checked so its device fingerprint is trusted —
   the script logs in on every iteration and cannot itself complete an SMS
   OTP challenge.
4. Run:
   ```bash
   k6 run \
     -e BASE_URL=https://staging.rentflow.co.ke \
     -e LOGIN_EMAIL=<the load-test account's email> \
     -e LOGIN_PASSWORD='<its password — pass as an env var, never hardcode it>' \
     infra/loadtest/k6-load-test.js
   ```
5. Read the `http_req_duration` p(95) k6 prints against the 800ms threshold,
   and watch the API server's own CPU/memory and Postgres connection count
   during the run — a passing p95 with the database gasping for connections
   is not actually a pass.

## Interpreting a failing run

- p95 breaching 800ms on the dashboard endpoint specifically usually means a
  missing index or an N+1 query — check `tests/test_query_plans.py`'s
  approach (it asserts query *count*, not just correctness) before adding
  indexes blind.
- Failures concentrated in `payments`/`invoices` at high VU counts often
  trace back to connection-pool exhaustion (`DATABASE_URL` pool size vs.
  concurrent request count), not application code.
