import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Theme } from '@/store/theme-store'

/**
 * Half of this store runs at import time: it reads the saved choice, falls
 * back to the OS preference, and puts the `dark` class on <html> before the
 * first component mounts. That half is what breaks in ways the screen does
 * not explain — a flash of the wrong theme on load, or a choice that silently
 * stops surviving a reload — so these cases re-import the module per scenario
 * rather than only driving the setters of an already-initialised store.
 */

const STORAGE_KEY = 'rentflow-theme'
const realMatchMedia = window.matchMedia

function stubMatchMedia(matches: boolean | undefined) {
  if (matches === undefined) {
    // Older Safari and jsdom without the shim: the store must not throw.
    delete (window as { matchMedia?: unknown }).matchMedia
    return
  }
  window.matchMedia = ((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

async function loadStore(opts: { stored?: string; prefersDark?: boolean } = {}) {
  vi.resetModules()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  if (opts.stored !== undefined) localStorage.setItem(STORAGE_KEY, opts.stored)
  stubMatchMedia(opts.prefersDark)
  return (await import('@/store/theme-store')).useThemeStore
}

const isDark = () => document.documentElement.classList.contains('dark')

beforeEach(() => {
  stubMatchMedia(false)
})

afterEach(() => {
  window.matchMedia = realMatchMedia
  document.documentElement.classList.remove('dark')
})

describe('the theme chosen at startup', () => {
  it('uses the saved choice over the OS preference', async () => {
    const store = await loadStore({ stored: 'light', prefersDark: true })

    expect(store.getState().theme).toBe('light')
    expect(isDark()).toBe(false)
  })

  it('falls back to the OS preference when nothing is saved', async () => {
    const store = await loadStore({ prefersDark: true })

    expect(store.getState().theme).toBe('dark')
    expect(isDark()).toBe(true)
  })

  it('defaults to light when nothing is saved and the OS prefers light', async () => {
    const store = await loadStore({ prefersDark: false })

    expect(store.getState().theme).toBe('light')
    expect(isDark()).toBe(false)
  })

  it('ignores a stored value that is not a theme', async () => {
    const store = await loadStore({ stored: 'chartreuse', prefersDark: true })

    expect(store.getState().theme).toBe('dark')
  })

  it('survives a browser with no matchMedia at all', async () => {
    const store = await loadStore({ prefersDark: undefined })

    expect(store.getState().theme).toBe('light')
  })

  it('survives localStorage throwing on read', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('access denied')
    })

    const store = await loadStore({ prefersDark: true })

    // Unreadable storage is not a reason to fail to boot; the OS preference
    // still decides.
    expect(store.getState().theme).toBe('dark')
  })
})

describe('changing the theme', () => {
  it('applies the class, persists the choice and updates the store', async () => {
    const store = await loadStore()

    store.getState().setTheme('dark')

    expect(store.getState().theme).toBe('dark')
    expect(isDark()).toBe(true)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark')
  })

  it('removes the class when going back to light', async () => {
    const store = await loadStore({ stored: 'dark' })
    expect(isDark()).toBe(true)

    store.getState().setTheme('light')

    expect(isDark()).toBe(false)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('light')
  })

  it('still switches when storage is unwritable, it just will not persist', async () => {
    const store = await loadStore()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })

    expect(() => store.getState().setTheme('dark')).not.toThrow()

    expect(store.getState().theme).toBe('dark')
    expect(isDark()).toBe(true)
  })

  it('toggles in both directions', async () => {
    const store = await loadStore()

    store.getState().toggle()
    expect(store.getState().theme).toBe<Theme>('dark')

    store.getState().toggle()
    expect(store.getState().theme).toBe<Theme>('light')
  })
})
