import { useQuery } from '@tanstack/react-query'
import {
  Building2,
  DoorOpen,
  FileText,
  Search,
  User,
  Wrench,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { searchApi } from '@/api'
import type { SearchResult } from '@/api/types'
import { Spinner } from '@/components/ui'
import { cn } from '@/lib/cn'
import { queryKeys } from '@/lib/query-client'
import { useCommandPaletteStore } from '@/store/command-palette-store'

const TYPE_ICON: Record<string, typeof User> = {
  tenant: User,
  property: Building2,
  unit: DoorOpen,
  invoice: FileText,
  maintenance_request: Wrench,
}

const TYPE_LABEL: Record<string, string> = {
  tenant: 'Tenant',
  property: 'Property',
  unit: 'Unit',
  invoice: 'Invoice',
  maintenance_request: 'Maintenance',
}

/** Global Cmd/Ctrl+K search — mounted once in AppShell, opens over any screen. */
export function CommandPalette() {
  const open = useCommandPaletteStore((state) => state.open)
  const setOpen = useCommandPaletteStore((state) => state.setOpen)
  const toggle = useCommandPaletteStore((state) => state.toggle)
  const [raw, setRaw] = useState('')
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        toggle()
      } else if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [toggle, setOpen])

  useEffect(() => {
    if (!open) {
      setRaw('')
      setQuery('')
      setActiveIndex(0)
    }
  }, [open])

  // Debounced: a search fires 200ms after typing stops, not on every keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(raw), 200)
    return () => window.clearTimeout(timer)
  }, [raw])

  const { data, isFetching } = useQuery({
    queryKey: queryKeys.search(query),
    queryFn: () => searchApi.query(query),
    enabled: open && query.trim().length >= 2,
  })

  const results = useMemo(() => data ?? [], [data])

  useEffect(() => {
    setActiveIndex(0)
  }, [results])

  const go = (result: SearchResult) => {
    setOpen(false)
    navigate(result.url)
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 px-4 pt-[12vh]">
      <div aria-hidden className="absolute inset-0" onClick={() => setOpen(false)} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className="relative flex max-h-[70vh] w-full max-w-xl flex-col overflow-hidden rounded-card bg-white shadow-xl"
      >
        <div className="flex items-center gap-2.5 border-b border-slate-100 px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            autoFocus
            value={raw}
            onChange={(event) => setRaw(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActiveIndex((index) => Math.min(index + 1, results.length - 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActiveIndex((index) => Math.max(index - 1, 0))
              } else if (event.key === 'Enter' && results[activeIndex]) {
                go(results[activeIndex])
              }
            }}
            placeholder="Search tenants, properties, units, invoices…"
            className="w-full border-0 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
          />
          {isFetching && <Spinner className="h-4 w-4 shrink-0 text-slate-400" />}
          <kbd className="hidden shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-400 sm:inline">
            Esc
          </kbd>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {query.trim().length < 2 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-400">
              Type at least 2 characters to search.
            </p>
          ) : results.length === 0 && !isFetching ? (
            <p className="px-4 py-8 text-center text-sm text-slate-400">
              No results for &ldquo;{query}&rdquo;.
            </p>
          ) : (
            <ul className="py-1.5">
              {results.map((result, index) => {
                const Icon = TYPE_ICON[result.type] ?? Search
                return (
                  <li key={`${result.type}-${result.id}`}>
                    <button
                      type="button"
                      onClick={() => go(result)}
                      onMouseEnter={() => setActiveIndex(index)}
                      className={cn(
                        'flex w-full items-center gap-3 px-4 py-2.5 text-left',
                        index === activeIndex ? 'bg-brand-50' : 'hover:bg-slate-50',
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-slate-400" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-slate-900">
                          {result.title}
                        </span>
                        <span className="block truncate text-xs text-slate-500">{result.subtitle}</span>
                      </span>
                      <span className="shrink-0 text-[11px] uppercase tracking-wide text-slate-400">
                        {TYPE_LABEL[result.type] ?? result.type}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
