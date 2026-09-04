import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  Check,
  ClipboardCheck,
  ClipboardList,
  Copy,
  Gauge,
  Pencil,
  UserPlus,
  Wrench,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { activityApi, applicationsApi, maintenanceApi, metersApi, unitsApi } from '@/api'
import type { WaitingListEntry } from '@/api/types'
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
  MAINTENANCE_STATUS_TONE,
  PageLoader,
  Select,
  Textarea,
  UNIT_STATUS_TONE,
  linkButtonClass,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const SELECTABLE_STATUSES = ['vacant', 'under_maintenance', 'reserved']

export function UnitDetailPage() {
  const { unitId } = useParams<{ unitId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [statusOpen, setStatusOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManage = permissions?.includes('unit:manage')
  const canSetStatus = permissions?.includes('unit:status_update')
  const canCreateTenancy = permissions?.includes('tenancy:manage')

  const unit = useQuery({
    queryKey: queryKeys.unit(unitId!),
    queryFn: () => unitsApi.get(unitId!),
    enabled: Boolean(unitId),
  })

  const readings = useQuery({
    queryKey: queryKeys.meterReadings({ unit_id: unitId }),
    queryFn: () => metersApi.list({ unit_id: unitId, limit: 6 }),
    enabled: Boolean(unitId),
  })

  const maintenance = useQuery({
    queryKey: queryKeys.maintenance({ unit_id: unitId }),
    queryFn: () => maintenanceApi.list({ unit_id: unitId, limit: 5 }),
    enabled: Boolean(unitId),
  })

  // Applicants only exist while the unit is lettable, so the query follows the
  // unit's own state rather than running on every visit.
  const waitingList = useQuery({
    queryKey: queryKeys.waitingList(unitId!),
    queryFn: () => applicationsApi.waitingList(unitId!),
    enabled: Boolean(unitId) && unit.data?.status !== 'occupied',
  })

  const history = useQuery({
    queryKey: queryKeys.activity({ entity_type: 'unit', entity_id: unitId }),
    queryFn: () => activityApi.list({ entity_type: 'unit', entity_id: unitId, limit: 10 }),
    enabled: Boolean(unitId),
  })

  const archive = useMutation({
    mutationFn: () => unitsApi.archive(unitId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      navigate('/units')
    },
    onError: (error) => setActionError(errorMessage(error)),
  })

  if (unit.isPending) return <PageLoader />
  if (unit.isError) {
    return (
      <Alert tone="danger" title="Could not load this unit">
        {errorMessage(unit.error)}
      </Alert>
    )
  }

  const record = unit.data

  return (
    <div>
      <PageHeader
        title={`Unit ${record.unit_number}`}
        description={record.property_name ?? undefined}
        backTo={record.property_id ? `/properties/${record.property_id}` : '/units'}
        backLabel="Back to property"
        actions={
          <>
            {canSetStatus && (
              <Button variant="outline" onClick={() => setStatusOpen(true)}>
                Change status
              </Button>
            )}
            {canManage && (
              <Link to={`/units/${unitId}/edit`} className={linkButtonClass('outline')}>
                <Pencil className="h-4 w-4" />
                Edit
              </Link>
            )}
            <Link
              to={`/inspections/new?unit_id=${unitId}&type=${
                record.current_tenancy_id ? 'routine' : 'move_in'
              }${record.current_tenancy_id ? `&tenancy_id=${record.current_tenancy_id}` : ''}`}
              className={linkButtonClass('outline')}
            >
              <ClipboardCheck className="h-4 w-4" />
              Inspect
            </Link>
            {record.status === 'vacant' && canCreateTenancy && (
              <Link to={`/tenancies/new?unit_id=${unitId}`} className={linkButtonClass()}>
                <UserPlus className="h-4 w-4" />
                Add tenant
              </Link>
            )}
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
              <Badge tone={UNIT_STATUS_TONE[record.status] ?? 'neutral'}>
                {humanize(record.status)}
              </Badge>
            </CardHeader>
            <CardBody>
              {record.current_tenant_name ? (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-slate-500">Current tenant</p>
                    <p className="font-medium text-slate-900">{record.current_tenant_name}</p>
                  </div>
                  {record.current_tenancy_id && (
                    <Link
                      to={`/tenancies/${record.current_tenancy_id}`}
                      className={linkButtonClass('outline', 'sm')}
                    >
                      View tenancy
                    </Link>
                  )}
                </div>
              ) : record.status === 'vacant' ? (
                <p className="text-sm text-slate-500">
                  Vacant{record.vacancy_date ? ` since ${shortDate(record.vacancy_date)}` : ''}.
                </p>
              ) : record.status === 'vacating' ? (
                <p className="text-sm text-slate-500">
                  The tenant has given notice. Expected free on{' '}
                  <strong>{shortDate(record.expected_vacancy_date)}</strong>.
                </p>
              ) : (
                <p className="text-sm text-slate-500">No active tenancy.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Meter readings</CardTitle>
              <Link
                to={`/meter-readings/new?unit_id=${unitId}`}
                className={linkButtonClass('outline', 'sm')}
              >
                <Gauge className="h-3.5 w-3.5" />
                Record reading
              </Link>
            </CardHeader>
            {readings.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {readings.data.map((reading) => (
                  <li key={reading.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        {humanize(reading.meter_type)} · {reading.consumption} units
                      </p>
                      <p className="text-xs text-slate-500">
                        {reading.previous_reading} → {reading.current_reading} on{' '}
                        {shortDate(reading.reading_date)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium">{kes(reading.amount)}</p>
                      <p className="text-xs text-slate-400">
                        {reading.billed_invoice_id ? 'Billed' : 'On next invoice'}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Gauge className="h-6 w-6" />}
                title="No readings yet"
                description="Record a water or electricity reading to bill utilities automatically."
              />
            )}
          </Card>

          {unit.data.status !== 'occupied' && <ApplicationsCard unitId={unitId!} waitingList={waitingList.data ?? []} />}

          <Card>
            <CardHeader>
              <CardTitle>Maintenance</CardTitle>
              <Link
                to={`/maintenance/new?unit_id=${unitId}`}
                className={linkButtonClass('outline', 'sm')}
              >
                <Wrench className="h-3.5 w-3.5" />
                Report issue
              </Link>
            </CardHeader>
            {maintenance.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {maintenance.data.map((request) => (
                  <li key={request.id} className="px-5 py-3">
                    <Link
                      to={`/maintenance/${request.id}`}
                      className="flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">{request.title}</p>
                        <p className="text-xs text-slate-500">
                          {request.reference_code} · {shortDate(request.created_at)}
                        </p>
                      </div>
                      <Badge tone={MAINTENANCE_STATUS_TONE[request.status] ?? 'neutral'}>
                        {humanize(request.status)}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Wrench className="h-6 w-6" />}
                title="No maintenance requests"
                description="Nothing has been reported for this unit."
              />
            )}
            {maintenance.data && maintenance.data.length >= 5 && (
              <div className="border-t border-slate-100 px-5 py-3">
                <Link
                  to={`/maintenance?unit_id=${unitId}`}
                  className="text-sm text-brand-600 hover:text-brand-700"
                >
                  See this unit&apos;s full history
                </Link>
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3 text-sm">
              <Detail label="Reference" value={record.reference_code} />
              <Detail label="Type" value={record.unit_type ?? 'Not specified'} />
              <Detail
                label="Layout"
                value={
                  record.bedrooms != null
                    ? `${record.bedrooms} bed · ${record.bathrooms ?? 0} bath`
                    : 'Not specified'
                }
              />
              <Detail label="Floor" value={record.floor ?? '—'} />
              <Detail label="Size" value={record.size_sqm ? `${record.size_sqm} sqm` : '—'} />
              <Detail label="Monthly rent" value={kes(record.monthly_rent)} />
              <Detail label="Deposit" value={kes(record.deposit_amount)} />
            </CardBody>
          </Card>

          {record.photos.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Photos</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="grid grid-cols-3 gap-2">
                  {record.photos.map((photo) => (
                    <a
                      key={photo.id}
                      href={photo.url}
                      target="_blank"
                      rel="noreferrer"
                      className="aspect-square overflow-hidden rounded-lg border border-slate-200"
                    >
                      <img src={photo.url} alt="" className="h-full w-full object-cover" />
                    </a>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>History</CardTitle>
            </CardHeader>
            {history.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {history.data.map((entry) => (
                  <li key={entry.id} className="px-5 py-2.5">
                    <p className="text-sm text-slate-700">{entry.summary ?? entry.action}</p>
                    <p className="text-xs text-slate-400">
                      {entry.actor_name ?? 'System'} · {dateTime(entry.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <CardBody>
                <p className="text-sm text-slate-500">No changes recorded yet.</p>
              </CardBody>
            )}
          </Card>

          {canManage && !record.is_archived && (
            <Button
              variant="ghost"
              className="w-full justify-center text-danger-600"
              icon={<Archive className="h-4 w-4" />}
              onClick={() => setArchiveOpen(true)}
            >
              Archive unit
            </Button>
          )}
        </div>
      </div>

      <StatusDialog
        open={statusOpen}
        onClose={() => setStatusOpen(false)}
        unitId={unitId!}
        currentStatus={record.status}
      />

      <Dialog
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        title={`Archive unit ${record.unit_number}?`}
        description="It disappears from active views but keeps its history."
        footer={
          <>
            <Button variant="ghost" onClick={() => setArchiveOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={archive.isPending} onClick={() => archive.mutate()}>
              Archive unit
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          A unit with a live tenancy cannot be archived — end the tenancy first.
        </p>
        {actionError && (
          <Alert tone="danger" className="mt-3">
            {actionError}
          </Alert>
        )}
      </Dialog>
    </div>
  )
}

function StatusDialog({
  open,
  onClose,
  unitId,
  currentStatus,
}: {
  open: boolean
  onClose: () => void
  unitId: string
  currentStatus: string
}) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState(currentStatus)
  const [expectedDate, setExpectedDate] = useState(today())
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      unitsApi.setStatus(unitId, {
        status,
        expected_vacancy_date: status === 'vacating' ? expectedDate : null,
        note: note || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['unit'] })
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['activity'] })
      onClose()
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Change unit status"
      description="The change is logged, and the owner is notified when a caretaker makes it."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={mutation.isPending}
            disabled={status === currentStatus}
            onClick={() => {
              setError(null)
              mutation.mutate()
            }}
          >
            Update status
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="New status">
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            {SELECTABLE_STATUSES.map((value) => (
              <option key={value} value={value}>
                {humanize(value)}
              </option>
            ))}
          </Select>
        </Field>

        {status === 'vacating' && (
          <Field label="Expected vacancy date" required>
            <Input
              type="date"
              value={expectedDate}
              onChange={(event) => setExpectedDate(event.target.value)}
            />
          </Field>
        )}

        <Field label="Note" hint="Saved with the change in the audit log.">
          <Textarea
            placeholder="Repainting after the last tenant moved out."
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>

        <Alert tone="info">
          Occupancy follows the tenancy — create or end a tenancy to move a unit in or out of{' '}
          <strong>occupied</strong>.
        </Alert>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{value}</dd>
    </div>
  )
}

/** While a unit is lettable, its detail page doubles as the vacancy desk: the
 *  link to share, and the queue of people who have answered it (US-064/US-067). */
function ApplicationsCard({
  unitId,
  waitingList,
}: {
  unitId: string
  waitingList: WaitingListEntry[]
}) {
  const [copied, setCopied] = useState(false)
  const applyUrl = `${window.location.origin}/apply/${unitId}`

  return (
    <Card>
      <CardHeader>
        <CardTitle>Applications</CardTitle>
        <Link to={`/applications?unit_id=${unitId}`} className="text-sm text-brand-600 hover:text-brand-700">
          See all
        </Link>
      </CardHeader>
      <CardBody className="space-y-4">
        <div>
          <p className="text-sm text-slate-600">
            Share this link on WhatsApp — anyone can apply without an account.
          </p>
          <div className="mt-2 flex gap-2">
            <Input readOnly value={applyUrl} className="font-mono text-xs" />
            <Button
              variant="outline"
              icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              onClick={async () => {
                await navigator.clipboard.writeText(applyUrl)
                setCopied(true)
                window.setTimeout(() => setCopied(false), 2000)
              }}
            >
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
        </div>

        {waitingList.length ? (
          <ul className="divide-y divide-slate-100">
            {waitingList.map((entry) => (
              <li key={entry.application_id} className="flex items-center justify-between gap-3 py-2">
                <Link to={`/applications/${entry.application_id}`} className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">
                    {entry.rank}. {entry.full_name}
                  </p>
                  <p className="text-xs text-slate-500">
                    {entry.phone_number} · {humanize(entry.status)}
                  </p>
                </Link>
                <Badge
                  tone={
                    entry.band === 'green' ? 'success' : entry.band === 'amber' ? 'warn' : 'danger'
                  }
                >
                  {entry.score}/100
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<ClipboardList className="h-6 w-6" />}
            title="Nobody has applied yet"
            description="Applications appear here already scored and ranked."
          />
        )}
      </CardBody>
    </Card>
  )
}
