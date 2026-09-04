/**
 * Offline action queue (US-025).
 *
 * A caretaker in a corridor with no signal must still be able to record a
 * payment, a meter reading or a maintenance request. Those actions are written
 * to IndexedDB and replayed, in order, once the connection returns.
 *
 * Two properties matter more than throughput here:
 *
 *   * **Order** — a meter reading recorded before a payment must reach the
 *     server in that order, so the queue is drained strictly FIFO and stops at
 *     the first item that fails for a retriable reason.
 *   * **No double-submission** — every queued item carries a client-generated
 *     `idempotency_key`, and an item is only removed after the server confirms.
 *     A 4xx is a decision (the server rejected it); a network error is a blip.
 */
import { openDB, type IDBPDatabase } from 'idb'

import { apiClient } from '@/lib/api-client'

const DB_NAME = 'rentflow-offline'
const DB_VERSION = 1
const STORE = 'queue'

/** Items older than this are stale enough to warn about (US-025). */
export const MAX_QUEUE_AGE_DAYS = 7

export type QueueStatus = 'pending' | 'syncing' | 'failed' | 'conflict'

export interface QueuedAction {
  id: string
  method: 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  url: string
  body?: unknown
  /** What the user did, in their words — shown in the pending-sync list. */
  label: string
  createdAt: number
  attempts: number
  status: QueueStatus
  lastError?: string
  /** Query keys to invalidate once this action lands. */
  invalidates?: string[]
}

let dbPromise: Promise<IDBPDatabase> | null = null

function db(): Promise<IDBPDatabase> {
  dbPromise ??= openDB(DB_NAME, DB_VERSION, {
    upgrade(database) {
      if (!database.objectStoreNames.contains(STORE)) {
        const store = database.createObjectStore(STORE, { keyPath: 'id' })
        store.createIndex('createdAt', 'createdAt')
      }
    },
  })
  return dbPromise
}

export async function enqueue(
  action: Omit<QueuedAction, 'id' | 'createdAt' | 'attempts' | 'status'>,
): Promise<QueuedAction> {
  const item: QueuedAction = {
    ...action,
    id: crypto.randomUUID(),
    createdAt: Date.now(),
    attempts: 0,
    status: 'pending',
  }
  const database = await db()
  await database.put(STORE, item)
  notify()
  return item
}

export async function list(): Promise<QueuedAction[]> {
  const database = await db()
  const items = (await database.getAll(STORE)) as QueuedAction[]
  return items.sort((a, b) => a.createdAt - b.createdAt)
}

export async function count(): Promise<number> {
  const database = await db()
  return database.count(STORE)
}

export async function remove(id: string): Promise<void> {
  const database = await db()
  await database.delete(STORE, id)
  notify()
}

export async function clearAll(): Promise<void> {
  const database = await db()
  await database.clear(STORE)
  notify()
}

async function update(item: QueuedAction): Promise<void> {
  const database = await db()
  await database.put(STORE, item)
}

// --------------------------------------------------------------------- syncing

export interface SyncResult {
  synced: number
  failed: number
  conflicts: QueuedAction[]
}

let syncing = false

export async function flush(): Promise<SyncResult> {
  const result: SyncResult = { synced: 0, failed: 0, conflicts: [] }

  // A second flush while one is running would replay the same items twice.
  if (syncing || !navigator.onLine) return result
  syncing = true

  try {
    for (const item of await list()) {
      if (item.status === 'conflict') continue

      item.status = 'syncing'
      item.attempts += 1
      await update(item)

      try {
        await apiClient.request({
          method: item.method,
          url: item.url,
          data: item.body,
          headers: { 'X-Idempotency-Key': item.id },
        })
        await remove(item.id)
        result.synced += 1
      } catch (error) {
        const status = (error as { response?: { status?: number } })?.response?.status
        const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
          ?.detail

        if (status === 409) {
          // Someone else changed the same thing while we were offline. Park it
          // and let the user decide (US-025).
          item.status = 'conflict'
          item.lastError = typeof detail === 'string' ? detail : 'Conflicts with a newer change'
          await update(item)
          result.conflicts.push(item)
        } else if (status && status >= 400 && status < 500) {
          // The server rejected it outright — retrying will not help.
          item.status = 'failed'
          item.lastError = typeof detail === 'string' ? detail : `Rejected (${status})`
          await update(item)
          result.failed += 1
        } else {
          // Network blip or server error: leave it pending and stop, so the
          // queue keeps its order on the next attempt.
          item.status = 'pending'
          item.lastError = 'Waiting for a connection'
          await update(item)
          break
        }
      }
    }
  } finally {
    syncing = false
    notify()
  }

  return result
}

// ------------------------------------------------------------------ subscribers

type Listener = () => void
const listeners = new Set<Listener>()

export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function notify(): void {
  for (const listener of listeners) listener()
}

/** Start syncing whenever the browser regains a connection. */
export function startAutoSync(): () => void {
  const onOnline = () => {
    void flush()
  }
  window.addEventListener('online', onOnline)

  // Also retry periodically: `online` fires on link-up, which is not the same
  // as the network actually working (captive portals, weak 3G).
  const timer = window.setInterval(() => {
    if (navigator.onLine) void flush()
  }, 30_000)

  return () => {
    window.removeEventListener('online', onOnline)
    window.clearInterval(timer)
  }
}

export function isStale(item: QueuedAction): boolean {
  return Date.now() - item.createdAt > MAX_QUEUE_AGE_DAYS * 24 * 60 * 60 * 1000
}
