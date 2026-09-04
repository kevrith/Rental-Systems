/**
 * A stable per-browser identifier.
 *
 * The backend mixes this with the user agent to decide whether a device is
 * "known" (skip 2FA) and to label the active-sessions list. It is a random
 * value, not a fingerprint — clearing site data legitimately produces a new
 * device, which the server treats as a new sign-in.
 */
const STORAGE_KEY = 'rentflow-device-id'

let cached: string | null = null

export function deviceId(): string {
  if (cached) return cached

  try {
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      cached = existing
      return existing
    }
    const fresh = crypto.randomUUID()
    localStorage.setItem(STORAGE_KEY, fresh)
    cached = fresh
    return fresh
  } catch {
    // Private mode or blocked storage: fall back to a per-tab value. The user
    // will simply be asked for an OTP each time, which is the safe outcome.
    cached = cached ?? crypto.randomUUID()
    return cached
  }
}

/** Coordinates for GPS-tagged captures, when the user allows it. */
export async function currentPosition(timeoutMs = 8000): Promise<GeolocationPosition | null> {
  if (!('geolocation' in navigator)) return null
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve(position),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60_000 },
    )
  })
}
