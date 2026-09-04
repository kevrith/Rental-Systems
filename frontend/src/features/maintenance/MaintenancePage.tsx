import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, AlertTriangle, BarChart3, Check, Plus, Wrench } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { maintenanceApi, unitsApi } from '@/api'
import { FileUpload, type UploadedFile } from '@/components/FileUpload'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Field,
  Input,
  MAINTENANCE_STATUS_TONE,
  PRIORITY_TONE,
  Select,
  Skeleton,
  Tab,
  Tabs,
  Textarea,
  linkButtonClass,
} from '@/components/ui'
import { submitOrQueue } from '@/hooks/use-offline-queue'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const CATEGORIES = ['plumbing', 'electrical', 'structural', 'appliance', 'security', 'other']
const STATUS_TABS = [
  { key: '', label: 'All' },
  { key: 'submitted', label: 'New' },
  { key: 'under_review', label: 'In review' },
  { key: 'approved', label: 'Approved' },
  { key: 'assigned', label: 'Assigned' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'completed', label: 'Completed' },
  { key: 'closed', label: 'Closed' },
]

export function MaintenancePage() {
  const [params] = useSearchParams()
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const canCreate = useAuthStore((state) =>
    state.user?.permissions?.includes('maintenance:create'),
  )

  // Scoping to one unit or property turns this page into that thing's complete
  // maintenance history (US-061), filters and all.
  const unitId = params.get('unit_id') ?? undefined
  const propertyId = params.get('property_id') ?? undefined

  const requests = useQuery({
    queryKey: queryKeys.maintenance({ status, priority, unitId, propertyId }),
    queryFn: () =>
      maintenanceApi.list({
        request_status: status || undefined,
        priority: priority || undefined,
        unit_id: unitId,
        property_id: propertyId,
        limit: 200,
      }),
  })

  const scopeLabel = requests.data?.[0]
    ? unitId
      ? `${requests.data[0].property_name} unit ${requests.data[0].unit_number}`
      : propertyId
        ? requests.data[0].property_name
        : null
    : null

  return (
    <div>
      <PageHeader
        title="Maintenance"
        description={
          scopeLabel
            ? `Every issue ever reported for ${scopeLabel}.`
            : 'Every reported issue, from first report to sign-off.'
        }
        backTo={unitId ? `/units/${unitId}` : propertyId ? `/properties/${propertyId}` : undefined}
        backLabel={unitId ? 'Back to the unit' : 'Back to the property'}
        actions={
          <>
            <Link to="/maintenance/analytics" className={linkButtonClass('outline')}>
              <BarChart3 className="h-4 w-4" />
              Costs
            </Link>
            {canCreate && (
              <Link to="/maintenance/new" className={linkButtonClass()}>
                <Plus className="h-4 w-4" />
                Report an issue
              </Link>
            )}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={status} onChange={setStatus}>
          {STATUS_TABS.map((tab) => (
            <Tab key={tab.key} value={tab.key}>
              {tab.label}
            </Tab>
          ))}
        </Tabs>
        <Select
          className="w-auto min-w-36"
          value={priority}
          onChange={(event) => setPriority(event.target.value)}
        >
          <option value="">Any priority</option>
          <option value="emergency">Emergency</option>
          <option value="urgent">Urgent</option>
          <option value="routine">Routine</option>
        </Select>
      </div>

      {requests.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-20" />
          ))}
        </div>
      ) : requests.data?.length ? (
        <div className="space-y-3">
          {requests.data.map((request) => (
            <Link
              key={request.id}
              to={`/maintenance/${request.id}`}
              className="block rounded-card border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-slate-900">{request.title}</p>
                    <Badge tone={PRIORITY_TONE[request.priority] ?? 'neutral'}>
                      {humanize(request.priority)}
                    </Badge>
                    <Badge tone={MAINTENANCE_STATUS_TONE[request.status] ?? 'neutral'}>
                      {humanize(request.status)}
                    </Badge>
                    {request.is_overdue && (
                      <Badge tone="danger">
                        <AlertTriangle className="h-3 w-3" />
                        Overdue
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-600">{request.description}</p>
                  <p className="mt-1.5 text-xs text-slate-400">
                    {request.reference_code} · {request.property_name} unit {request.unit_number} ·
                    reported by {request.reported_by_name ?? 'unknown'} on{' '}
                    {shortDate(request.created_at)}
                  </p>
                  {(request.vendor || request.expected_completion_date) && (
                    <p className="mt-1 text-xs text-slate-500">
                      {request.vendor ? `Assigned to ${request.vendor.name}` : 'No vendor yet'}
                      {request.expected_completion_date
                        ? ` · due ${shortDate(request.expected_completion_date)}`
                        : ''}
                      {request.cost ? ` · ${kes(request.cost)}` : ''}
                    </p>
                  )}
                </div>
                {request.photo_urls && request.photo_urls.length > 0 && (
                  <img
                    src={request.photo_urls[0]}
                    alt=""
                    className="h-16 w-16 shrink-0 rounded-lg object-cover"
                  />
                )}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Wrench className="h-6 w-6" />}
            title="Nothing to fix"
            description="No maintenance requests match these filters."
          />
        </Card>
      )}
    </div>
  )
}

export function MaintenanceFormPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [unitId, setUnitId] = useState(params.get('unit_id') ?? '')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('other')
  const [priority, setPriority] = useState('routine')
  const [photos, setPhotos] = useState<UploadedFile[]>([])
  const [error, setError] = useState<string | null>(null)
  const [queued, setQueued] = useState(false)

  const units = useQuery({
    queryKey: queryKeys.units({ forMaintenance: true }),
    queryFn: () => unitsApi.list(),
  })

  const photoRequired = priority !== 'routine'

  const create = useMutation({
    mutationFn: async () => {
      const body = {
        unit_id: unitId,
        title,
        description,
        category,
        priority,
        photo_file_ids: photos.map((photo) => photo.id),
      }
      return submitOrQueue({
        run: () => maintenanceApi.create(body),
        method: 'POST',
        url: '/maintenance',
        body,
        label: `Maintenance: ${title}`,
      })
    },
    onSuccess: async (result) => {
      if (result.queued) {
        setQueued(true)
        return
      }
      await queryClient.invalidateQueries({ queryKey: ['maintenance'] })
      await queryClient.invalidateQueries({ queryKey: ['caretaker'] })
      navigate(`/maintenance/${result.data!.id}`)
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  if (queued) {
    return (
      <div className="mx-auto max-w-lg">
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
            <Check className="h-10 w-10 text-money-600" />
            <p className="font-medium text-slate-900">Saved on this device</p>
            <p className="max-w-sm text-sm text-slate-500">
              You are offline. This request will be sent — and the owner alerted — as soon as you
              reconnect.
            </p>
            <Link to="/maintenance" className={linkButtonClass('outline')}>
              Back to maintenance
            </Link>
          </CardBody>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg">
      <PageHeader title="Report a maintenance issue" backTo="/maintenance" />

      <Card>
        <CardBody className="space-y-4">
          <Field label="Unit" required>
            <Select value={unitId} onChange={(event) => setUnitId(event.target.value)}>
              <option value="">Choose a unit</option>
              {units.data?.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  Unit {unit.unit_number}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="What's wrong?" required>
            <Input
              placeholder="Kitchen tap leaking"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>

          <Field label="Describe the issue" required>
            <Textarea
              placeholder="Constant drip under the sink since Tuesday. The cabinet floor is getting wet."
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Category">
              <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                {CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {humanize(value)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Priority">
              <Select value={priority} onChange={(event) => setPriority(event.target.value)}>
                <option value="routine">Routine</option>
                <option value="urgent">Urgent</option>
                <option value="emergency">Emergency</option>
              </Select>
            </Field>
          </div>

          {priority === 'emergency' && (
            <Alert tone="danger" icon={<AlertTriangle className="h-4 w-4" />}>
              The owner gets an immediate WhatsApp alert marked URGENT.
            </Alert>
          )}

          <FileUpload
            value={photos}
            onChange={setPhotos}
            category="maintenance"
            max={5}
            label={`Photos${photoRequired ? ' (required)' : ''}`}
            hint={
              photoRequired
                ? 'At least one photo is required for urgent and emergency requests.'
                : 'Optional, but a photo saves a site visit.'
            }
          />

          {error && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              {error}
            </Alert>
          )}

          <Button
            className="w-full justify-center"
            size="lg"
            disabled={
              !unitId || !title || !description || (photoRequired && photos.length === 0)
            }
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Submit request
          </Button>
        </CardBody>
      </Card>
    </div>
  )
}
