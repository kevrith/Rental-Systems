import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import 'fake-indexeddb/auto'
import { afterEach, beforeEach, vi } from 'vitest'

/**
 * jsdom stops short of several browser APIs this app relies on, so they are
 * filled in once here rather than mocked in each test that trips over them.
 */

// `matchMedia` — used by responsive layout components.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

// `crypto.randomUUID` — the offline queue's idempotency key comes from here.
if (!globalThis.crypto?.randomUUID) {
  Object.defineProperty(globalThis, 'crypto', {
    value: {
      ...globalThis.crypto,
      randomUUID: () => `test-${Math.random().toString(16).slice(2)}-${Date.now()}`,
    },
    configurable: true,
  })
}

// Recharts measures its container, and jsdom reports every element as 0x0 —
// which makes charts render nothing at all. A fixed size keeps them mounting.
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

beforeEach(() => {
  // Default to online. The offline-queue tests override this per case.
  Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
  localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
