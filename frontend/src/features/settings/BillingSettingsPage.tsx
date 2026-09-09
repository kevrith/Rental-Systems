import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, CreditCard } from 'lucide-react'
import { useState } from 'react'

import { subscriptionApi } from '@/api'
import type { BillingInterval, Subscription } from '@/api/types'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const PLAN_LABELS: Record<string, string> = {
  starter: 'Starter',
  professional: 'Professional',
  business: 'Business',
}

const STATUS_TONE = {
  active: 'success',
  past_due: 'warn',
  lapsed: 'danger',
  cancelled: 'neutral',
} as const

export function BillingSettingsPage() {
  const queryClient = useQueryClient()
  const [interval, setInterval] = useState<BillingInterval>('monthly')
  const [error, setError] = useState<string | null>(null)

  const plans = useQuery({ queryKey: queryKeys.billingPlans, queryFn: subscriptionApi.plans })
  const subscription = useQuery({
    queryKey: queryKeys.subscription,
    queryFn: subscriptionApi.current,
  })
  const invoices = useQuery({
    queryKey: queryKeys.subscriptionInvoices,
    queryFn: subscriptionApi.invoices,
  })

  const checkout = useMutation({
    mutationFn: (plan: string) => subscriptionApi.checkout({ plan, interval }),
    onSuccess: (result) => {
      window.location.href = result.authorization_url
    },
    onError: (checkoutError) => setError(errorMessage(checkoutError)),
  })

  const cancel = useMutation({
    mutationFn: subscriptionApi.cancel,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['billing'] })
    },
    onError: (cancelError) => setError(errorMessage(cancelError)),
  })

  if (subscription.isPending) return <Skeleton className="h-40" />

  const current = subscription.data

  return (
    <div className="space-y-5">
      {error && (
        <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
          {error}
        </Alert>
      )}

      {current && <CurrentPlan subscription={current} onCancel={() => cancel.mutate()} />}

      <Card>
        <CardHeader>
          <CardTitle>{current ? 'Change plan' : 'Choose a plan'}</CardTitle>
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
            {(['monthly', 'annual'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setInterval(option)}
                className={
                  interval === option
                    ? 'rounded-md bg-white px-3 py-1 font-medium shadow-sm dark:bg-slate-900'
                    : 'rounded-md px-3 py-1 text-slate-500'
                }
              >
                {option === 'monthly' ? 'Monthly' : 'Annual'}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {plans.data?.map((plan) => {
            const price = interval === 'annual' ? plan.annual : plan.monthly
            const isCurrent = current?.plan === plan.id && current.interval === interval
            return (
              <div
                key={plan.id}
                className="rounded-card border border-slate-200 p-4 dark:border-slate-700"
              >
                <p className="font-semibold text-slate-900 dark:text-slate-100">
                  {PLAN_LABELS[plan.id] ?? humanize(plan.id)}
                </p>
                <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
                  {kes(price)}
                </p>
                <p className="text-xs text-slate-500">
                  per {interval === 'annual' ? 'year' : 'month'}
                  {interval === 'annual' ? ' — two months free' : ''}
                </p>
                <Button
                  className="mt-3 w-full justify-center"
                  variant={isCurrent ? 'secondary' : 'primary'}
                  disabled={isCurrent}
                  loading={checkout.isPending && checkout.variables === plan.id}
                  onClick={() => {
                    setError(null)
                    checkout.mutate(plan.id)
                  }}
                >
                  {isCurrent ? 'Current plan' : 'Choose'}
                </Button>
              </div>
            )
          })}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Billing history</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {!invoices.data?.length ? (
            <EmptyState
              icon={<CreditCard className="h-6 w-6" />}
              title="Nothing billed yet"
              description="Invoices for your subscription will appear here."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Period</Th>
                  <Th>Amount</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {invoices.data.map((invoice) => (
                  <tr key={invoice.id}>
                    <Td className="font-mono text-xs">{invoice.reference_code}</Td>
                    <Td className="text-slate-600 dark:text-slate-300">
                      {shortDate(invoice.period_start)} to {shortDate(invoice.period_end)}
                    </Td>
                    <Td>{kes(invoice.amount)}</Td>
                    <Td>
                      <Badge
                        tone={
                          invoice.status === 'paid'
                            ? 'success'
                            : invoice.status === 'failed'
                              ? 'danger'
                              : 'neutral'
                        }
                      >
                        {humanize(invoice.status)}
                      </Badge>
                      {invoice.failure_reason && (
                        <p className="mt-0.5 text-xs text-danger-600">{invoice.failure_reason}</p>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function CurrentPlan({
  subscription,
  onCancel,
}: {
  subscription: Subscription
  onCancel: () => void
}) {
  const lapsed = subscription.status === 'lapsed'
  const pastDue = subscription.status === 'past_due'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your plan</CardTitle>
        <Badge tone={STATUS_TONE[subscription.status]}>{humanize(subscription.status)}</Badge>
      </CardHeader>
      <CardBody className="space-y-3">
        {lapsed && (
          <Alert tone="danger" title="Your subscription is unpaid" icon={<AlertCircle className="h-4 w-4" />}>
            Your data is safe and fully visible, but you cannot add or change anything until the
            balance is settled.
          </Alert>
        )}
        {pastDue && (
          <Alert tone="warn" title="We could not charge your card" icon={<AlertCircle className="h-4 w-4" />}>
            We will try again{subscription.grace_ends_at ? ` until ${shortDate(subscription.grace_ends_at)}` : ''}.
            Update your card to avoid losing the ability to add or change data.
          </Alert>
        )}

        <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Row label="Plan" value={`${PLAN_LABELS[subscription.plan] ?? humanize(subscription.plan)} (${humanize(subscription.interval)})`} />
          <Row label="Amount" value={kes(subscription.amount)} />
          <Row label="Current period ends" value={shortDate(subscription.current_period_end)} />
          <Row
            label={subscription.cancelled_at ? 'Access until' : 'Next charge'}
            value={
              subscription.cancelled_at
                ? shortDate(subscription.current_period_end)
                : shortDate(subscription.next_billing_date)
            }
          />
          <Row
            label="Card"
            value={
              subscription.card_last4
                ? `${humanize(subscription.card_brand ?? 'card')} ending ${subscription.card_last4}`
                : 'None saved'
            }
          />
        </div>

        {!subscription.cancelled_at && (
          <Button variant="secondary" onClick={onCancel}>
            Cancel subscription
          </Button>
        )}
        {subscription.cancelled_at && (
          <p className="flex items-center gap-1.5 text-sm text-slate-500">
            <CheckCircle2 className="h-4 w-4" />
            Cancelled. You keep full access until {shortDate(subscription.current_period_end)}.
          </p>
        )}
      </CardBody>
    </Card>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="font-medium text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  )
}
