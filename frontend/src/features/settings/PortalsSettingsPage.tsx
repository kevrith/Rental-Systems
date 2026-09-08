import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { portalsApi } from '@/api'
import type { PortalName } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Field,
  Input,
  PageLoader,
} from '@/components/ui'
import { dateTime, errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const PORTALS: { value: PortalName; label: string }[] = [
  { value: 'buyrentkenya', label: 'BuyRentKenya' },
  { value: 'pigiame', label: 'PigiaMe' },
]

/**
 * Property portal connections (Sprint 23, US-099).
 *
 * Connecting a portal here is what makes a published vacancy listing show up
 * there too — the listing itself still has to be created and published from
 * the vacancy desk, same as before this sprint.
 */
export function PortalsSettingsPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, { api_key: string; account_id: string }>>({})

  const connections = useQuery({ queryKey: queryKeys.portalConnections, queryFn: portalsApi.list })

  const save = useMutation({
    mutationFn: (portal: PortalName) =>
      portalsApi.save(portal, {
        api_key: drafts[portal]?.api_key ?? '',
        account_id: drafts[portal]?.account_id || undefined,
      }),
    onSuccess: async (_result, portal) => {
      setError(null)
      setNotice(`Connected to ${PORTALS.find((p) => p.value === portal)?.label}.`)
      setDrafts((current) => ({ ...current, [portal]: { api_key: '', account_id: '' } }))
      await queryClient.invalidateQueries({ queryKey: queryKeys.portalConnections })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const disconnect = useMutation({
    mutationFn: (portal: PortalName) => portalsApi.remove(portal),
    onSuccess: async () => {
      setError(null)
      setNotice('Disconnected. Listings already published there stay up until they expire.')
      await queryClient.invalidateQueries({ queryKey: queryKeys.portalConnections })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (connections.isPending) return <PageLoader />

  return (
    <div>
      <PageHeader
        title="Property portals"
        description="Auto-publish your vacant units to listing portals, and take them down the moment they're let."
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
        {PORTALS.map((portal) => {
          const existing = connections.data?.find((c) => c.portal === portal.value)
          const draft = drafts[portal.value] ?? { api_key: '', account_id: '' }
          return (
            <Card key={portal.value}>
              <CardHeader>
                <CardTitle>{portal.label}</CardTitle>
              </CardHeader>
              <CardBody className="space-y-4">
                {existing?.configured ? (
                  <Alert tone="success">
                    <CheckCircle2 className="mr-1.5 inline h-4 w-4" />
                    Connected{existing.account_id ? ` as ${existing.account_id}` : ''}.
                    {existing.last_synced_at && <> Last published {dateTime(existing.last_synced_at)}.</>}
                    {existing.last_error && (
                      <span className="mt-1 block text-danger-700">{existing.last_error}</span>
                    )}
                  </Alert>
                ) : (
                  <Alert tone="info">Not connected.</Alert>
                )}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="API key" required>
                    <Input
                      type="password"
                      placeholder={existing?.configured ? 'Enter again to replace' : ''}
                      value={draft.api_key}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [portal.value]: { ...draft, api_key: event.target.value },
                        }))
                      }
                    />
                  </Field>
                  <Field label="Account ID" hint="Optional — as given by the portal">
                    <Input
                      value={draft.account_id}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [portal.value]: { ...draft, account_id: event.target.value },
                        }))
                      }
                    />
                  </Field>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    loading={save.isPending && save.variables === portal.value}
                    disabled={!draft.api_key.trim()}
                    onClick={() => save.mutate(portal.value)}
                  >
                    {existing?.configured ? 'Replace API key' : 'Connect'}
                  </Button>
                  {existing?.configured && (
                    <Button
                      variant="ghost"
                      icon={<Trash2 className="h-4 w-4" />}
                      loading={disconnect.isPending && disconnect.variables === portal.value}
                      onClick={() => disconnect.mutate(portal.value)}
                    >
                      Disconnect
                    </Button>
                  )}
                </div>
              </CardBody>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
