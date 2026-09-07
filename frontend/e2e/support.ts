import type { APIRequestContext, Page } from '@playwright/test'

/**
 * Shared helpers for the E2E suite.
 *
 * The backend API URL is read the same way the app itself reads it
 * (`VITE_API_URL`, falling back to the local default) rather than being
 * hardcoded a second time — a CI run that points the frontend at a different
 * backend must not leave these helpers silently talking to the wrong one.
 */
export const API_BASE_URL = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1'

let counter = 0

/** A fresh, valid Kenyan mobile number per call — phone numbers are unique
 * across the platform, so a counter beats randomness for guaranteeing that. */
export function uniquePhone(): string {
  counter += 1
  return `+2547${Date.now().toString().slice(-6)}${counter.toString().padStart(2, '0')}`
}

export function uniqueEmail(prefix: string): string {
  counter += 1
  return `${prefix}-${Date.now()}-${counter}@e2e.rentflow.test`
}

interface Registered {
  email: string
  password: string
  organizationName: string
  accessToken: string
}

/**
 * Register a fresh owner account via the API — not the UI — for tests whose
 * subject is something *downstream* of having an account (recording a
 * payment, say). `auth.spec.ts` is the one place registration itself is
 * driven through the UI; every other spec treats a working account as a
 * precondition, the same way the backend's own test suite treats
 * `register_owner` as a fixture rather than re-testing it in every file.
 */
export async function registerOwner(request: APIRequestContext): Promise<Registered> {
  const suffix = `${Date.now()}${Math.random().toString(36).slice(2, 6)}`
  const email = uniqueEmail('owner')
  const password = `E2e-Pass-${suffix}!`

  const response = await request.post(`${API_BASE_URL}/auth/register`, {
    data: {
      full_name: 'E2E Test Owner',
      organization_name: `E2E Portfolio ${suffix}`,
      email,
      phone_number: uniquePhone(),
      password,
      account_type: 'owner',
    },
  })
  if (!response.ok()) {
    throw new Error(`Registration failed in test setup: ${response.status()} ${await response.text()}`)
  }
  const body = await response.json()

  return {
    email,
    password,
    organizationName: body.organization?.name ?? '',
    accessToken: body.tokens.access_token,
  }
}

/** Load the sample portfolio (Sprint 26) so a test has something real to act
 * on — four tenants at different stages of paying, one property, a year of
 * history — without each spec hand-building fixtures over the API. */
export async function loadDemoData(request: APIRequestContext, accessToken: string): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/organizations/demo-data`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok()) {
    throw new Error(`Demo data seeding failed in test setup: ${response.status()} ${await response.text()}`)
  }
}

/**
 * Put a browser tab into an authenticated state without driving the UI
 * through login — mirrors how the backend suite's `Actor` fixture holds a
 * token rather than re-authenticating for every test. Written into the exact
 * localStorage shape `useAuthStore`'s zustand `persist` middleware produces,
 * so a page reload after this rehydrates the store precisely as it would
 * after a real login.
 */
export async function signInAs(page: Page, session: Registered): Promise<void> {
  // A page has to exist before localStorage can be written for its origin.
  await page.goto('/login')
  await page.evaluate(
    ([token, email]) => {
      localStorage.setItem(
        'rentflow-auth',
        JSON.stringify({
          state: {
            accessToken: token,
            refreshToken: token,
            user: { email },
            organization: null,
          },
          version: 0,
        }),
      )
    },
    [session.accessToken, session.email],
  )
}
