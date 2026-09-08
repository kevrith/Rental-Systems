import {
  AlertTriangle,
  CheckCircle2,
  CloudOff,
  RefreshCw,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { useState } from 'react'

import { Alert, Badge, Button, Dialog } from '@/components/ui'
import { useOfflineQueue, type SyncState } from '@/hooks/use-offline-queue'
import { cn } from '@/lib/cn'
import { relative } from '@/lib/format'

const STATE_STYLES: Record<SyncState, { dot: string; label: string; text: string }> = {
  synced: { dot: 'bg-money-500', label: 'Synced', text: 'text-money-700' },
  pending: { dot: 'bg-warn-500', label: 'Pending sync', text: 'text-warn-700' },
  syncing: { dot: 'bg-warn-500 animate-pulse', label: 'Syncing…', text: 'text-warn-700' },
  offline: { dot: 'bg-slate-400', label: 'Offline', text: 'text-slate-600' },
  error: { dot: 'bg-danger-500', label: 'Sync problem', text: 'text-danger-700' },
}

/**
 * Always-visible connection and queue status (US-025).
 *
 * Green means everything reached the server; orange means work is saved locally
 * but not sent; red means something needs the user's attention.
 */
export function SyncIndicator({ compact = false }: { compact?: boolean }) {
  const queue = useOfflineQueue()
  const [open, setOpen] = useState(false)
  const style = STATE_STYLES[queue.state]
  const count = queue.pending.length + queue.failed.length + queue.conflicts.length

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          'inline-flex shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-white px-2 py-1.5 text-xs font-medium sm:px-3',
          style.text,
        )}
        aria-label={`Sync status: ${style.label}`}
      >
        <span className={cn('h-2 w-2 rounded-full', style.dot)} aria-hidden />
        {!compact && style.label}
        {count > 0 && (
          <span className="rounded-full bg-slate-100 px-1.5 text-[11px] text-slate-600">{count}</span>
        )}
      </button>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Sync status"
        description={
          queue.online
            ? 'Work is sent to the server as soon as it is saved.'
            : 'You are offline. Everything you record is saved on this device and sent when you reconnect.'
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
            <Button
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={() => void queue.sync()}
              loading={queue.syncing}
              disabled={!queue.online || count === 0}
            >
              Sync now
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {!queue.online && (
            <Alert tone="warn" icon={<CloudOff className="h-4 w-4" />} title="No connection">
              Keep working — nothing is lost.
            </Alert>
          )}

          {queue.stale.length > 0 && (
            <Alert
              tone="danger"
              icon={<AlertTriangle className="h-4 w-4" />}
              title={`${queue.stale.length} item(s) waiting over 7 days`}
            >
              Get online soon so this work reaches the office.
            </Alert>
          )}

          {queue.conflicts.length > 0 && (
            <Alert
              tone="danger"
              icon={<AlertTriangle className="h-4 w-4" />}
              title="Conflicting changes"
            >
              Someone else changed the same records while you were offline. Review each item below
              and re-enter it if it is still correct.
            </Alert>
          )}

          {count === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <CheckCircle2 className="h-8 w-8 text-money-500" />
              <p className="text-sm font-medium text-slate-900">Everything is synced</p>
              <p className="text-sm text-slate-500">No work is waiting on this device.</p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {queue.items.map((item) => (
                <li key={item.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{item.label}</p>
                    <p className="text-xs text-slate-500">
                      Saved {relative(new Date(item.createdAt))}
                      {item.attempts > 0 && ` · ${item.attempts} attempt(s)`}
                    </p>
                    {item.lastError && (
                      <p className="mt-0.5 text-xs text-danger-600">{item.lastError}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge
                      tone={
                        item.status === 'conflict' || item.status === 'failed'
                          ? 'danger'
                          : item.status === 'syncing'
                            ? 'warn'
                            : 'neutral'
                      }
                    >
                      {item.status}
                    </Badge>
                    {(item.status === 'failed' || item.status === 'conflict') && (
                      <button
                        type="button"
                        onClick={() => void queue.discard(item.id)}
                        aria-label="Discard"
                        className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-danger-600"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Dialog>
    </>
  )
}

/** Compact banner used at the top of caretaker screens. */
export function OfflineBanner() {
  const { online, pending } = useOfflineQueue()
  if (online && pending.length === 0) return null

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-4 py-2 text-xs font-medium',
        online ? 'bg-warn-50 text-warn-700' : 'bg-slate-800 text-white',
      )}
    >
      {online ? <UploadCloud className="h-3.5 w-3.5" /> : <CloudOff className="h-3.5 w-3.5" />}
      {online
        ? `${pending.length} item(s) waiting to sync`
        : 'Offline — your work is saved on this device'}
    </div>
  )
}
