import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests against a real running backend, database and frontend —
 * the layer the Vitest suite deliberately does not cover (its own config says
 * so: "screens are thin compositions over useQuery, and covering them is a
 * separate piece of work"). This is that separate piece of work, scoped to the
 * paths where a defect is a customer's money or a customer's data, not to
 * every screen.
 *
 * `baseURL` and the backend's own URL both come from the environment rather
 * than being hardcoded, because CI and a local run point at different things:
 * CI brings up Postgres, Redis and the backend as services and passes their
 * real addresses in; a local run defaults to the same ports `npm run dev`
 * and `uvicorn` already use, so `npx playwright test` works with zero setup
 * once both are running.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // CI shares a runner across the whole matrix; a flake there should retry
  // once before failing the build. Locally a retry only hides a real bug.
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Only starts a dev server locally. In CI the workflow starts `vite preview`
  // itself (against a production build, which is what actually ships) and
  // passes its URL via E2E_BASE_URL — a second server here would collide with
  // the port CI already bound.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        url: baseURL,
        reuseExistingServer: true,
        timeout: 30_000,
      },
})
