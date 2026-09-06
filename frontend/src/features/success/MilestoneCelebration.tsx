import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PartyPopper } from 'lucide-react'

import { customerSuccessApi } from '@/api'
import type { MilestoneKey } from '@/api/types'
import { Confetti } from '@/components/Confetti'
import { Button } from '@/components/ui'
import { queryKeys } from '@/lib/query-client'

const MILESTONE_COPY: Record<MilestoneKey, string> = {
  payments_100: "You've processed 100 payments through RentFlow!",
  tenants_50: "You've reached 50 tenants — your portfolio is growing.",
  first_etims_receipt: 'Your first eTIMS-compliant receipt has gone out.',
}

/** Per-organization milestone celebrations (US-092). Renders the oldest
 * unacknowledged milestone as a dismissible banner; acknowledging one reveals
 * the next, if any. */
export function MilestoneCelebration() {
  const queryClient = useQueryClient()

  const pending = useQuery({
    queryKey: queryKeys.pendingMilestones,
    queryFn: customerSuccessApi.pendingMilestones,
    staleTime: 5 * 60_000,
  })

  const acknowledge = useMutation({
    mutationFn: (key: string) => customerSuccessApi.acknowledgeMilestone(key),
    onSuccess: (_data, key) => {
      queryClient.setQueryData(
        queryKeys.pendingMilestones,
        (queryClient.getQueryData(queryKeys.pendingMilestones) as { milestone_key: string }[] | undefined)?.filter(
          (m) => m.milestone_key !== key,
        ) ?? [],
      )
    },
  })

  const milestone = pending.data?.[0]
  if (!milestone) return null

  return (
    <div className="fixed inset-x-4 bottom-4 z-40 sm:inset-x-auto sm:right-6 sm:w-96">
      <div className="relative overflow-hidden rounded-xl border border-money-100 bg-white p-4 shadow-xl">
        <Confetti pieces={16} />
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-money-100 text-money-700">
            <PartyPopper className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-900">Milestone reached!</p>
            <p className="mt-0.5 text-sm text-slate-600">{MILESTONE_COPY[milestone.milestone_key]}</p>
            <Button
              size="sm"
              variant="secondary"
              className="mt-3"
              loading={acknowledge.isPending}
              onClick={() => acknowledge.mutate(milestone.milestone_key)}
            >
              Nice!
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
