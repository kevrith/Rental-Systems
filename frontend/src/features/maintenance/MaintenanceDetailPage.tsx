import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  HelpCircle,
  MessageSquareWarning,
  Play,
  Star,
  ThumbsDown,
  ThumbsUp,
  UserPlus,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'

import { maintenanceApi, vendorsApi } from '@/api'
import type { MaintenanceRequest } from '@/api/types'
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
  Field,
  Input,
  MAINTENANCE_STATUS_TONE,
  PRIORITY_TONE,
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const REJECTION_REASONS = [
  { value: 'not_landlord_responsibility', label: 'Not the landlord’s responsibility' },
  { value: 'tenant_caused_damage', label: 'Damage caused by the tenant' },
  { value: 'duplicate_request', label: 'Duplicate of another request' },
  { value: 'cost_not_justified', label: 'Cost not justified' },
  { value: 'scheduled_for_later', label: 'Scheduled for a later date' },
  { value: 'other', label: 'Other (explain below)' },
]

type ActionKind = 'approve' | 'reject' | 'assign' | 'complete' | 'info' | null

export function MaintenanceDetailPage() {
  const { requestId } = useParams<{ requestId: string }>()
  const queryClient = useQueryClient()
  const [action, setAction] = useState<ActionKind>(null)
  const [error, setError] = useState<string | null>(null)

  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManage = permissions?.includes('maintenance:manage')
  const canApprove = permissions?.includes('maintenance:approve')

  const request = useQuery({
    queryKey: queryKeys.maintenanceRequest(requestId!),
    queryFn: () => maintenanceApi.get(requestId!),
    enabled: Boolean(requestId),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['maintenance'] })
    await queryClient.invalidateQueries({ queryKey: ['vendors'] })
    await queryClient.invalidateQueries({ queryKey: ['caretaker'] })
  }

  const simpleAction = useMutation({
    mutationFn: (kind: 'review' | 'start' | 'close') => {
      if (kind === 'review') return maintenanceApi.review(requestId!)
      if (kind === 'start') return maintenanceApi.start(requestId!)
      return maintenanceApi.close(requestId!)
    },
    onSuccess: refresh,
    onError: (actionError) => setError(errorMessage(actionError)),
  })

  if (request.isPending) return <PageLoader />
  if (request.isError) {
    return (
      <Alert tone="danger" title="Could not load this request">
        {errorMessage(request.error)}
      </Alert>
    )
  }

  const record = request.data
  const status = record.status

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={record.title}
        description={`${record.reference_code} · ${record.property_name} unit ${record.unit_number}`}
        backTo="/maintenance"
        backLabel="All maintenance"
      />

      {record.is_overdue && (
        <Alert
          tone="danger"
          className="mb-4"
          icon={<AlertTriangle className="h-4 w-4" />}
          title="This job is overdue"
        >
          It was expected by {shortDate(record.expected_completion_date)} and is still open.
          {record.vendor ? ` Chase ${record.vendor.name} on ${record.vendor.phone_number}.` : ''}
        </Alert>
      )}

      {record.info_requested && (
        <Alert
          tone="warn"
          className="mb-4"
          icon={<HelpCircle className="h-4 w-4" />}
          title="Waiting on more detail"
        >
          {record.info_requested}
        </Alert>
      )}

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
            <div className="flex flex-wrap gap-2">
              <Badge tone={PRIORITY_TONE[record.priority] ?? 'neutral'}>
                {humanize(record.priority)}
              </Badge>
              <Badge tone={MAINTENANCE_STATUS_TONE[status] ?? 'neutral'}>{humanize(status)}</Badge>
            </div>
          </CardHeader>
          <CardBody className="space-y-4">
            <p className="whitespace-pre-wrap text-sm text-slate-700">{record.description}</p>

            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <Detail label="Category" value={humanize(record.category)} />
              <Detail label="Reported by" value={record.reported_by_name ?? '—'} />
              <Detail label="Reported" value={dateTime(record.created_at)} />
              <Detail
                label="Open for"
                value={record.days_open === null ? '—' : `${record.days_open} day(s)`}
              />
              {record.expected_completion_date && (
                <Detail
                  label="Expected by"
                  value={shortDate(record.expected_completion_date)}
                />
              )}
              {record.approved_by_name && (
                <Detail label="Approved by" value={record.approved_by_name} />
              )}
              {record.completed_at && (
                <Detail label="Completed" value={dateTime(record.completed_at)} />
              )}
            </dl>

            {(record.estimated_cost || record.cost) && (
              <div className="grid gap-3 rounded-lg bg-slate-50 p-3 text-sm sm:grid-cols-3">
                <Detail
                  label="Estimate"
                  value={record.estimated_cost ? kes(record.estimated_cost) : '—'}
                />
                <Detail label="Actual" value={record.cost ? kes(record.cost) : 'Not yet recorded'} />
                {record.cost_variance && Number(record.cost_variance) !== 0 && (
                  <Detail
                    label="Variance"
                    value={
                      <span
                        className={
                          Number(record.cost_variance) > 0
                            ? 'font-medium text-danger-700'
                            : 'font-medium text-money-700'
                        }
                      >
                        {Number(record.cost_variance) > 0 ? '+' : ''}
                        {kes(record.cost_variance)}
                      </span>
                    }
                  />
                )}
              </div>
            )}

            {record.rejection_reason && (
              <Alert tone="danger" title="Not approved">
                {humanize(record.rejection_reason)}
                {record.rejection_note ? ` — ${record.rejection_note}` : ''}
              </Alert>
            )}

            {record.photo_urls && record.photo_urls.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {record.photo_urls.map((url) => (
                  <a
                    key={url}
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="aspect-square overflow-hidden rounded-lg border border-slate-200"
                  >
                    <img src={url} alt="" className="h-full w-full object-cover" />
                  </a>
                ))}
              </div>
            )}

            {record.resolution_notes && (
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Resolution</p>
                <p className="mt-0.5 whitespace-pre-wrap text-sm text-slate-700">
                  {record.resolution_notes}
                </p>
              </div>
            )}
          </CardBody>
        </Card>

        {record.vendor && (
          <Card>
            <CardHeader>
              <CardTitle>Assigned contractor</CardTitle>
              {record.vendor_rating && (
                <span className="inline-flex items-center gap-1 text-sm font-medium text-slate-700">
                  <Star className="h-4 w-4 fill-warn-400 text-warn-400" />
                  {record.vendor_rating} / 5
                </span>
              )}
            </CardHeader>
            <CardBody className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link
                  to={`/vendors/${record.vendor.id}`}
                  className="font-medium text-slate-900 hover:text-brand-700"
                >
                  {record.vendor.name}
                </Link>
                <a
                  href={`tel:${record.vendor.phone_number}`}
                  className="text-sm text-brand-600 hover:text-brand-700"
                >
                  {record.vendor.phone_number}
                </a>
              </div>
              <p className="text-xs text-slate-400">
                {record.vendor.jobs_completed} completed job(s)
                {record.assigned_at ? ` · assigned ${shortDate(record.assigned_at)}` : ''}
              </p>
              {record.vendor_review && (
                <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                  {record.vendor_review}
                </p>
              )}
            </CardBody>
          </Card>
        )}

        {record.tenant_rating && (
          <Card>
            <CardHeader>
              <CardTitle>Tenant feedback</CardTitle>
              <span className="inline-flex items-center gap-1 text-sm font-medium text-slate-700">
                <Star className="h-4 w-4 fill-warn-400 text-warn-400" />
                {record.tenant_rating} / 5
              </span>
            </CardHeader>
            {record.tenant_feedback && (
              <CardBody>
                <p className="text-sm text-slate-700">{record.tenant_feedback}</p>
              </CardBody>
            )}
          </Card>
        )}

        {(canManage || canApprove) && (
          <Card>
            <CardHeader>
              <CardTitle>What happens next</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {status === 'submitted' && canManage && (
                  <Button
                    variant="outline"
                    icon={<MessageSquareWarning className="h-4 w-4" />}
                    loading={simpleAction.isPending}
                    onClick={() => {
                      setError(null)
                      simpleAction.mutate('review')
                    }}
                  >
                    Start review
                  </Button>
                )}

                {(status === 'submitted' || status === 'under_review') && (
                  <>
                    {canApprove && (
                      <Button
                        icon={<ThumbsUp className="h-4 w-4" />}
                        onClick={() => setAction('approve')}
                      >
                        Approve
                      </Button>
                    )}
                    {canManage && (
                      <Button
                        variant="outline"
                        icon={<HelpCircle className="h-4 w-4" />}
                        onClick={() => setAction('info')}
                      >
                        Ask for more detail
                      </Button>
                    )}
                    {canApprove && (
                      <Button
                        variant="danger"
                        icon={<ThumbsDown className="h-4 w-4" />}
                        onClick={() => setAction('reject')}
                      >
                        Reject
                      </Button>
                    )}
                  </>
                )}

                {(status === 'approved' || status === 'assigned') && canManage && (
                  <Button
                    variant={status === 'approved' ? 'primary' : 'outline'}
                    icon={<UserPlus className="h-4 w-4" />}
                    onClick={() => setAction('assign')}
                  >
                    {status === 'approved' ? 'Assign a vendor' : 'Reassign'}
                  </Button>
                )}

                {(status === 'approved' || status === 'assigned') && canManage && (
                  <Button
                    variant="outline"
                    icon={<Play className="h-4 w-4" />}
                    loading={simpleAction.isPending}
                    onClick={() => {
                      setError(null)
                      simpleAction.mutate('start')
                    }}
                  >
                    Mark work started
                  </Button>
                )}

                {(status === 'assigned' || status === 'in_progress') && canManage && (
                  <Button
                    variant="success"
                    icon={<CheckCircle2 className="h-4 w-4" />}
                    onClick={() => setAction('complete')}
                  >
                    Mark complete
                  </Button>
                )}

                {status === 'completed' && canApprove && (
                  <Button
                    icon={<CircleDollarSign className="h-4 w-4" />}
                    loading={simpleAction.isPending}
                    onClick={() => {
                      setError(null)
                      simpleAction.mutate('close')
                    }}
                  >
                    Close and allocate cost
                  </Button>
                )}
              </div>

              {status === 'completed' && (
                <p className="text-xs text-slate-500">
                  Closing signs the job off. In agency mode the cost is deducted on the owner&apos;s
                  next statement.
                </p>
              )}

              {(status === 'rejected' || status === 'closed' || status === 'cancelled') && (
                <p className="text-sm text-slate-500">
                  This job is {humanize(status).toLowerCase()} — nothing further to do.
                </p>
              )}

              {error && <Alert tone="danger">{error}</Alert>}
            </CardBody>
          </Card>
        )}

        {record.timeline && record.timeline.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>History</CardTitle>
            </CardHeader>
            <CardBody>
              <ol className="space-y-3">
                {record.timeline.map((entry, index) => (
                  <li key={`${entry.action}-${index}`} className="flex gap-3">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-400" />
                    <div className="min-w-0">
                      <p className="text-sm text-slate-700">{entry.summary}</p>
                      <p className="text-xs text-slate-400">
                        {dateTime(entry.occurred_at)}
                        {entry.actor_name ? ` · ${entry.actor_name}` : ''}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </CardBody>
          </Card>
        )}
      </div>

      <ApproveDialog
        open={action === 'approve'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
      <RejectDialog
        open={action === 'reject'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
      <AssignDialog
        open={action === 'assign'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
      <CompleteDialog
        open={action === 'complete'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
      <InfoDialog
        open={action === 'info'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
    </div>
  )
}

type DialogProps = {
  open: boolean
  record: MaintenanceRequest
  onClose: () => void
  onDone: () => Promise<void>
}

/** The vendor picker, pre-filtered to whoever can actually do this category of job. */
function VendorSelect({
  category,
  value,
  onChange,
  allowEmpty,
}: {
  category: string
  value: string
  onChange: (value: string) => void
  allowEmpty?: boolean
}) {
  const [showAll, setShowAll] = useState(false)

  const vendors = useQuery({
    queryKey: queryKeys.vendors({ category: showAll ? undefined : category }),
    queryFn: () => vendorsApi.list(showAll ? {} : { category }),
  })

  return (
    <div className="space-y-1.5">
      <Select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{allowEmpty ? 'Assign later' : 'Choose a vendor'}</option>
        {vendors.data?.map((vendor) => (
          <option key={vendor.id} value={vendor.id}>
            {vendor.name}
            {vendor.average_rating ? ` — ${vendor.average_rating.toFixed(1)}/5` : ''}
            {vendor.jobs_completed ? ` (${vendor.jobs_completed} jobs)` : ''}
          </option>
        ))}
      </Select>
      <button
        type="button"
        className="text-xs text-brand-600 hover:text-brand-700"
        onClick={() => setShowAll((state) => !state)}
      >
        {showAll ? `Show only ${humanize(category).toLowerCase()} specialists` : 'Show every vendor'}
      </button>
    </div>
  )
}

function ApproveDialog({ open, record, onClose, onDone }: DialogProps) {
  const [estimate, setEstimate] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [vendorId, setVendorId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const approve = useMutation({
    mutationFn: () =>
      maintenanceApi.approve(record.id, {
        estimated_cost: estimate || null,
        expected_completion_date: dueDate || null,
        vendor_id: vendorId || null,
      }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (approveError) => setError(errorMessage(approveError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Approve this job"
      description="Approving commits the spend. Pick a vendor now to send the job straight out."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={approve.isPending}
            onClick={() => {
              setError(null)
              approve.mutate()
            }}
          >
            Approve
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Cost estimate (KES)" hint="What you expect this to cost">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={estimate}
              onChange={(event) => setEstimate(event.target.value)}
            />
          </Field>
          <Field label="Expected completion" hint="Left blank, we set it from the priority">
            <Input
              type="date"
              min={today()}
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
            />
          </Field>
        </div>

        <Field label="Send to vendor" hint="Optional — they get the job details on WhatsApp">
          <VendorSelect category={record.category} value={vendorId} onChange={setVendorId} allowEmpty />
        </Field>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function RejectDialog({ open, record, onClose, onDone }: DialogProps) {
  const [reason, setReason] = useState(REJECTION_REASONS[0].value)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reject = useMutation({
    mutationFn: () => maintenanceApi.reject(record.id, { reason, note: note || undefined }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (rejectError) => setError(errorMessage(rejectError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Reject this request"
      description="The reporter is told the reason, so make it one they can act on."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={reason === 'other' && !note.trim()}
            loading={reject.isPending}
            onClick={() => {
              setError(null)
              reject.mutate()
            }}
          >
            Reject
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Reason" required>
          <Select value={reason} onChange={(event) => setReason(event.target.value)}>
            {REJECTION_REASONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Note"
          required={reason === 'other'}
          hint="Included in the message sent to the reporter"
        >
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function AssignDialog({ open, record, onClose, onDone }: DialogProps) {
  const [vendorId, setVendorId] = useState(record.vendor_id ?? '')
  const [estimate, setEstimate] = useState(record.estimated_cost ?? '')
  const [dueDate, setDueDate] = useState(record.expected_completion_date ?? '')
  const [error, setError] = useState<string | null>(null)

  const assign = useMutation({
    mutationFn: () =>
      maintenanceApi.assign(record.id, {
        vendor_id: vendorId,
        estimated_cost: estimate || null,
        expected_completion_date: dueDate || null,
      }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (assignError) => setError(errorMessage(assignError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Assign a vendor"
      description="They get the job details, address and deadline on WhatsApp straight away."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!vendorId}
            loading={assign.isPending}
            onClick={() => {
              setError(null)
              assign.mutate()
            }}
          >
            Assign and notify
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Vendor" required>
          <VendorSelect category={record.category} value={vendorId} onChange={setVendorId} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Cost estimate (KES)">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={estimate}
              onChange={(event) => setEstimate(event.target.value)}
            />
          </Field>
          <Field label="Complete by">
            <Input
              type="date"
              min={today()}
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
            />
          </Field>
        </div>

        <Alert tone="info" icon={<CalendarClock className="h-4 w-4" />}>
          If the job is still open the day after this date, it is flagged overdue and the manager is
          alerted.
        </Alert>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function CompleteDialog({ open, record, onClose, onDone }: DialogProps) {
  const [cost, setCost] = useState(record.estimated_cost ?? '')
  const [notes, setNotes] = useState('')
  const [rating, setRating] = useState<number | null>(null)
  const [review, setReview] = useState('')
  const [error, setError] = useState<string | null>(null)

  const complete = useMutation({
    mutationFn: () =>
      maintenanceApi.complete(record.id, {
        actual_cost: cost,
        resolution_notes: notes || undefined,
        vendor_rating: rating,
        vendor_review: review || null,
      }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (completeError) => setError(errorMessage(completeError)),
  })

  const overrun =
    record.estimated_cost && cost && Number(cost) > Number(record.estimated_cost)
      ? Number(cost) - Number(record.estimated_cost)
      : 0

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Mark this job complete"
      description="Record what it actually cost, and score the contractor while it is fresh."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="success"
            disabled={cost === ''}
            loading={complete.isPending}
            onClick={() => {
              setError(null)
              complete.mutate()
            }}
          >
            Complete
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Actual cost (KES)" required>
          <Input
            type="number"
            min="0"
            step="0.01"
            value={cost}
            onChange={(event) => setCost(event.target.value)}
          />
        </Field>

        {overrun > 0 && (
          <Alert tone="warn" icon={<AlertTriangle className="h-4 w-4" />}>
            That is {kes(overrun)} over the approved estimate of {kes(record.estimated_cost)}. The
            overrun is recorded on the audit trail.
          </Alert>
        )}

        <Field label="What was done">
          <Textarea
            placeholder="Replaced the tap washer and the shut-off valve; tested and dry."
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>

        {record.vendor && (
          <>
            <Field label={`Rate ${record.vendor.name}`} hint="Feeds their score in the vendor list">
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-label={`${value} star${value === 1 ? '' : 's'}`}
                    onClick={() => setRating(value === rating ? null : value)}
                    className="rounded-lg p-1 hover:bg-slate-100"
                  >
                    <Star
                      className={
                        rating !== null && value <= rating
                          ? 'h-6 w-6 fill-warn-400 text-warn-400'
                          : 'h-6 w-6 text-slate-300'
                      }
                    />
                  </button>
                ))}
              </div>
            </Field>

            {rating !== null && (
              <Field label="Review">
                <Textarea
                  placeholder="Arrived same day, tidy work."
                  value={review}
                  onChange={(event) => setReview(event.target.value)}
                />
              </Field>
            )}
          </>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function InfoDialog({ open, record, onClose, onDone }: DialogProps) {
  const [question, setQuestion] = useState('')
  const [error, setError] = useState<string | null>(null)

  const ask = useMutation({
    mutationFn: () => maintenanceApi.requestInfo(record.id, question),
    onSuccess: async () => {
      await onDone()
      setQuestion('')
      onClose()
    },
    onError: (askError) => setError(errorMessage(askError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Ask for more detail"
      description="Sent to whoever reported the issue. The job stays under review until they answer."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={question.trim().length < 5}
            loading={ask.isPending}
            onClick={() => {
              setError(null)
              ask.mutate()
            }}
          >
            Send
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="What do you need to know?" required>
          <Textarea
            placeholder="Is the leak coming from the tap itself or the pipe under the sink? A photo of the cabinet floor would help."
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function Detail({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{value}</dd>
    </div>
  )
}
