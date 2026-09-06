import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { customerSuccessApi } from '@/api'
import { Button, Dialog, Textarea } from '@/components/ui'
import { cn } from '@/lib/cn'
import { queryKeys } from '@/lib/query-client'

const TRIGGER_COPY: Record<string, string> = {
  first_payment: "You've just recorded your first payment — how's RentFlow working out so far?",
  first_inspection: "You've completed your first inspection — how likely are you to recommend RentFlow?",
  first_month: "You've been with RentFlow a month now — how likely are you to recommend us to a peer?",
}

/** Post-milestone NPS survey (US-092). Polled once per session rather than on
 * a timer — a pending prompt only ever appears after a milestone-worthy
 * write, so there is nothing to gain from checking more often. */
export function NpsPopup() {
  const queryClient = useQueryClient()
  const [score, setScore] = useState<number | null>(null)
  const [comment, setComment] = useState('')

  const pending = useQuery({
    queryKey: queryKeys.pendingNps,
    queryFn: customerSuccessApi.pendingNps,
    staleTime: 5 * 60_000,
  })

  const respond = useMutation({
    mutationFn: () =>
      customerSuccessApi.respondToNps(pending.data!.id, { score: score!, comment: comment || undefined }),
    onSuccess: () => {
      queryClient.setQueryData(queryKeys.pendingNps, null)
      setScore(null)
      setComment('')
    },
  })

  if (!pending.data) return null

  return (
    <Dialog
      open
      onClose={() => queryClient.setQueryData(queryKeys.pendingNps, null)}
      title="Quick question"
      description={TRIGGER_COPY[pending.data.trigger_event] ?? 'How likely are you to recommend RentFlow?'}
      footer={
        <Button className="ml-auto" disabled={score === null} loading={respond.isPending} onClick={() => respond.mutate()}>
          Submit
        </Button>
      }
    >
      <div className="flex justify-between gap-1">
        {Array.from({ length: 11 }, (_, value) => (
          <button
            key={value}
            type="button"
            onClick={() => setScore(value)}
            className={cn(
              'h-9 flex-1 rounded-lg text-sm font-medium',
              score === value
                ? 'bg-brand-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
            )}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs text-slate-400">
        <span>Not likely</span>
        <span>Very likely</span>
      </div>
      <Textarea
        className="mt-4"
        placeholder="Anything you'd like to add? (optional)"
        value={comment}
        onChange={(event) => setComment(event.target.value)}
        rows={3}
      />
    </Dialog>
  )
}
