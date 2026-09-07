import { beforeEach, describe, expect, it } from 'vitest'

import { hasPermission, isTenant, useAuthStore, type AuthUser } from '@/store/auth-store'

/**
 * The store decides what the UI lets someone do. `hasPermission` mirrors the
 * backend's role matrix, and getting it wrong in the permissive direction
 * shows a caretaker buttons that will 403 — getting it wrong in the other
 * direction hides work someone is paid to do.
 */

const user: AuthUser = {
  id: 'u1',
  organization_id: 'o1',
  full_name: 'Jane Wanjiru',
  email: 'jane@example.com',
  phone_number: '+254712345678',
  role: 'property_manager',
  is_active: true,
  is_email_verified: true,
  is_phone_verified: true,
  permissions: ['payment:record', 'tenant:view'],
}

beforeEach(() => {
  useAuthStore.getState().logout()
  localStorage.clear()
})

describe('session lifecycle', () => {
  it('stores tokens and user on sign-in', () => {
    useAuthStore.getState().setSession({
      accessToken: 'a',
      refreshToken: 'r',
      user,
    })

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('a')
    expect(state.user?.full_name).toBe('Jane Wanjiru')
  })

  it('keeps the existing user when a refresh supplies only tokens', () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user })
    useAuthStore.getState().setSession({ accessToken: 'a2', refreshToken: 'r2' })

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('a2')
    expect(state.user?.full_name).toBe('Jane Wanjiru')
  })

  it('clears everything on logout', () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user })

    useAuthStore.getState().logout()

    const state = useAuthStore.getState()
    expect(state.accessToken).toBeNull()
    expect(state.refreshToken).toBeNull()
    expect(state.user).toBeNull()
    expect(state.organization).toBeNull()
  })

  it('advances the activity timestamp on touch', () => {
    const before = useAuthStore.getState().lastActivityAt
    useAuthStore.getState().touch()
    expect(useAuthStore.getState().lastActivityAt).toBeGreaterThanOrEqual(before)
  })

  it('does not persist lastActivityAt — a browser reopened tomorrow is not idle', () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user })

    const persisted = JSON.parse(localStorage.getItem('rentflow-auth') ?? '{}')
    expect(persisted.state).toHaveProperty('accessToken')
    expect(persisted.state).not.toHaveProperty('lastActivityAt')
  })
})

describe('hasPermission', () => {
  it('is true for a permission the role holds', () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user })
    expect(hasPermission('payment:record')).toBe(true)
  })

  it('is false for one it does not', () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user })
    expect(hasPermission('payment:approve')).toBe(false)
  })

  it('is false when signed out, rather than throwing', () => {
    expect(hasPermission('payment:record')).toBe(false)
  })

  it('is false when the server sent no permissions list at all', () => {
    useAuthStore.getState().setSession({
      accessToken: 'a',
      refreshToken: 'r',
      user: { ...user, permissions: undefined },
    })
    expect(hasPermission('payment:record')).toBe(false)
  })
})

describe('isTenant', () => {
  it('recognises a tenant portal login', () => {
    useAuthStore
      .getState()
      .setSession({ accessToken: 'a', refreshToken: 'r', user: { ...user, role: 'tenant' } })
    expect(isTenant()).toBe(true)
  })

  it('is false for staff and for nobody', () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user })
    expect(isTenant()).toBe(false)

    useAuthStore.getState().logout()
    expect(isTenant()).toBe(false)
  })
})
