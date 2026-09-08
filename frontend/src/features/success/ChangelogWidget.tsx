import { useQuery } from '@tanstack/react-query'
import { Megaphone } from 'lucide-react'
import { useState } from 'react'

import { customerSuccessApi } from '@/api'
import { Dialog, Spinner } from '@/components/ui'
import { dateTime } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** In-app changelog bell (US-092). Mounted in `AppShell`'s header next to the
 * notification bell it already has. */
export function ChangelogWidget() {
  const [open, setOpen] = useState(false)

  const unseen = useQuery({
    queryKey: queryKeys.changelogUnseenCount,
    queryFn: customerSuccessApi.changelogUnseenCount,
    staleTime: 5 * 60_000,
  })

  const entries = useQuery({
    queryKey: queryKeys.changelog,
    queryFn: customerSuccessApi.changelog,
    enabled: open,
  })

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 sm:p-2"
        aria-label="What's new"
      >
        <Megaphone className="h-5 w-5" />
        {(unseen.data?.count ?? 0) > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-semibold text-white">
            {unseen.data!.count > 9 ? '9+' : unseen.data!.count}
          </span>
        )}
      </button>

      <Dialog open={open} onClose={() => setOpen(false)} title="What's new" size="md">
        {entries.isPending ? (
          <Spinner />
        ) : entries.data && entries.data.length > 0 ? (
          <ul className="space-y-4">
            {entries.data.map((entry) => (
              <li key={entry.id} className="border-b border-slate-100 pb-4 last:border-0 last:pb-0">
                <p className="text-sm font-semibold text-slate-900">{entry.title}</p>
                <p className="text-xs text-slate-400">{dateTime(entry.published_at)}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{entry.body}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No updates yet.</p>
        )}
      </Dialog>
    </>
  )
}
