import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { useAuthStore } from '@/store/auth-store'

const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'touchstart', 'scroll', 'visibilitychange'] as const

/**
 * Auto-logout after a period of inactivity (US-005).
 *
 * The timeout comes from the user's own profile — the backend defaults it by
 * role, so an owner (30 min) times out far sooner than a caretaker mid-shift
 * (4 hours). Activity is recorded with a ref, not state, so a mouse move never
 * re-renders the whole app.
 */
export function useInactivityLogout() {
  const navigate = useNavigate()
  const timeoutMinutes = useAuthStore((state) => state.user?.inactivity_timeout_minutes ?? 30)
  const accessToken = useAuthStore((state) => state.accessToken)
  const lastActivity = useRef(0)

  useEffect(() => {
    if (!accessToken) return

    // Seeded here rather than at render time: Date.now() during render is
    // impure and makes the countdown restart on every re-render.
    lastActivity.current = Date.now()

    const markActive = () => {
      lastActivity.current = Date.now()
    }
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, markActive, { passive: true })
    }

    const limitMs = Math.max(5, timeoutMinutes) * 60_000
    const interval = window.setInterval(async () => {
      if (Date.now() - lastActivity.current < limitMs) return

      window.clearInterval(interval)
      try {
        await authApi.logout(useAuthStore.getState().refreshToken)
      } catch {
        // The session is ending regardless of whether the server hears about it.
      }
      useAuthStore.getState().logout()
      navigate('/login?timeout=1', { replace: true })
    }, 30_000)

    return () => {
      for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, markActive)
      window.clearInterval(interval)
    }
  }, [accessToken, navigate, timeoutMinutes])
}
