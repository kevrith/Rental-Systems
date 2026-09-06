import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ActivitySquare,
  AlertCircle,
  Ban,
  Check,
  Copy,
  KeyRound,
  Plus,
  Webhook as WebhookIcon,
} from 'lucide-react'
import { useState } from 'react'

import { apiKeysApi, webhooksApi } from '@/api'
import type { ApiKey, ApiKeyScope, WebhookDelivery, WebhookEndpoint, WebhookEvent } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  Field,
  Input,
  Skeleton,
  Table,
  Tabs,
  Tab,
  Td,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const API_KEY_SCOPES: ApiKeyScope[] = [
  'properties:read',
  'units:read',
  'tenants:read',
  'payments:read',
  'invoices:read',
]

const WEBHOOK_EVENTS: WebhookEvent[] = [
  'payment.received',
  'tenant.created',
  'lease.signed',
  'inspection.completed',
  'maintenance.status_changed',
  'invoice.generated',
]

function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex gap-2">
      <Input readOnly value={value} className="font-mono text-xs" />
      <Button
        type="button"
        variant="outline"
        icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        onClick={async () => {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          window.setTimeout(() => setCopied(false), 2000)
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </Button>
    </div>
  )
}

export function DeveloperPage() {
  const [tab, setTab] = useState<'api-keys' | 'webhooks'>('api-keys')

  return (
    <div>
      <PageHeader
        title="Developer"
        description="API keys and webhooks for integrating your own systems with RentFlow."
      />
      <Tabs value={tab} onChange={(value) => setTab(value as typeof tab)}>
        <Tab value="api-keys">API keys</Tab>
        <Tab value="webhooks">Webhooks</Tab>
      </Tabs>
      <div className="mt-4">
        {tab === 'api-keys' ? <ApiKeysSection /> : <WebhooksSection />}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ API keys

function ApiKeysSection() {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [revealed, setRevealed] = useState<{ name: string; api_key: string } | null>(null)

  const keys = useQuery({ queryKey: queryKeys.apiKeys, queryFn: apiKeysApi.list })

  const revoke = useMutation({
    mutationFn: (id: string) => apiKeysApi.revoke(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys }),
  })

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>API keys</CardTitle>
          <p className="text-sm text-slate-500">
            Read-only access to your properties, units, tenants, payments and invoices.
          </p>
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
          Create key
        </Button>
      </CardHeader>
      <CardBody>
        {keys.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : keys.data?.length ? (
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th>Key</Th>
                  <Th>Scopes</Th>
                  <Th>Last used</Th>
                  <Th>Status</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {keys.data.map((key) => (
                  <ApiKeyRow key={key.id} apiKey={key} onRevoke={() => revoke.mutate(key.id)} />
                ))}
              </tbody>
            </Table>
          </div>
        ) : (
          <EmptyState
            icon={<KeyRound className="h-6 w-6" />}
            title="No API keys yet"
            description="Create a key to give an integration read access to your data."
            action={
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
                Create key
              </Button>
            }
          />
        )}
      </CardBody>

      <CreateApiKeyDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(key) => {
          setCreating(false)
          setRevealed({ name: key.name, api_key: key.api_key })
        }}
      />

      <Dialog
        open={revealed !== null}
        onClose={() => setRevealed(null)}
        title={`"${revealed?.name}" created`}
        description="Copy this key now — it will not be shown again."
        footer={<Button onClick={() => setRevealed(null)}>Done</Button>}
      >
        {revealed && <CopyField value={revealed.api_key} />}
      </Dialog>
    </Card>
  )
}

