import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Bell,
  Check,
  FileSpreadsheet,
  FileText,
  Megaphone,
  Receipt,
  RefreshCw,
  TrendingUp,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { bulkApi, propertiesApi } from '@/api'
import type { BulkOperation } from '@/api/types'
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
  Select,
  Skeleton,
  Table,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const STATUS_TONE: Record<string, 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info'> = {
  previewed: 'info',
  running: 'brand',
  completed: 'success',
  partial: 'warn',
  failed: 'danger',
  cancelled: 'neutral',
}

type ActionKind =
  | 'rent_increase'
  | 'payment_reminder'
  | 'announcement'
  | 'generate_invoices'
  | 'renewal_notices'
  | null

const ACTIONS: {
  kind: Exclude<ActionKind, null>
  label: string
  description: string
  icon: ReactNode
}[] = [
  {
    kind: 'rent_increase',
    label: 'Raise the rent',
    description: 'Across a property, with a notice to every tenant.',
    icon: <TrendingUp className="h-5 w-5" />,
  },
  {
    kind: 'payment_reminder',
    label: 'Chase arrears',
    description: 'A reminder to everyone who currently owes.',
    icon: <Bell className="h-5 w-5" />,
  },
  {
    kind: 'announcement',
    label: 'Send an announcement',
    description: 'One message to every tenant in scope.',
    icon: <Megaphone className="h-5 w-5" />,
  },
  {
    kind: 'generate_invoices',
    label: 'Raise this month’s invoices',
    description: 'For every live tenancy that has not been billed yet.',
    icon: <Receipt className="h-5 w-5" />,
  },
  {
    kind: 'renewal_notices',
    label: 'Offer renewals',
    description: 'To every lease expiring inside the window.',
    icon: <RefreshCw className="h-5 w-5" />,
  },
]

export function BulkOperationsPage() {
  const [action, setAction] = useState<ActionKind>(null)
  const [preview, setPreview] = useState<BulkOperation | null>(null)

  const operations = useQuery({
    queryKey: queryKeys.bulkOperations(),
    queryFn: () => bulkApi.list({ limit: 30 }),
  })

  return (
    <div>
      <PageHeader
        title="Bulk actions"
        description="One action, many tenants. Every one shows you exactly who it touches before it runs."
      />

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ACTIONS.map((item) => (
          <button
            key={item.kind}
            type="button"
            onClick={() => setAction(item.kind)}
            className="flex items-start gap-3 rounded-card border border-slate-200 bg-white p-4 text-left shadow-sm transition-shadow hover:shadow-md"
          >
            <span className="mt-0.5 text-brand-600">{item.icon}</span>
            <span className="min-w-0">
              <span className="block font-medium text-slate-900">{item.label}</span>
              <span className="mt-0.5 block text-sm text-slate-500">{item.description}</span>
            </span>
          </button>
        ))}
        <a
          href="/bulk/import"
          className="flex items-start gap-3 rounded-card border border-dashed border-slate-300 bg-white p-4 text-left transition-colors hover:bg-slate-50"
        >
          <span className="mt-0.5 text-slate-400">
            <FileSpreadsheet className="h-5 w-5" />
          </span>
          <span className="min-w-0">
            <span className="block font-medium text-slate-900">Import tenants</span>
            <span className="mt-0.5 block text-sm text-slate-500">
              From a spreadsheet, with a preview and per-row errors.
            </span>
          </span>
        </a>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {operations.isPending ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-12" />
              ))}
            </div>
          ) : operations.data?.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Action</Th>
                    <Th>When</Th>
                    <Th>Affected</Th>
                    <Th>Result</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {operations.data.map((operation) => (
                    <tr key={operation.id}>
                      <Td>{humanize(operation.kind)}</Td>
                      <Td className="text-slate-500">{dateTime(operation.created_at)}</Td>
                      <Td>{operation.total}</Td>
                      <Td>
                        <Badge tone={STATUS_TONE[operation.status] ?? 'neutral'}>
                          {humanize(operation.status)}
                        </Badge>
                        {operation.summary && (
                          <span className="ml-2 text-xs text-slate-500">{operation.summary}</span>
                        )}
                      </Td>
                      <Td>
                        <button
                          type="button"
                          className="text-sm text-brand-600 hover:text-brand-700"
                          onClick={() => setPreview(operation)}
                        >
                          {operation.status === 'previewed' ? 'Review' : 'Details'}
                        </button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<Megaphone className="h-6 w-6" />}
              title="Nothing run yet"
              description="Pick an action above. You will see who it affects before anything happens."
            />
          )}
        </CardBody>
      </Card>

      <BuildPreviewDialog
        action={action}
        onClose={() => setAction(null)}
        onPreviewed={(operation) => {
          setAction(null)
          setPreview(operation)
        }}
      />
      <ReviewDialog
        operation={preview}
        onClose={() => setPreview(null)}
        onChanged={(operation) => setPreview(operation)}
      />
    </div>
  )
}

