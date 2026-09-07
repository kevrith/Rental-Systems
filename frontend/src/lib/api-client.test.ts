import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { API_BASE_URL, apiClient, geoHeaders } from '@/lib/api-client'
import { useAuthStore } from '@/store/auth-store'

/**
 * The interceptor in `api-client.ts` carries the single most dangerous piece of
 * logic in the frontend: refresh tokens rotate on every use, so two concurrent
 * 401s that each call `/auth/refresh` make the server treat the second as a
 * stolen token and revoke every session the user has. The code collapses
 * concurrent refreshes into one shared promise to prevent exactly that.
 *
 * Intercepted at the network layer with MSW rather than by mocking axios,
 * because the refresh goes out on a *second*, module-private axios instance —
 * an adapter bound to `apiClient` would never see it, and the test would pass
 * while testing nothing.
 */

const url = (path: string) => `${API_BASE_URL}${path}`

let refreshCalls = 0
const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  refreshCalls = 0
})
afterAll(() => server.close())

beforeEach(() => {
  useAuthStore.getState().logout()
})

function signIn(): void {
  useAuthStore.getState().setSession({ accessToken: 'access-1', refreshToken: 'refresh-1' })
}

/** A refresh endpoint that counts how many times it was actually called. */
function countingRefresh(status = 200) {
  return http.post(url('/auth/refresh'), () => {
    refreshCalls += 1
    if (status !== 200) {
      return HttpResponse.json({ detail: 'Session has been revoked' }, { status })
    }
    return HttpResponse.json({ access_token: 'access-2', refresh_token: 'refresh-2' })
  })
}

describe('request interceptor', () => {
  it('attaches the bearer token and a device id', async () => {
    signIn()
    let seen: Headers | undefined
    server.use(
      http.get(url('/properties'), ({ request }) => {
        seen = request.headers
        return HttpResponse.json([])
      }),
    )

    await apiClient.get('/properties')

    expect(seen?.get('authorization')).toBe('Bearer access-1')
    expect(seen?.get('x-device-id')).toBeTruthy()
  })

  it('sends no Authorization header when signed out', async () => {
    let seen: Headers | undefined
    server.use(
      http.get(url('/listings/abc'), ({ request }) => {
        seen = request.headers
        return HttpResponse.json({})
      }),
    )

    await apiClient.get('/listings/abc')

    expect(seen?.get('authorization')).toBeNull()
  })
})

describe('refresh on 401', () => {
  it('leaves a 403 alone — the role is wrong, refreshing cannot fix it', async () => {
    signIn()
    server.use(
      http.get(url('/agency/dashboard'), () =>
        HttpResponse.json({ detail: 'Not your organization' }, { status: 403 }),
      ),
      countingRefresh(),
    )

    await expect(apiClient.get('/agency/dashboard')).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(refreshCalls).toBe(0)
    // Still signed in: a 403 is not a session problem.
    expect(useAuthStore.getState().accessToken).toBe('access-1')
  })

  it('retries the original request once with the refreshed token', async () => {
    signIn()
    let attempts = 0
    server.use(
      http.get(url('/dashboard'), ({ request }) => {
        attempts += 1
        if (attempts === 1) return HttpResponse.json({ detail: 'expired' }, { status: 401 })
        expect(request.headers.get('authorization')).toBe('Bearer access-2')
        return HttpResponse.json({ collected: 1 })
      }),
      countingRefresh(),
    )

    const response = await apiClient.get('/dashboard')

    expect(response.data).toEqual({ collected: 1 })
    expect(useAuthStore.getState().accessToken).toBe('access-2')
    expect(refreshCalls).toBe(1)
  })

  it('collapses concurrent 401s into a single refresh', async () => {
    signIn()
    const seenTokens: (string | null)[] = []
    let firstPass = true
    server.use(
      http.get(url('/dashboard'), ({ request }) => {
        const auth = request.headers.get('authorization')
        seenTokens.push(auth)
        if (auth === 'Bearer access-1') return HttpResponse.json({ detail: 'expired' }, { status: 401 })
        return HttpResponse.json({ ok: firstPass ? (firstPass = false) : true })
      }),
      http.get(url('/arrears'), ({ request }) => {
        const auth = request.headers.get('authorization')
        if (auth === 'Bearer access-1') return HttpResponse.json({ detail: 'expired' }, { status: 401 })
        return HttpResponse.json({ ok: true })
      }),
      countingRefresh(),
    )

    // Two requests in flight together, both holding the stale token. The
    // second must wait on the first refresh rather than starting its own —
    // presenting an already-rotated refresh token is what the server treats as
    // theft, and it responds by revoking every session the user has.
    await Promise.all([apiClient.get('/dashboard'), apiClient.get('/arrears')])

    expect(refreshCalls).toBe(1)
    expect(useAuthStore.getState().accessToken).toBe('access-2')
  })

  it('does not retry a second time if the retried request also 401s', async () => {
    signIn()
    server.use(
      http.get(url('/dashboard'), () => HttpResponse.json({ detail: 'expired' }, { status: 401 })),
      countingRefresh(),
    )

    await expect(apiClient.get('/dashboard')).rejects.toMatchObject({
      response: { status: 401 },
    })
    // One refresh, not an infinite loop.
    expect(refreshCalls).toBe(1)
  })

  it('signs the user out when the refresh itself is rejected', async () => {
    signIn()
    server.use(
      http.get(url('/dashboard'), () => HttpResponse.json({ detail: 'expired' }, { status: 401 })),
      countingRefresh(401),
    )

    await expect(apiClient.get('/dashboard')).rejects.toBeTruthy()
    expect(useAuthStore.getState().accessToken).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('rejects without refreshing when there is no refresh token at all', async () => {
    useAuthStore.getState().setTokens({ accessToken: 'access-1', refreshToken: '' })
    server.use(
      http.get(url('/dashboard'), () => HttpResponse.json({ detail: 'expired' }, { status: 401 })),
      countingRefresh(),
    )

    await expect(apiClient.get('/dashboard')).rejects.toBeTruthy()
    expect(refreshCalls).toBe(0)
    expect(useAuthStore.getState().accessToken).toBeNull()
  })
})

describe('geoHeaders', () => {
  it('formats coordinates the way the backend parses them', () => {
    expect(geoHeaders({ latitude: -1.2921, longitude: 36.8219 })).toEqual({
      'X-Geo-Position': '-1.2921,36.8219',
    })
  })

  it('sends nothing when the browser refused location', () => {
    expect(geoHeaders(null)).toEqual({})
  })
})
