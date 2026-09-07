import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vitest/config'

/**
 * A separate config from `vite.config.ts` on purpose.
 *
 * The app config loads `vite-plugin-pwa`, which generates and injects a service
 * worker. Under test that produces a worker nothing runs and a manifest nothing
 * reads, and it slows every run down for no benefit — so the test config takes
 * only the two things tests actually need: JSX transform and the `@` alias.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      /*
       * Scoped to the layer that is actually under test, not to `src/**`.
       *
       * A threshold computed over every screen would come out around 30% and
       * would say nothing about whether the tested code is tested well. What is
       * in here is the logic that has no visual signal when it breaks — money
       * formatting, the token refresh, the offline queue, the auth store, the
       * route guard, and the primitives every screen is built from.
       *
       * Screens are the honest gap. They are thin compositions over `useQuery`,
       * and covering them is a separate piece of work, not something to fake by
       * widening this list.
       */
      include: [
        'src/lib/**',
        'src/store/**',
        'src/components/ui/**',
        'src/components/ProtectedRoute.tsx',
      ],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        // The service worker runs in a worker context jsdom cannot host.
        'src/sw.ts',
        // WebAuthn needs a real authenticator; jsdom has no credentials API.
        'src/lib/webauthn.ts',
      ],
      /*
       * Set from the measured figure, as a ratchet. Raise them as coverage
       * rises; do not set an aspirational number that fails on the first run,
       * because a threshold nobody can pass gets deleted from CI within a week.
       *
       * `functions` is deliberately far lower than the others and is not a
       * measure of anything much here: `query-client.ts` is a hundred-odd
       * one-line key factories, each counted as an uncovered function, which
       * drags the figure down without saying anything about risk. Statements,
       * lines and branches are the numbers worth watching.
       */
      thresholds: {
        statements: 80,
        branches: 88,
        functions: 30,
        lines: 80,
      },
    },
  },
})