function BuildPreviewDialog({
  action,
  onClose,
  onPreviewed,
}: {
  action: ActionKind
  onClose: () => void
  onPreviewed: (operation: BulkOperation) => void
}) {
  const queryClient = useQueryClient()
  const [propertyId, setPropertyId] = useState('')
  const [increaseType, setIncreaseType] = useState('percent')
  const [value, setValue] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [withinDays, setWithinDays] = useState('60')
  const [error, setError] = useState<string | null>(null)

  const properties = useQuery({
    queryKey: queryKeys.properties(),
    queryFn: () => propertiesApi.list(),
    enabled: action !== null,
  })

  const build = useMutation({
    mutationFn: () => {
      const scope = { property_id: propertyId || null }
      if (action === 'rent_increase') {
        return bulkApi.previewRentIncrease({
          ...scope,
          increase_type: increaseType,
          value,
          effective_date: effectiveDate,
        })
      }
      if (action === 'payment_reminder') return bulkApi.previewReminders(scope)
      if (action === 'announcement')
        return bulkApi.previewAnnouncement({ ...scope, subject, message })
      if (action === 'generate_invoices') return bulkApi.previewInvoiceRun(scope)
      return bulkApi.previewRenewals({ ...scope, within_days: Number(withinDays) })
    },
    onSuccess: async (operation) => {
      await queryClient.invalidateQueries({ queryKey: ['bulk'] })
      onPreviewed(operation)
    },
    onError: (buildError) => setError(errorMessage(buildError)),
  })

  const meta = ACTIONS.find((item) => item.kind === action)
  const valid =
    action !== 'rent_increase'
      ? action !== 'announcement' || (subject.length > 2 && message.length > 4)
      : Boolean(value) && Boolean(effectiveDate)

  return (
    <Dialog
      open={action !== null}
      onClose={onClose}
      title={meta?.label ?? ''}
      description="We will show you exactly who this affects before anything is sent."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={build.isPending}
            onClick={() => {
              setError(null)
              build.mutate()
            }}
          >
            Preview
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Which property?" hint="Leave blank for the whole portfolio">
          <Select value={propertyId} onChange={(event) => setPropertyId(event.target.value)}>
            <option value="">Everything</option>
            {properties.data?.map((property) => (
              <option key={property.id} value={property.id}>
                {property.name}
              </option>
            ))}
          </Select>
        </Field>

        {action === 'rent_increase' && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Increase by" required>
                <Select
                  value={increaseType}
                  onChange={(event) => setIncreaseType(event.target.value)}
                >
                  <option value="percent">A percentage</option>
                  <option value="fixed">A fixed amount</option>
                </Select>
              </Field>
              <Field label={increaseType === 'percent' ? 'Percent' : 'Amount (KES)'} required>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                />
              </Field>
            </div>
            <Field
              label="Effective from"
              required
              hint="Must give tenants their contractual notice — usually 30 days"
            >
              <Input
                type="date"
                min={today()}
                value={effectiveDate}
                onChange={(event) => setEffectiveDate(event.target.value)}
              />
            </Field>
          </>
        )}

        {action === 'announcement' && (
          <>
            <Field label="Subject" required>
              <Input
                placeholder="Water shutdown on Saturday"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
              />
            </Field>
            <Field label="Message" required>
              <Textarea
                placeholder="Water will be off on Saturday from 8am to 2pm while the tank is cleaned."
                value={message}
                onChange={(event) => setMessage(event.target.value)}
              />
            </Field>
          </>
        )}

        {action === 'renewal_notices' && (
          <Field label="Leases expiring within" hint="Days from today">
            <Input
              type="number"
              min="1"
              max="365"
              value={withinDays}
              onChange={(event) => setWithinDays(event.target.value)}
            />
          </Field>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function ReviewDialog({
  operation,
  onClose,
  onChanged,
}: {
  operation: BulkOperation | null
  onClose: () => void
  onChanged: (operation: BulkOperation) => void
}) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: () => bulkApi.execute(operation!.id),
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ['bulk'] })
      await queryClient.invalidateQueries({ queryKey: ['tenancies'] })
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      onChanged(updated)
    },
    onError: (runError) => setError(errorMessage(runError)),
  })

  const cancel = useMutation({
    mutationFn: () => bulkApi.cancel(operation!.id),
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ['bulk'] })
      onChanged(updated)
    },
    onError: (cancelError) => setError(errorMessage(cancelError)),
  })

  if (!operation) return null

  const pending = operation.status === 'previewed'
  const isIncrease = operation.kind === 'rent_increase'

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={humanize(operation.kind)}
      description={
        pending
          ? `${operation.total} tenant(s) will be affected. Nothing has happened yet.`
          : operation.summary ?? undefined
      }
      footer={
        pending ? (
          <>
            <Button
              variant="outline"
              loading={cancel.isPending}
              onClick={() => {
                setError(null)
                cancel.mutate()
              }}
            >
              Discard
            </Button>
            <Button
              disabled={operation.total === 0}
              loading={run.isPending}
              onClick={() => {
                setError(null)
                run.mutate()
              }}
            >
              Run it
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {isIncrease && operation.effective_date && (
          <Alert tone="warn" icon={<AlertTriangle className="h-4 w-4" />}>
            Every tenant below gets a written notice that their rent changes on{' '}
            {shortDate(operation.effective_date)}.
          </Alert>
        )}

        {!pending && (
          <div className="flex gap-3">
            <span className="inline-flex items-center gap-1.5 text-sm text-money-700">
              <Check className="h-4 w-4" />
              {operation.succeeded} succeeded
            </span>
            {operation.failed > 0 && (
              <span className="inline-flex items-center gap-1.5 text-sm text-danger-700">
                <X className="h-4 w-4" />
                {operation.failed} failed
              </span>
            )}
          </div>
        )}

        {operation.failures.length > 0 && (
          <div className="rounded-lg border border-danger-200 bg-danger-50 p-3">
            <p className="text-sm font-medium text-danger-800">What failed, and why</p>
            <ul className="mt-1 space-y-1 text-sm text-danger-700">
              {operation.failures.map((failure, index) => (
                <li key={index}>
                  {failure.tenant_name ?? 'Unknown'}
                  {failure.unit_number ? ` (unit ${failure.unit_number})` : ''}: {failure.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        {operation.targets.length ? (
          <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
            <Table>
              <thead>
                <tr>
                  <Th>Tenant</Th>
                  <Th>Unit</Th>
                  {isIncrease ? (
                    <>
                      <Th>Now</Th>
                      <Th>After</Th>
                    </>
                  ) : (
                    <Th>Phone</Th>
                  )}
                </tr>
              </thead>
              <tbody>
                {operation.targets.map((target) => (
                  <tr key={target.tenancy_id}>
                    <Td>{target.tenant_name}</Td>
                    <Td className="text-slate-500">
                      {target.property_name} {target.unit_number}
                    </Td>
                    {isIncrease ? (
                      <>
                        <Td>{kes(target.current_rent)}</Td>
                        <Td>
                          <span className="font-medium text-slate-900">
                            {kes(target.new_rent ?? 0)}
                          </span>
                          {target.increase_percent != null && (
                            <span className="ml-1 text-xs text-slate-500">
                              +{target.increase_percent.toFixed(1)}%
                            </span>
                          )}
                        </Td>
                      </>
                    ) : (
                      <Td className="text-slate-500">{target.phone_number}</Td>
                    )}
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        ) : (
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="Nobody matches"
            description="No tenant in this scope needs this action right now."
          />
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}
