/**
 * RentFlow load test (Sprint 24, US-102: "500 concurrent users, 10,000
 * units, p95 < 800ms").
 *
 * This script is ready to run but has NOT been executed against a real
 * staging deployment — there isn't one yet (see sprint-plan.md's Sprint 24
 * status). k6 isn't installed in the dev sandbox this was written in either.
 * Running it for real needs:
 *   1. A running RentFlow instance sized like production (not a laptop),
 *      seeded with roughly 10,000 units across many organizations.
 *   2. A pool of real login credentials for that seeded data — BASE_URL,
 *      LOGIN_EMAIL/LOGIN_PASSWORD below are placeholders, not real values.
 *   3. k6 itself: https://k6.io/docs/get-started/installation/
 *
 * Run: k6 run -e BASE_URL=https://staging.rentflow.co.ke \
 *             -e LOGIN_EMAIL=loadtest@example.com \
 *             -e LOGIN_PASSWORD='<real password, never hardcode this>' \
 *             infra/loadtest/k6-load-test.js
 */
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Rate, Trend } from 'k6/metrics'

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000'
const LOGIN_EMAIL = __ENV.LOGIN_EMAIL
const LOGIN_PASSWORD = __ENV.LOGIN_PASSWORD

const failureRate = new Rate('rentflow_failed_requests')
const loginDuration = new Trend('rentflow_login_duration')

// Ramp profile matching the acceptance criterion: reach and hold 500
// concurrent virtual users, not just spike through them.
export const options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '3m', target: 500 },
    { duration: '5m', target: 500 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    // The acceptance criterion itself: p95 under 800ms.
    http_req_duration: ['p(95)<800'],
    rentflow_failed_requests: ['rate<0.01'],
  },
}

function authHeaders(token) {
  return { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } }
}

export default function () {
  // POST /auth/login returns a 2FA challenge unless the calling device is
  // already trusted (`LoginChallengeResponse.otp_required=False`, tokens
  // included directly). A real run needs a seeded load-test account whose
  // device fingerprint (X-Device-Id below) was pre-verified via the normal
  // "remember this device" flow — otherwise every virtual user would stall
  // on an OTP prompt with nowhere to receive the SMS.
  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: LOGIN_EMAIL, password: LOGIN_PASSWORD, remember_device: true }),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Id': `k6-loadtest-${__VU}`,
      },
    },
  )
  loginDuration.add(loginRes.timings.duration)
  const loggedIn = check(loginRes, {
    'login succeeded (trusted device, no OTP)': (r) =>
      r.status === 200 && r.json('otp_required') === false,
  })
  failureRate.add(!loggedIn)
  if (!loggedIn) {
    sleep(1)
    return
  }

  const token = loginRes.json('tokens.access_token')
  const opts = authHeaders(token)

  const dashboardRes = http.get(`${BASE_URL}/api/v1/dashboard/portfolio`, opts)
  failureRate.add(!check(dashboardRes, { 'dashboard 200': (r) => r.status === 200 }))

  const paymentsRes = http.get(`${BASE_URL}/api/v1/payments?limit=25`, opts)
  failureRate.add(!check(paymentsRes, { 'payments list 200': (r) => r.status === 200 }))

  const invoicesRes = http.get(`${BASE_URL}/api/v1/invoices?limit=25`, opts)
  failureRate.add(!check(invoicesRes, { 'invoices list 200': (r) => r.status === 200 }))

  sleep(1)
}
