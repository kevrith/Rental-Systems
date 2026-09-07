import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ShieldOff } from 'lucide-react'
import { useState } from 'react'

import { securityApi } from '@/api'
import type { FraudAlertStatus } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  PageLoader,
  Tab,
  Tabs,
} from '@/components/ui'
import { dateTime, errorMessage, humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const TABS: { value: FraudAlertStatus | 'all'; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'suppressed', label: 'Suppressed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
]

/**
 * Fraud pattern review (US-097). Every alert is one flagged payment event —
 * a caretaker recording cash unusually fast, an off-hours entry, an amount
 * that doesn't match the rent, or the same amount paid twice in quick
 * succession. Suppressing a pattern here stops it from ever alerting again
 * for this organisation.
 */
export function FraudAlertsPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<FraudAlertStatus | 'all'>('open')
  const [error, setError] = useState<string | null>(null)

  const alerts = useQuery({
    queryKey: queryKeys.fraudAlerts(tab === 'all' ? undefined : tab),
    queryFn: () => securityApi.fraudAlerts(tab === 'all' ? undefined : tab),
  })

  const resolve = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'suppressed' | 'resolved' }) =>
      securityApi.resolveFraudAlert(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['security', 'fraud-alerts'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  return (
    <div>
      <PageHeader
        title="Fraud alerts"
        description="Suspicious payment patterns, flagged automatically as they happen."
      />

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <Tabs value={tab} onChange={(value) => setTab(value as FraudAlertStatus | 'all')} className="mb-4">
        {TABS.map((item) => (
          <Tab key={item.value} value={item.value}>
            {item.label}
          </Tab>
        ))}
      </Tabs>

      {alerts.isPending ? (
        <PageLoader />
      ) : alerts.data && alerts.data.length > 0 ? (
        <div className="space-y-3">
          {alerts.data.map((alert) => (
            <Card key={alert.id}>
              <CardBody className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <Badge tone={alert.status === 'open' ? 'warn' : 'neutral'}>
                      {humanize(alert.alert_type)}
                    </Badge>
                    {alert.status !== 'open' && (
                      <Badge tone={alert.status === 'suppressed' ? 'neutral' : 'success'}>
                        {humanize(alert.status)}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-slate-800">{alert.summary}</p>
                  <p className="mt-1 text-xs text-slate-400">{dateTime(alert.created_at)}</p>
                </div>
                {alert.status === 'open' && (
                  <div className="flex shrink-0 gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<ShieldOff className="h-3.5 w-3.5" />}
                      loading={resolve.isPending}
                      onClick={() => resolve.mutate({ id: alert.id, status: 'suppressed' })}
                    >
                      Not fraud — suppress
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                      loading={resolve.isPending}
                      onClick={() => resolve.mutate({ id: alert.id, status: 'resolved' })}
                    >
                      Resolve
                    </Button>
                  </div>
                )}
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<AlertTriangle className="h-6 w-6" />}
          title="Nothing here"
          description="No alerts in this view. Rapid cash payments, off-hours activity, unusual amounts and duplicate payments are flagged automatically."
        />
      )}
    </div>
  )
}
