import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, Check, ClipboardList, CreditCard, PartyPopper, UserRound, Users } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { customerSuccessApi } from '@/api'
import type { OnboardingProgress } from '@/api/types'
import { Confetti } from '@/components/Confetti'
import { Button, Dialog } from '@/components/ui'
import { queryKeys } from '@/lib/query-client'
import { useHasPermission } from '@/store/auth-store'

const STEPS: {
  key: keyof Omit<OnboardingProgress, 'dismissed_at' | 'completed_at'>
  label: string
  description: string
  to: string
  icon: React.ReactNode
}[] = [
  {
    key: 'added_property',
    label: 'Add your first property',
    description: 'A building, compound or standalone house you manage.',
    to: '/properties/new',
    icon: <Building2 className="h-4 w-4" />,
  },
  {
    key: 'added_units',
    label: 'Add units',
    description: 'The rentable spaces inside that property.',
    to: '/units/new',
    icon: <ClipboardList className="h-4 w-4" />,
  },
  {
    key: 'invited_caretaker',
    label: 'Invite your caretaker',
    description: 'Give the person on site their own login.',
    to: '/team',
    icon: <Users className="h-4 w-4" />,
  },
  {
    key: 'added_tenant',
    label: 'Add your first tenant',
    description: 'Who is renting, and the terms of their tenancy.',
    to: '/tenants/new',
    icon: <UserRound className="h-4 w-4" />,
  },
  {
    key: 'setup_payment',
    label: 'Set up your payment account',
    description: 'Confirm the details tenants pay rent to.',
    to: '/settings/organization',
    icon: <CreditCard className="h-4 w-4" />,
  },
]

/** First-login setup wizard (US-089). Steps are marked done by hand from this
 * checklist rather than auto-detected from other screens — accurate and far
 * simpler than teaching five unrelated flows about onboarding state. */
export function OnboardingWizard() {
  const canManage = useHasPermission('onboarding:manage')
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [justCompleted, setJustCompleted] = useState(false)
  const openedOnceRef = useRef(false)

  const progress = useQuery({
    queryKey: queryKeys.onboarding,
    queryFn: customerSuccessApi.onboarding,
    enabled: canManage,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!progress.data || openedOnceRef.current) return
    openedOnceRef.current = true
    if (!progress.data.dismissed_at && !progress.data.completed_at) setOpen(true)
  }, [progress.data])

  const markStep = useMutation({
    mutationFn: (step: string) => customerSuccessApi.markOnboardingStep(step),
    onSuccess: (data) => {
      const wasIncomplete = !queryClient.getQueryData<OnboardingProgress>(queryKeys.onboarding)
        ?.completed_at
      queryClient.setQueryData(queryKeys.onboarding, data)
      if (wasIncomplete && data.completed_at) setJustCompleted(true)
    },
  })

  const dismiss = useMutation({
    mutationFn: customerSuccessApi.dismissOnboarding,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.onboarding, data)
      setOpen(false)
    },
  })

  if (!canManage || !progress.data) return null

  const data = progress.data
  const doneCount = STEPS.filter((step) => data[step.key]).length

  return (
    <>
      {!open && !data.dismissed_at && !data.completed_at && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-4 right-4 z-40 rounded-full bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg hover:bg-brand-700 sm:bottom-6 sm:right-6"
        >
          Setup guide · {doneCount}/{STEPS.length}
        </button>
      )}

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={data.completed_at ? "You're all set!" : 'Get started with RentFlow'}
        description={
          data.completed_at
            ? 'Every setup step is complete.'
            : `${doneCount} of ${STEPS.length} steps complete — do them in any order.`
        }
        size="md"
        footer={
          <div className="flex w-full items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              loading={dismiss.isPending}
              onClick={() => dismiss.mutate()}
            >
              Don't show this again
            </Button>
            <Button size="sm" onClick={() => setOpen(false)}>
              Close
            </Button>
          </div>
        }
      >
        <div className="relative">
          {justCompleted && <Confetti />}
          <ul className="space-y-2">
            {STEPS.map((step) => {
              const done = Boolean(data[step.key])
              return (
                <li
                  key={step.key}
                  className="flex items-start gap-3 rounded-lg border border-slate-100 p-3"
                >
                  <span
                    className={
                      done
                        ? 'flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-money-100 text-money-700'
                        : 'flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500'
                    }
                  >
                    {done ? <Check className="h-3.5 w-3.5" /> : step.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900">{step.label}</p>
                    <p className="text-xs text-slate-500">{step.description}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Link
                      to={step.to}
                      onClick={() => setOpen(false)}
                      className="text-xs font-medium text-brand-600 hover:text-brand-700"
                    >
                      Go
                    </Link>
                    {!done && (
                      <button
                        type="button"
                        onClick={() => markStep.mutate(step.key)}
                        disabled={markStep.isPending}
                        className="text-xs text-slate-400 hover:text-slate-700"
                      >
                        Mark done
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
          {data.completed_at && (
            <div className="mt-4 flex items-center gap-2 rounded-lg bg-money-50 p-3 text-sm text-money-700">
              <PartyPopper className="h-4 w-4" />
              Nice work — your account is fully set up.
            </div>
          )}
        </div>
      </Dialog>
    </>
  )
}
