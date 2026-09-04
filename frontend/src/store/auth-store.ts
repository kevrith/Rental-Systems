import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AuthUser {
  id: string
  organization_id: string
  full_name: string
  email: string
  phone_number: string
  role: string
  is_active: boolean
  is_email_verified: boolean
  is_phone_verified: boolean
  profile_photo_url?: string | null
  always_require_2fa?: boolean
  inactivity_timeout_minutes?: number
  deletion_requested_at?: string | null
  last_login_at?: string | null
  permissions?: string[]
}

export interface AuthOrganization {
  id: string
  name: string
  slug: string
  operating_mode: string
  subscription_plan: string
  trial_ends_at: string | null
  is_trial?: boolean
  is_trial_expired?: boolean
  trial_days_remaining?: number | null
  is_read_only?: boolean
}

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: AuthUser | null
  organization: AuthOrganization | null
  /** Wall-clock ms of the last user interaction, for the inactivity timeout. */
  lastActivityAt: number

  setSession: (session: {
    accessToken: string
    refreshToken: string
    user?: AuthUser
    organization?: AuthOrganization
  }) => void
  setTokens: (tokens: { accessToken: string; refreshToken: string }) => void
  setUser: (user: AuthUser) => void
  setOrganization: (organization: AuthOrganization) => void
  touch: () => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      organization: null,
      lastActivityAt: Date.now(),

      setSession: ({ accessToken, refreshToken, user, organization }) =>
        set((state) => ({
          accessToken,
          refreshToken,
          user: user ?? state.user,
          organization: organization ?? state.organization,
          lastActivityAt: Date.now(),
        })),
      setTokens: ({ accessToken, refreshToken }) =>
        set({ accessToken, refreshToken, lastActivityAt: Date.now() }),
      setUser: (user) => set({ user }),
      setOrganization: (organization) => set({ organization }),
      touch: () => set({ lastActivityAt: Date.now() }),
      logout: () =>
        set({ accessToken: null, refreshToken: null, user: null, organization: null }),
    }),
    {
      name: 'rentflow-auth',
      // `lastActivityAt` is intentionally not persisted: a browser reopened the
      // next morning should not be judged against yesterday's timestamp.
      partialize: ({ accessToken, refreshToken, user, organization }) => ({
        accessToken,
        refreshToken,
        user,
        organization,
      }),
    },
  ),
)

/** Permission check that mirrors the backend's role matrix. */
export function useHasPermission(permission: string): boolean {
  const permissions = useAuthStore((state) => state.user?.permissions)
  return permissions?.includes(permission) ?? false
}

export function hasPermission(permission: string): boolean {
  return useAuthStore.getState().user?.permissions?.includes(permission) ?? false
}

export function isTenant(): boolean {
  return useAuthStore.getState().user?.role === 'tenant'
}
