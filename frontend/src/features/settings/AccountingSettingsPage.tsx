import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { accountingApi } from '@/api'
import type { AccountingProvider } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import { Alert, Button, Card, CardBody, CardHeader, CardTitle, PageLoader } from '@/components/ui'
import { dateTime, errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const PROVIDERS: { value: AccountingProvider; label: string }[] = [
  { value: 'quickbooks', label: 'QuickBooks Online' },
  { value: 'xero', label: 'Xero' },
]

/**
 * QuickBooks / Xero connections (Sprint 23, US-100).
 *
 * Connecting redirects the browser to the provider's own consent screen;
 * `/settings/accounting?connected=<provider>` or `?error=...` is where it
 * comes back to once the backend has exchanged the authorization code.
 */
export function AccountingSettingsPage() {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const connections = useQuery({ queryKey: queryKeys.accountingConnections, queryFn: accountingApi.list })

  useEffect(() => {
    const connected = params.get('connected')
    const oauthError = params.get('error')
    if (connected) {
      setNotice(`Connected to ${PROVIDERS.find((p) => p.value === connected)?.label ?? connected}.`)
      void queryClient.invalidateQueries({ queryKey: queryKeys.accountingConnections })
    }
    if (oauthError) setError(oauthError)
    if (connected || oauthError) setParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connect = useMutation({
    mutationFn: (provider: AccountingProvider) => accountingApi.connect(provider, 'sandbox'),
    onSuccess: (result) => {
      window.location.href = result.authorize_url
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const disconnect = useMutation({
    mutationFn: (provider: AccountingProvider) => accountingApi.disconnect(provider),
    onSuccess: async () => {
      setError(null)
      setNotice('Disconnected.')
      await queryClient.invalidateQueries({ queryKey: queryKeys.accountingConnections })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const sync = useMutation({
    mutationFn: (provider: AccountingProvider) => accountingApi.sync(provider),
    onSuccess: async (result, provider) => {
      setError(null)
      setNotice(`Sync complete: ${result.synced} synced, ${result.failed} failed.`)
      await queryClient.invalidateQueries({ queryKey: queryKeys.accountingReport(provider) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.accountingConnections })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (connections.isPending) return <PageLoader />

  return (
    <div>
      <PageHeader
        title="Accounting software"
        description="Sync rent payments, maintenance costs and owner disbursements to QuickBooks or Xero."
        backTo="/settings"
        backLabel="Settings"
      />

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}
      {notice && (
        <Alert tone="success" className="mb-4">
          {notice}
        </Alert>
      )}

      <div className="space-y-4">
        {PROVIDERS.map((provider) => {
          const existing = connections.data?.find((c) => c.provider === provider.value)
          return (
            <Card key={provider.value}>
              <CardHeader>
                <CardTitle>{provider.label}</CardTitle>
              </CardHeader>
              <CardBody className="space-y-4">
                {existing ? (
                  <Alert tone="success">
                    <CheckCircle2 className="mr-1.5 inline h-4 w-4" />
                    Connected to company {existing.external_account_id} ({existing.environment}).
                    {existing.last_synced_at && <> Last synced {dateTime(existing.last_synced_at)}.</>}
                    {existing.last_error && (
                      <span className="mt-1 block text-danger-700">{existing.last_error}</span>
                    )}
                  </Alert>
                ) : (
                  <Alert tone="info">Not connected.</Alert>
                )}

                <div className="flex flex-wrap gap-2">
                  {existing ? (
                    <>
                      <Button
                        variant="secondary"
                        icon={<RefreshCw className="h-4 w-4" />}
                        loading={sync.isPending && sync.variables === provider.value}
                        onClick={() => sync.mutate(provider.value)}
                      >
                        Sync now
                      </Button>
                      <Button
                        variant="ghost"
                        loading={disconnect.isPending && disconnect.variables === provider.value}
                        onClick={() => disconnect.mutate(provider.value)}
                      >
                        Disconnect
                      </Button>
                    </>
                  ) : (
                    <Button
                      loading={connect.isPending && connect.variables === provider.value}
                      onClick={() => connect.mutate(provider.value)}
                    >
                      Connect {provider.label}
                    </Button>
                  )}
                </div>

                {existing && <AccountingSyncSummary provider={provider.value} />}
              </CardBody>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

function AccountingSyncSummary({ provider }: { provider: AccountingProvider }) {
  const report = useQuery({
    queryKey: queryKeys.accountingReport(provider),
    queryFn: () => accountingApi.report(provider),
  })
  if (!report.data || report.data.synced + report.data.failed + report.data.pending === 0) return null

  return (
    <div className="grid grid-cols-1 gap-3 border-t border-slate-100 pt-4 sm:grid-cols-3">
      <StatCard label="Synced" value={String(report.data.synced)} tone="success" />
      <StatCard
        label="Failed"
        value={String(report.data.failed)}
        tone={report.data.failed > 0 ? 'danger' : 'default'}
      />
      <StatCard label="Pending" value={String(report.data.pending)} />
    </div>
  )
}
