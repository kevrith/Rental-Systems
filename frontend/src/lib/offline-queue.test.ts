import { HttpResponse, http } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { API_BASE_URL } from '@/lib/api-client'
import { clearAll, count, enqueue, flush, list, remove, subscribe } from '@/lib/offline-queue'
import { useAuthStore } from '@/store/auth-store'

/**
 * A caretaker records a payment in a corridor with no signal. What happens next
 * decides whether the tenant is charged once, twice, or not at all — so the two
 * properties this file exists to protect are FIFO order and no double-submission.
 *
 * The failure modes are deliberately distinguished by the code and so are the
 * tests: a 4xx is the server making a decision, a 409 is somebody else having
 * changed the same thing, and a network error is a blip that must leave the
 * item queued and stop the drain so the queue keeps its order.
 */

const url = (path: string) => `${API_BASE_URL}${path}`
const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

beforeEach(async () => {
  await clearAll()
  useAuthStore.getState().setSession({ accessToken: 'access-1', refreshToken: 'refresh-1' })
})

function offline(): void {
  Object.defineProperty(navigator, 'onLine', { value: false, configurable: true })
}

describe('enqueue', () => {
  it('stores an action with a client-generated id and a pending status', async () => {
    const item = await enqueue({
      method: 'POST',
      url: '/payments',
      body: { amount: '5000' },
      label: 'Cash payment for A1',
    })

    expect(item.id).toBeTruthy()
    expect(item.status).toBe('pending')
    expect(item.attempts).toBe(0)
    expect(await count()).toBe(1)
  })

  it('lists items oldest first, whatever order they went in', async () => {
    const first = await enqueue({ method: 'POST', url: '/a', label: 'first' })
    // `createdAt` is millisecond-resolution, so two enqueues in the same tick
    // could tie. Nudge the second so the ordering under test is unambiguous.
    await new Promise((resolve) => setTimeout(resolve, 2))
    const second = await enqueue({ method: 'POST', url: '/b', label: 'second' })

    const items = await list()
    expect(items.map((item) => item.id)).toEqual([first.id, second.id])
  })

  it('notifies subscribers so the pending-sync badge updates', async () => {
    let calls = 0
    const unsubscribe = subscribe(() => {
      calls += 1
    })

    await enqueue({ method: 'POST', url: '/a', label: 'first' })
    expect(calls).toBe(1)

    unsubscribe()
    await enqueue({ method: 'POST', url: '/b', label: 'second' })
    expect(calls).toBe(1)
  })
})

describe('flush', () => {
  it('does nothing while the browser is offline', async () => {
    offline()
    await enqueue({ method: 'POST', url: '/payments', label: 'Cash payment' })

    const result = await flush()

    expect(result).toEqual({ synced: 0, failed: 0, conflicts: [] })
    expect(await count()).toBe(1)
  })

  it('replays queued actions in order and removes them once accepted', async () => {
    const seen: string[] = []
    server.use(
      http.post(url('/payments'), async ({ request }) => {
        seen.push(((await request.json()) as { label: string }).label)
        return HttpResponse.json({ ok: true }, { status: 201 })
      }),
    )

    await enqueue({ method: 'POST', url: '/payments', body: { label: 'first' }, label: 'first' })
    await new Promise((resolve) => setTimeout(resolve, 2))
    await enqueue({ method: 'POST', url: '/payments', body: { label: 'second' }, label: 'second' })

    const result = await flush()

    expect(result.synced).toBe(2)
    expect(seen).toEqual(['first', 'second'])
    expect(await count()).toBe(0)
  })

  it('sends the item id as an idempotency key, so a replay cannot double-charge', async () => {
    let key: string | null = null
    server.use(
      http.post(url('/payments'), ({ request }) => {
        key = request.headers.get('x-idempotency-key')
        return HttpResponse.json({ ok: true }, { status: 201 })
      }),
    )

    const item = await enqueue({ method: 'POST', url: '/payments', label: 'Cash payment' })
    await flush()

    expect(key).toBe(item.id)
  })

  it('parks a 409 as a conflict for the user to resolve, and keeps it', async () => {
    server.use(
      http.post(url('/payments'), () =>
        HttpResponse.json({ detail: 'Someone recorded this already' }, { status: 409 }),
      ),
    )
    await enqueue({ method: 'POST', url: '/payments', label: 'Cash payment' })

    const result = await flush()

    expect(result.conflicts).toHaveLength(1)
    const [item] = await list()
    expect(item.status).toBe('conflict')
    expect(item.lastError).toBe('Someone recorded this already')
    expect(await count()).toBe(1)
  })

  it('skips an item already marked conflict rather than retrying it forever', async () => {
    let calls = 0
    server.use(
      http.post(url('/payments'), () => {
        calls += 1
        return HttpResponse.json({ detail: 'Conflict' }, { status: 409 })
      }),
    )
    await enqueue({ method: 'POST', url: '/payments', label: 'Cash payment' })

    await flush()
    await flush()

    expect(calls).toBe(1)
  })

  it('marks a 4xx failed — the server decided, and retrying will not help', async () => {
    server.use(
      http.post(url('/payments'), () =>
        HttpResponse.json({ detail: 'Amount must be positive' }, { status: 400 }),
      ),
    )
    await enqueue({ method: 'POST', url: '/payments', label: 'Cash payment' })

    const result = await flush()

    expect(result.failed).toBe(1)
    const [item] = await list()
    expect(item.status).toBe('failed')
    expect(item.lastError).toBe('Amount must be positive')
  })

  it('stops at a server error and leaves the rest queued, preserving order', async () => {
    let calls = 0
    server.use(
      http.post(url('/first'), () => {
        calls += 1
        return HttpResponse.json({ detail: 'boom' }, { status: 500 })
      }),
      http.post(url('/second'), () => {
        calls += 1
        return HttpResponse.json({ ok: true }, { status: 201 })
      }),
    )

    await enqueue({ method: 'POST', url: '/first', label: 'first' })
    await new Promise((resolve) => setTimeout(resolve, 2))
    await enqueue({ method: 'POST', url: '/second', label: 'second' })

    const result = await flush()

    // The second item is NOT attempted: draining past a failure would reorder
    // the queue, and a meter reading must reach the server before the payment
    // that was recorded after it.
    expect(calls).toBe(1)
    expect(result.synced).toBe(0)
    expect(await count()).toBe(2)
    const items = await list()
    expect(items[0].status).toBe('pending')
    expect(items[0].attempts).toBe(1)
    expect(items[1].attempts).toBe(0)
  })
})

describe('remove and clearAll', () => {
  it('drops one item', async () => {
    const item = await enqueue({ method: 'POST', url: '/a', label: 'first' })
    await enqueue({ method: 'POST', url: '/b', label: 'second' })

    await remove(item.id)

    expect(await count()).toBe(1)
  })

  it('empties the queue', async () => {
    await enqueue({ method: 'POST', url: '/a', label: 'first' })
    await clearAll()
    expect(await count()).toBe(0)
  })
})
