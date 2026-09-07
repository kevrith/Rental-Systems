import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark, Plus, Users, X } from 'lucide-react'
import { useState } from 'react'

import { savedViewsApi } from '@/api'
import { Button, Input } from '@/components/ui'
import { cn } from '@/lib/cn'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

/**
 * A row of saved filter presets for one list screen — `entityType` picks the
 * screen ("tenants", "maintenance", ...), `filters` is whatever that screen's
 * own filter state looks like, and `onApply` hands a saved one back in that
 * same shape. The screen owns its filter state; this component only offers to
 * save or restore a snapshot of it.
 */
export function SavedViewsBar({
  entityType,
  filters,
  onApply,
}: {
  entityType: string
  filters: Record<string, string>
  onApply: (filters: Record<string, string>) => void
}) {
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const queryClient = useQueryClient()
  const userId = useAuthStore((state) => state.user?.id)

  const views = useQuery({
    queryKey: queryKeys.savedViews(entityType),
    queryFn: () => savedViewsApi.list(entityType),
  })

  const create = useMutation({
    mutationFn: () =>
      savedViewsApi.create({ entity_type: entityType, name: name.trim(), filters }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.savedViews(entityType) })
      setSaving(false)
      setName('')
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => savedViewsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.savedViews(entityType) }),
  })

  if (!views.data?.length && !saving) {
    return (
      <button
        type="button"
        onClick={() => setSaving(true)}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700"
      >
        <Bookmark className="h-3.5 w-3.5" />
        Save this filter
      </button>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {views.data?.map((view) => (
        <span
          key={view.id}
          className={cn(
            'group flex items-center gap-1 rounded-full border border-slate-200 py-1 pl-2.5 pr-1 text-xs text-slate-600 hover:border-brand-300 hover:bg-brand-50',
          )}
        >
          <button type="button" onClick={() => onApply(view.filters as Record<string, string>)}>
            {view.is_shared && <Users className="mr-1 inline h-3 w-3 text-slate-400" />}
            {view.name}
          </button>
          {view.user_id === userId && (
            <button
              type="button"
              onClick={() => remove.mutate(view.id)}
              aria-label={`Delete ${view.name}`}
              className="rounded-full p-0.5 text-slate-300 hover:bg-slate-200 hover:text-slate-600"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      ))}

      {saving ? (
        <span className="flex items-center gap-1.5">
          <Input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && name.trim()) create.mutate()
              if (event.key === 'Escape') setSaving(false)
            }}
            placeholder="View name"
            className="h-7 w-36 text-xs"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Save
          </Button>
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setSaving(true)}
          aria-label="Save this filter as a new view"
          className="flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2 py-1 text-xs text-slate-500 hover:border-slate-400 hover:text-slate-700"
        >
          <Plus className="h-3 w-3" />
          Save view
        </button>
      )}
    </div>
  )
}