function ApiKeyRow({ apiKey, onRevoke }: { apiKey: ApiKey; onRevoke: () => void }) {
  const [showUsage, setShowUsage] = useState(false)
  const usage = useQuery({
    queryKey: queryKeys.apiKeyUsage(apiKey.id),
    queryFn: () => apiKeysApi.usage(apiKey.id),
    enabled: showUsage,
  })

  const revoked = apiKey.revoked_at !== null
  const expired = apiKey.expires_at !== null && new Date(apiKey.expires_at) < new Date()

  return (
    <>
      <tr>
        <Td className="font-medium text-slate-900">{apiKey.name}</Td>
        <Td className="font-mono text-xs text-slate-500">{apiKey.key_prefix}…</Td>
        <Td>
          <div className="flex flex-wrap gap-1">
            {apiKey.scopes.map((scope) => (
              <Badge key={scope} tone="neutral">
                {scope}
              </Badge>
            ))}
          </div>
        </Td>
        <Td className="text-sm text-slate-500">
          {apiKey.last_used_at ? relative(apiKey.last_used_at) : 'Never'}
        </Td>
        <Td>
          {revoked ? (
            <Badge tone="danger">Revoked</Badge>
          ) : expired ? (
            <Badge tone="warn">Expired</Badge>
          ) : (
            <Badge tone="success">Active</Badge>
          )}
        </Td>
        <Td>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              icon={<ActivitySquare className="h-3.5 w-3.5" />}
              onClick={() => setShowUsage(true)}
            >
              Usage
            </Button>
            {!revoked && (
              <Button variant="outline" size="sm" icon={<Ban className="h-3.5 w-3.5" />} onClick={onRevoke}>
                Revoke
              </Button>
            )}
          </div>
        </Td>
      </tr>
      <Dialog
        open={showUsage}
        onClose={() => setShowUsage(false)}
        title={`Usage — ${apiKey.name}`}
        footer={<Button onClick={() => setShowUsage(false)}>Close</Button>}
      >
        {usage.isPending ? (
          <Skeleton className="h-24" />
        ) : usage.data ? (
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Requests today</span>
              <span className="font-medium">{usage.data.requests_today}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Requests, last 7 days</span>
              <span className="font-medium">{usage.data.requests_last_7_days}</span>
            </div>
            <div>
              <p className="mb-1 text-slate-500">Endpoints hit</p>
              {Object.keys(usage.data.endpoints_hit).length ? (
                <ul className="space-y-1">
                  {Object.entries(usage.data.endpoints_hit).map(([endpoint, count]) => (
                    <li key={endpoint} className="flex justify-between font-mono text-xs">
                      <span>{endpoint}</span>
                      <span>{count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400">No requests yet</p>
              )}
            </div>
          </div>
        ) : null}
      </Dialog>
    </>
  )
}

function CreateApiKeyDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (key: { name: string; api_key: string }) => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<ApiKeyScope[]>([])
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => apiKeysApi.create({ name: name.trim(), scopes }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys })
      setName('')
      setScopes([])
      onCreated(created)
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  const toggle = (scope: ApiKeyScope) =>
    setScopes((state) => (state.includes(scope) ? state.filter((item) => item !== scope) : [...state, scope]))

  const valid = name.trim().length > 1 && scopes.length > 0

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Create an API key"
      description="Give it a name so you remember what it's for, and only the scopes it needs."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Create key
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Name" required>
          <Input
            placeholder="Accounting integration"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Scopes" required>
          <div className="flex flex-wrap gap-2">
            {API_KEY_SCOPES.map((scope) => {
              const selected = scopes.includes(scope)
              return (
                <button
                  key={scope}
                  type="button"
                  onClick={() => toggle(scope)}
                  className={
                    selected
                      ? 'rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white'
                      : 'rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50'
                  }
                >
                  {scope}
                </button>
              )
            })}
          </div>
        </Field>
        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}
      </div>
    </Dialog>
  )
}

// ------------------------------------------------------------------ webhooks

function WebhooksSection() {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [revealed, setRevealed] = useState<{ url: string; secret: string } | null>(null)
  const [viewingDeliveries, setViewingDeliveries] = useState<WebhookEndpoint | null>(null)

  const endpoints = useQuery({ queryKey: queryKeys.webhookEndpoints, queryFn: webhooksApi.list })

  const archive = useMutation({
    mutationFn: (id: string) => webhooksApi.archive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.webhookEndpoints }),
  })

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Webhooks</CardTitle>
          <p className="text-sm text-slate-500">
            Push real-time events to your own systems. Up to 10 endpoints.
          </p>
        </div>
        <Button
          icon={<Plus className="h-4 w-4" />}
          disabled={(endpoints.data?.length ?? 0) >= 10}
          onClick={() => setCreating(true)}
        >
          Add endpoint
        </Button>
      </CardHeader>
      <CardBody>
        {endpoints.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : endpoints.data?.length ? (
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <Th>URL</Th>
                  <Th>Events</Th>
                  <Th>Status</Th>
                  <Th>Last delivery</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {endpoints.data.map((endpoint) => (
                  <tr key={endpoint.id}>
                    <Td className="max-w-[16rem] truncate font-mono text-xs">{endpoint.url}</Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        {endpoint.event_types.map((event) => (
                          <Badge key={event} tone="neutral">
                            {humanize(event.replace('.', ' '))}
                          </Badge>
                        ))}
                      </div>
                    </Td>
                    <Td>
                      {!endpoint.is_active ? (
                        <Badge tone="neutral">Disabled</Badge>
                      ) : endpoint.consecutive_failures > 0 ? (
                        <Badge tone="warn">{endpoint.consecutive_failures} failing</Badge>
                      ) : (
                        <Badge tone="success">Healthy</Badge>
                      )}
                    </Td>
                    <Td className="text-sm text-slate-500">
                      {endpoint.last_triggered_at ? relative(endpoint.last_triggered_at) : 'Never'}
                    </Td>
                    <Td>
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => setViewingDeliveries(endpoint)}>
                          Deliveries
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          icon={<Ban className="h-3.5 w-3.5" />}
                          onClick={() => archive.mutate(endpoint.id)}
                        >
                          Remove
                        </Button>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        ) : (
          <EmptyState
            icon={<WebhookIcon className="h-6 w-6" />}
            title="No webhook endpoints yet"
            description="Register an HTTPS endpoint to be notified when payments, tenants and leases change."
            action={
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
                Add endpoint
              </Button>
            }
          />
        )}
      </CardBody>

      <CreateWebhookDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(endpoint) => {
          setCreating(false)
          setRevealed({ url: endpoint.url, secret: endpoint.secret })
        }}
      />

      <Dialog
        open={revealed !== null}
        onClose={() => setRevealed(null)}
        title="Endpoint registered"
        description={`Use this secret to verify the X-RentFlow-Signature header on requests to ${revealed?.url}.`}
        footer={<Button onClick={() => setRevealed(null)}>Done</Button>}
      >
        {revealed && <CopyField value={revealed.secret} />}
      </Dialog>

      <DeliveriesDialog endpoint={viewingDeliveries} onClose={() => setViewingDeliveries(null)} />
    </Card>
  )
}

function CreateWebhookDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (endpoint: { url: string; secret: string }) => void
}) {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [events, setEvents] = useState<WebhookEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      webhooksApi.create({ url: url.trim(), description: description.trim() || null, event_types: events }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.webhookEndpoints })
      setUrl('')
      setDescription('')
      setEvents([])
      onCreated(created)
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  const toggle = (event: WebhookEvent) =>
    setEvents((state) => (state.includes(event) ? state.filter((item) => item !== event) : [...state, event]))

  const valid = url.trim().startsWith('https://') && events.length > 0

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a webhook endpoint"
      description="Your endpoint must be reachable over HTTPS."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Add endpoint
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Endpoint URL" required hint="Must start with https://">
          <Input
            placeholder="https://example.com/webhooks/rentflow"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </Field>
        <Field label="Description" hint="Optional">
          <Input
            placeholder="Accounting sync"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Events" required>
          <div className="flex flex-wrap gap-2">
            {WEBHOOK_EVENTS.map((event) => {
              const selected = events.includes(event)
              return (
                <button
                  key={event}
                  type="button"
                  onClick={() => toggle(event)}
                  className={
                    selected
                      ? 'rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white'
                      : 'rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50'
                  }
                >
                  {humanize(event.replace('.', ' '))}
                </button>
              )
            })}
          </div>
        </Field>
        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}
      </div>
    </Dialog>
  )
}

function DeliveriesDialog({ endpoint, onClose }: { endpoint: WebhookEndpoint | null; onClose: () => void }) {
  const deliveries = useQuery({
    queryKey: queryKeys.webhookDeliveries(endpoint?.id ?? ''),
    queryFn: () => webhooksApi.deliveries(endpoint!.id),
    enabled: endpoint !== null,
  })

  return (
    <Dialog
      open={endpoint !== null}
      onClose={onClose}
      title="Recent deliveries"
      description={endpoint?.url}
      footer={<Button onClick={onClose}>Close</Button>}
    >
      {deliveries.isPending ? (
        <Skeleton className="h-32" />
      ) : deliveries.data?.length ? (
        <ul className="max-h-96 space-y-2 overflow-y-auto">
          {deliveries.data.map((delivery: WebhookDelivery) => (
            <li key={delivery.id} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{humanize(delivery.event_type.replace('.', ' '))}</span>
                <Badge
                  tone={
                    delivery.status === 'success'
                      ? 'success'
                      : delivery.status === 'failed'
                        ? 'danger'
                        : 'warn'
                  }
                >
                  {humanize(delivery.status)}
                </Badge>
              </div>
              <div className="mt-1 flex justify-between text-xs text-slate-500">
                <span>
                  {delivery.attempt_count} attempt{delivery.attempt_count === 1 ? '' : 's'}
                  {delivery.response_status_code ? ` · HTTP ${delivery.response_status_code}` : ''}
                </span>
                <span>{dateTime(delivery.created_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">No deliveries yet.</p>
      )}
    </Dialog>
  )
}
