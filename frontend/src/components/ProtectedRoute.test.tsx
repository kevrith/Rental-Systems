import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { ProtectedRoute } from '@/components/ProtectedRoute'
import { API_BASE_URL } from '@/lib/api-client'
import { useAuthStore, type AuthUser } from '@/store/auth-store'

/**
 * This is the only thing standing between an unauthenticated browser and every
 * screen in the app. Its guards are pure redirects, which means a mistake here
 * fails open and silently — exactly the kind of defect a test is worth having.
 *
 * Server-side authorisation is the real enforcement (`app.api.deps.require`);
 * these guards exist so a user is not shown work they will only be refused.
 * Both matter, and this file covers the client half.
 */

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const staff: AuthUser = {
  id: 'u1',
  organization_id: 'o1',
  full_name: 'Jane Wanjiru',
  email: 'jane@example.com',
  phone_number: '+254712345678',
  role: 'property_manager',
  is_active: true,
  is_email_verified: true,
  is_phone_verified: true,
  permissions: ['payment:record'],
}

function renderRoute(element: React.ReactElement, initial = '/guarded') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route element={element}>
            <Route path="/guarded" element={<div>Guarded page</div>} />
            <Route path="/internal" element={<div>Internal tools</div>} />
          </Route>
          {/*
            The redirect targets sit outside the guarded group on purpose. If
            `/dashboard` were itself guarded, a denied route would redirect
            into the same guard and loop, and the test would be asserting on
            React's bail-out rather than on the guard.
          */}
          <Route path="/dashboard" element={<div>Dashboard</div>} />
          <Route path="/login" element={<div>Sign in</div>} />
          <Route path="/portal" element={<div>Tenant portal</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** The profile call `ProtectedRoute` makes before rendering anything. */
function profileReturns(user: AuthUser) {
  server.use(http.get(`${API_BASE_URL}/auth/me`, () => HttpResponse.json(user)))
}

beforeEach(() => {
  useAuthStore.getState().logout()
})

describe('when signed out', () => {
  it('redirects to the login page', async () => {
    renderRoute(<ProtectedRoute />)

    expect(await screen.findByText('Sign in')).toBeInTheDocument()
    expect(screen.queryByText('Guarded page')).not.toBeInTheDocument()
  })
})

describe('when signed in', () => {
  beforeEach(() => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r', user: staff })
  })

  it('renders the route', async () => {
    profileReturns(staff)
    renderRoute(<ProtectedRoute />)

    expect(await screen.findByText('Guarded page')).toBeInTheDocument()
  })

  it('sends a tenant to the portal rather than a staff screen', async () => {
    const tenant = { ...staff, role: 'tenant' }
    useAuthStore.getState().setUser(tenant)
    profileReturns(tenant)

    renderRoute(<ProtectedRoute allowRoles={['property_manager', 'owner']} />)

    expect(await screen.findByText('Tenant portal')).toBeInTheDocument()
  })

  it('redirects when the required permission is missing', async () => {
    profileReturns(staff)
    renderRoute(<ProtectedRoute requirePermission="payment:approve" />, '/internal')

    expect(await screen.findByText('Dashboard')).toBeInTheDocument()
    expect(screen.queryByText('Internal tools')).not.toBeInTheDocument()
  })

  it('allows a route whose required permission the user holds', async () => {
    profileReturns(staff)
    renderRoute(<ProtectedRoute requirePermission="payment:record" />)

    expect(await screen.findByText('Guarded page')).toBeInTheDocument()
  })

  it('keeps a normal user out of the platform-staff area', async () => {
    profileReturns(staff)
    renderRoute(<ProtectedRoute requirePlatformStaff />, '/internal')

    expect(await screen.findByText('Dashboard')).toBeInTheDocument()
    expect(screen.queryByText('Internal tools')).not.toBeInTheDocument()
  })

  it('lets platform staff into it', async () => {
    const platformStaff = { ...staff, is_platform_staff: true }
    useAuthStore.getState().setUser(platformStaff)
    profileReturns(platformStaff)

    renderRoute(<ProtectedRoute requirePlatformStaff />, '/internal')

    expect(await screen.findByText('Internal tools')).toBeInTheDocument()
  })

  it('signs the user out to login when the profile call fails and nothing is cached', async () => {
    useAuthStore.getState().setSession({ accessToken: 'a', refreshToken: 'r' })
    server.use(
      http.get(`${API_BASE_URL}/auth/me`, () =>
        HttpResponse.json({ detail: 'User not found' }, { status: 401 }),
      ),
      // A 401 sends the API client to `/auth/refresh` first. Handled here so
      // the test exercises the real path rather than leaking a live request.
      http.post(`${API_BASE_URL}/auth/refresh`, () =>
        HttpResponse.json({ detail: 'Session has been revoked' }, { status: 401 }),
      ),
    )

    renderRoute(<ProtectedRoute />)

    expect(await screen.findByText('Sign in')).toBeInTheDocument()
  })
})
