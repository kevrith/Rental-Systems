import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { cn } from '@/lib/cn'

/**
 * `deviceId` caches its value in a module-level variable, so each test has to
 * import a fresh copy of the module — otherwise the first test's id leaks into
 * every one after it and the caching behaviour becomes untestable.
 */
async function freshDevice() {
  vi.resetModules()
  return import('@/lib/device')
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('deviceId', () => {
  it('generates an id and remembers it across calls', async () => {
    const { deviceId } = await freshDevice()

    const first = deviceId()
    expect(first).toBeTruthy()
    expect(deviceId()).toBe(first)
  })

  it('reuses the id already in storage, so a device stays recognised', async () => {
    localStorage.setItem('rentflow-device-id', 'known-device')
    const { deviceId } = await freshDevice()

    expect(deviceId()).toBe('known-device')
  })

  it('still returns an id when storage is blocked, rather than throwing', async () => {
    const { deviceId } = await freshDevice()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: storage is disabled')
    })

    // Private browsing: the fallback is a per-tab id, which means the user is
    // asked for an OTP each time. That is the safe outcome, not an error page.
    const id = deviceId()
    expect(id).toBeTruthy()
    expect(deviceId()).toBe(id)
  })
})

describe('currentPosition', () => {
  it('resolves null when the browser has no geolocation at all', async () => {
    const { currentPosition } = await freshDevice()
    const original = Object.getOwnPropertyDescriptor(navigator, 'geolocation')
    // @ts-expect-error — deleting an optional browser API for the test
    delete navigator.geolocation

    await expect(currentPosition()).resolves.toBeNull()

    if (original) Object.defineProperty(navigator, 'geolocation', original)
  })

  it('resolves null when the user denies the permission', async () => {
    const { currentPosition } = await freshDevice()
    Object.defineProperty(navigator, 'geolocation', {
      value: {
        getCurrentPosition: (_ok: unknown, fail: (error: unknown) => void) =>
          fail({ code: 1, message: 'User denied Geolocation' }),
      },
      configurable: true,
    })

    // A caretaker who declines location must still be able to record a
    // reading — the coordinates are evidence, not a gate.
    await expect(currentPosition()).resolves.toBeNull()
  })

  it('resolves the position when the user allows it', async () => {
    const { currentPosition } = await freshDevice()
    const position = { coords: { latitude: -1.2921, longitude: 36.8219 } }
    Object.defineProperty(navigator, 'geolocation', {
      value: { getCurrentPosition: (ok: (value: unknown) => void) => ok(position) },
      configurable: true,
    })

    await expect(currentPosition()).resolves.toBe(position)
  })
})

describe('cn', () => {
  it('joins the class names it is given', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops the falsy values conditional classes produce', () => {
    expect(cn('a', false, null, undefined, '', 'b')).toBe('a b')
  })

  it('flattens nested arrays', () => {
    expect(cn('a', ['b', ['c', false]], 'd')).toBe('a b c d')
  })

  it('is an empty string when there is nothing to join', () => {
    expect(cn()).toBe('')
    expect(cn(false, null)).toBe('')
  })
})
