import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, ThumbsUp } from 'lucide-react'
import { useState } from 'react'

import { customerSuccessApi } from '@/api'
import type { FeatureRequest } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Textarea,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const STATUS_TONE = {
  open: 'neutral',
  planned: 'info',
  shipped: 'success',
  declined: 'danger',
} as const

/** The shared feature-voting board (US-092) — platform-wide, not scoped to one
 * organization: every customer sees and votes on the same list. */
export function FeatureBoardPage() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)

  const requests = useQuery({
    queryKey: queryKeys.featureBoard,
    queryFn: customerSuccessApi.featureBoard,
  })

  const vote = useMutation({
    mutationFn: (id: string) => customerSuccessApi.voteFeatureRequest(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.featureBoard })
      const previous = queryClient.getQueryData<FeatureRequest[]>(queryKeys.featureBoard)
      queryClient.setQueryData<FeatureRequest[]>(
        queryKeys.featureBoard,
        previous?.map((row) =>
          row.id === id
            ? {
                ...row,
                voted_by_me: !row.voted_by_me,
                vote_count: row.vote_count + (row.voted_by_me ? -1 : 1),
              }
            : row,
        ),
      )
      return { previous }
    },
    onError: (_error, _id, context) => {
      if (context?.previous) queryClient.setQueryData(queryKeys.featureBoard, context.previous)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.featureBoard }),
  })

  if (requests.isPending) return <PageLoader />

  const rows = [...(requests.data ?? [])].sort((a, b) => b.vote_count - a.vote_count)

  return (
    <div>
      <PageHeader
        title="Feature requests"
        description="Vote on what RentFlow should build next."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Suggest a feature
          </Button>
        }
      />

      {rows.length === 0 ? (
        <EmptyState title="No feature requests yet" description="Be the first to suggest one." />
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <Card key={row.id}>
              <CardBody className="flex items-start gap-4">
                <button
                  type="button"
                  onClick={() => vote.mutate(row.id)}
                  className={cn(
                    'flex w-14 shrink-0 flex-col items-center gap-0.5 rounded-lg border py-2 text-sm font-semibold',
                    row.voted_by_me
                      ? 'border-brand-200 bg-brand-50 text-brand-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50',
                  )}
                >
                  <ThumbsUp className="h-4 w-4" />
                  {row.vote_count}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-slate-900">{row.title}</p>
                    <Badge tone={STATUS_TONE[row.status]}>{row.status}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{row.description}</p>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <CreateFeatureRequestDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}

function CreateFeatureRequestDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')

  const create = useMutation({
    mutationFn: () => customerSuccessApi.createFeatureRequest({ title, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.featureBoard })
      setTitle('')
      setDescription('')
      onClose()
    },
  })

  return (
    <Dialog open={open} onClose={onClose} title="Suggest a feature" size="sm">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          create.mutate()
        }}
      >
        <Field label="Title">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} />
        </Field>
        <Field label="Description">
          <Textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            required
            rows={4}
          />
        </Field>
        {create.isError && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
        <Button type="submit" className="w-full" loading={create.isPending}>
          Submit
        </Button>
      </form>
    </Dialog>
  )
}
