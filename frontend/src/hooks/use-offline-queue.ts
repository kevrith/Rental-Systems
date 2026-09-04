import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'

import * as queue from '@/lib/offline-queue'

export type SyncState = 'synced' | 'pending' | 'syncing' | 'offline' | 'error'

/**
 * Live view of the offline queue for the sync indicator (US-025).
 *
 * The indicator is always visible in the caretaker shell, so this hook keeps
 * both the connection state and the pending count current without polling the
 * database on every render.
 */
export function useOfflineQueue() {
  const queryClient = useQueryClient()
  const [items, setItems] = useState<queue.QueuedAction[]>([])
  const [online, setOnline] = useState(() => navigator.onLine)
  const [syncing, setSyncing] = useState(false)

  const refresh = useCallback(async () => {
    setItems(await queue.list())
  }, [])

  useEffect(() => {
    void refresh()
    const unsubscribe = queue.subscribe(() => void refresh())
    const stopAutoSync = queue.startAutoSync()

    const onOnline = () => setOnline(true)
    const onOffline = () => setOnline(false)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)

    return () => {
      unsubscribe()
      stopAutoSync()
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [refresh])

  const sync = useCallback(async () => {
    setSyncing(true)
    try {
      const result = await queue.flush()
      if (result.synced > 0) {
        // Anything the queue touched may now be stale on screen.
        await queryClient.invalidateQueries()
      }
      return result
    } finally {
      setSyncing(false)
      await refresh()
    }
  }, [queryClient, refresh])

  const pending = items.filter((item) => item.status === 'pending' || item.status === 'syncing')
  const failed = items.filter((item) => item.status === 'failed')
  const conflicts = items.filter((item) => item.status === 'conflict')
  const stale = pending.filter(queue.isStale)

  let state: SyncState = 'synced'
  if (!online) state = 'offline'
  else if (syncing) state = 'syncing'
  else if (failed.length > 0 || conflicts.length > 0) state = 'error'
  else if (pending.length > 0) state = 'pending'

  return {
    items,
    pending,
    failed,
    conflicts,
    stale,
    online,
    syncing,
    state,
    sync,
    discard: queue.remove,
    clearAll: queue.clearAll,
    refresh,
  }
}

/**
 * Run a mutation online, or queue it when offline.
 *
 * Returns `queued: true` when the action was parked, so the caller can tell the
 * user their work is saved but not yet sent — never claim it succeeded.
 */
export async function submitOrQueue<T>(options: {
  run: () => Promise<T>
  method: queue.QueuedAction['method']
  url: string
  body?: unknown
  label: string
}): Promise<{ queued: boolean; data?: T }> {
  if (!navigator.onLine) {
    await queue.enqueue({
      method: options.method,
      url: options.url,
      body: options.body,
      label: options.label,
    })
    return { queued: true }
  }

  try {
    return { queued: false, data: await options.run() }
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status
    // No response at all means the request never reached the server — that is a
    // connectivity failure, so queue it rather than losing the user's work.
    if (status === undefined) {
      await queue.enqueue({
        method: options.method,
        url: options.url,
        body: options.body,
        label: options.label,
      })
      return { queued: true }
    }
    throw error
  }
}
