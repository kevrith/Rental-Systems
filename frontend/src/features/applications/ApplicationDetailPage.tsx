import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CalendarClock,
  Check,
  FileText,
  Phone,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  UserCheck,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'

import { applicationsApi } from '@/api'
import type { TenantApplication } from '@/api/types'
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
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

import { APPLICATION_STATUS_TONE } from './ApplicationsPage'
import { ScoreBreakdownCard } from './score'

const REJECTION_REASONS = [
  { value: 'insufficient_income', label: 'Income does not support the rent' },
  { value: 'failed_reference_check', label: 'Failed the landlord reference check' },
  { value: 'incomplete_application', label: 'Application is incomplete' },
  { value: 'no_guarantor', label: 'No acceptable guarantor' },
  { value: 'unit_taken', label: 'Unit has been let to someone else' },
  { value: 'other', label: 'Other (explain below)' },
]

const GUARANTOR_TONE: Record<string, 'neutral' | 'success' | 'warn' | 'danger'> = {
  pending: 'warn',
  acknowledged: 'success',
  declined: 'danger',
  expired: 'neutral',
}

const REFERENCE_TONE: Record<string, 'neutral' | 'success' | 'warn' | 'danger'> = {
  sent: 'warn',
  positive: 'success',
  negative: 'danger',
  no_response: 'neutral',
}

type ActionKind = 'approve' | 'reject' | 'interview' | 'guarantor' | 'reference' | null

export function ApplicationDetailPage() {
  const { applicationId } = useParams<{ applicationId: string }>()
  const queryClient = useQueryClient()
  const [action, setAction] = useState<ActionKind>(null)
  const [error, setError] = useState<string | null>(null)

  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManage = permissions?.includes('application:manage')
  const canDecide = permissions?.includes('application:decide')

  const application = useQuery({
    queryKey: queryKeys.application(applicationId!),
    queryFn: () => applicationsApi.get(applicationId!),
    enabled: Boolean(applicationId),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['applications'] })
    await queryClient.invalidateQueries({ queryKey: ['units'] })
    await queryClient.invalidateQueries({ queryKey: ['tenants'] })
  }

  const review = useMutation({
    mutationFn: () => applicationsApi.review(applicationId!),
    onSuccess: refresh,
    onError: (reviewError) => setError(errorMessage(reviewError)),
  })

  if (application.isPending) return <PageLoader />
  if (application.isError) {
    return (
      <Alert tone="danger" title="Could not load this application">
        {errorMessage(application.error)}
      </Alert>
    )
  }

  const record = application.data
  const open = ['submitted', 'under_review', 'interview_scheduled'].includes(record.status)
  const negativeReference = record.references.some((r) => r.status === 'negative')

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={record.full_name}
        description={`${record.reference_code} · ${record.property_name} unit ${record.unit_number}`}
        backTo="/applications"
        backLabel="All applications"
        actions={
          <Badge tone={APPLICATION_STATUS_TONE[record.status] ?? 'neutral'}>
            {humanize(record.status)}
          </Badge>
        }
      />

      {negativeReference && (
        <Alert
          tone="danger"
          className="mb-4"
          icon={<AlertTriangle className="h-4 w-4" />}
          title="A previous landlord gave a negative reference"
        >
          Read the reference below before making a decision.
        </Alert>
      )}

      {record.rejection_reason && (
        <Alert tone="danger" className="mb-4" title="Not approved">
          {humanize(record.rejection_reason)}
          {record.decision_note ? ` — ${record.decision_note}` : ''}
          {record.decided_by_name ? ` (${record.decided_by_name}, ${shortDate(record.decided_at)})` : ''}
        </Alert>
      )}

      {record.status === 'approved' && (
        <Alert tone="success" className="mb-4" title="Approved" icon={<Check className="h-4 w-4" />}>
          The unit is reserved and a tenant record has been created.{' '}
          {record.tenant_id && (
            <Link
              to={`/tenancies/new?tenant_id=${record.tenant_id}&unit_id=${record.unit_id}`}
              className="font-medium underline"
            >
              Start the tenancy
            </Link>
          )}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>The applicant</CardTitle>
              <a
                href={`tel:${record.phone_number}`}
                className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700"
              >
                <Phone className="h-4 w-4" />
                {record.phone_number}
              </a>
            </CardHeader>
            <CardBody className="space-y-4">
              <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <Detail label="National ID" value={record.national_id ?? '—'} />
                <Detail label="Email" value={record.email ?? '—'} />
                <Detail label="Occupants" value={String(record.occupants)} />
                <Detail
                  label="Wants to move in"
                  value={record.intended_move_in ? shortDate(record.intended_move_in) : '—'}
                />
                <Detail label="Currently lives at" value={record.current_address ?? '—'} />
                <Detail
                  label="Years there"
                  value={record.years_at_current_address ?? '—'}
                />
              </dl>
              {record.reason_for_moving && (
                <div className="rounded-lg bg-slate-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Reason for moving</p>
                  <p className="mt-0.5 text-sm text-slate-700">{record.reason_for_moving}</p>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>How they will pay</CardTitle>
            </CardHeader>
            <CardBody>
              <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <Detail label="Status" value={humanize(record.employment_status)} />
                <Detail label="Employer" value={record.employer_name ?? '—'} />
                <Detail label="Role" value={record.job_title ?? '—'} />
                <Detail
                  label="Time in the job"
                  value={
                    record.months_in_employment
                      ? `${record.months_in_employment} month(s)`
                      : '—'
                  }
                />
                <Detail
                  label="Monthly income"
                  value={record.monthly_income ? kes(record.monthly_income) : '—'}
                />
                <Detail
                  label="Rent on this unit"
                  value={record.monthly_rent ? kes(record.monthly_rent) : '—'}
                />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Guarantors</CardTitle>
              {canManage && open && (
                <Button size="sm" variant="outline" onClick={() => setAction('guarantor')}>
                  Add a guarantor
                </Button>
              )}
            </CardHeader>
            <CardBody className="space-y-3">
              {record.guarantors.length ? (
                record.guarantors.map((guarantor) => (
                  <div
                    key={guarantor.id}
                    className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-200 p-3"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900">{guarantor.full_name}</p>
                      <p className="text-xs text-slate-500">
                        {guarantor.relationship_to_applicant} · {guarantor.phone_number}
                        {guarantor.monthly_income
                          ? ` · earns ${kes(guarantor.monthly_income)}`
                          : ''}
                      </p>
                      {guarantor.declined_reason && (
                        <p className="mt-1 text-xs text-danger-700">{guarantor.declined_reason}</p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      <Badge tone={GUARANTOR_TONE[guarantor.status] ?? 'neutral'}>
                        {humanize(guarantor.status)}
                      </Badge>
                      {guarantor.signature_id ? (
                        <span className="inline-flex items-center gap-1 text-xs text-money-700">
                          <Check className="h-3.5 w-3.5" />
                          Guarantee signed
                        </span>
                      ) : (
                        guarantor.status === 'acknowledged' &&
                        canManage && (
                          <SignGuaranteeButton
                            applicationId={record.id}
                            guarantorId={guarantor.id}
                            onDone={refresh}
                          />
                        )
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  Nobody has been named. A confirmed guarantor is worth 20 points on the score.
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Landlord references</CardTitle>
              {canManage && open && (
                <Button size="sm" variant="outline" onClick={() => setAction('reference')}>
                  Ask a landlord
                </Button>
              )}
            </CardHeader>
            <CardBody className="space-y-3">
              {record.references.length ? (
                record.references.map((check) => (
                  <div
                    key={check.id}
                    className="rounded-lg border border-slate-200 p-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900">{check.landlord_name}</p>
                        <p className="text-xs text-slate-500">
                          {check.landlord_phone}
                          {check.property_reference ? ` · ${check.property_reference}` : ''} · asked{' '}
                          {shortDate(check.sent_at)}
                        </p>
                      </div>
                      <Badge tone={REFERENCE_TONE[check.status] ?? 'neutral'}>
                        {humanize(check.status)}
                      </Badge>
                    </div>
                    {check.responded_at && (
                      <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-600">
                        <span className="inline-flex items-center gap-1">
                          {check.paid_on_time ? (
                            <Check className="h-3.5 w-3.5 text-money-600" />
                          ) : (
                            <X className="h-3.5 w-3.5 text-danger-600" />
                          )}
                          Paid on time
                        </span>
                        <span className="inline-flex items-center gap-1">
                          {check.would_rent_again ? (
                            <Check className="h-3.5 w-3.5 text-money-600" />
                          ) : (
                            <X className="h-3.5 w-3.5 text-danger-600" />
                          )}
                          Would rent again
                        </span>
                      </div>
                    )}
                    {check.response_note && (
                      <p className="mt-2 rounded bg-slate-50 p-2 text-sm text-slate-700">
                        {check.response_note}
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  No reference requested yet. We ask the previous landlord automatically when the
                  applicant gives us their number.
                </p>
              )}
            </CardBody>
          </Card>

          {(record.id_document_url || record.passport_photo_url || record.payslip_urls.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle>Documents</CardTitle>
              </CardHeader>
              <CardBody className="flex flex-wrap gap-3">
                {record.passport_photo_url && (
                  <a
                    href={record.passport_photo_url}
                    target="_blank"
                    rel="noreferrer"
                    className="h-24 w-24 overflow-hidden rounded-lg border border-slate-200"
                  >
                    <img
                      src={record.passport_photo_url}
                      alt="Passport photo"
                      className="h-full w-full object-cover"
                    />
                  </a>
                )}
                {[
                  ...(record.id_document_url
                    ? [{ url: record.id_document_url, label: 'ID document' }]
                    : []),
                  ...record.payslip_urls.map((url, index) => ({
                    url,
                    label: `Payslip ${index + 1}`,
                  })),
                ].map((doc) => (
                  <a
                    key={doc.url}
                    href={doc.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  >
                    <FileText className="h-4 w-4 text-slate-400" />
                    {doc.label}
                  </a>
                ))}
              </CardBody>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Screening score</CardTitle>
            </CardHeader>
            <CardBody>
              <ScoreBreakdownCard breakdown={record.score_breakdown} />
            </CardBody>
          </Card>

          {(canManage || canDecide) && open && (
            <Card>
              <CardHeader>
                <CardTitle>Decision</CardTitle>
              </CardHeader>
              <CardBody className="space-y-3">
                {record.status === 'submitted' && canManage && (
                  <Button
                    variant="outline"
                    className="w-full justify-center"
                    loading={review.isPending}
                    onClick={() => {
                      setError(null)
                      review.mutate()
                    }}
                  >
                    Start review
                  </Button>
                )}

                {canManage && (
                  <Button
                    variant="outline"
                    className="w-full justify-center"
                    icon={<CalendarClock className="h-4 w-4" />}
                    onClick={() => setAction('interview')}
                  >
                    {record.interview_at ? 'Reschedule interview' : 'Schedule an interview'}
                  </Button>
                )}

                {canDecide && (
                  <>
                    <Button
                      className="w-full justify-center"
                      icon={<ThumbsUp className="h-4 w-4" />}
                      onClick={() => setAction('approve')}
                    >
                      Approve
                    </Button>
                    <Button
                      variant="danger"
                      className="w-full justify-center"
                      icon={<ThumbsDown className="h-4 w-4" />}
                      onClick={() => setAction('reject')}
                    >
                      Reject
                    </Button>
                  </>
                )}

                {error && <Alert tone="danger">{error}</Alert>}
              </CardBody>
            </Card>
          )}

          {record.interview_at && (
            <Card>
              <CardHeader>
                <CardTitle>Interview</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="text-sm text-slate-800">{dateTime(record.interview_at)}</p>
                {record.interview_notes && (
                  <p className="mt-1 text-sm text-slate-600">{record.interview_notes}</p>
                )}
              </CardBody>
            </Card>
          )}
        </div>
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
      <InterviewDialog
        open={action === 'interview'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
      <GuarantorDialog
        open={action === 'guarantor'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
      <ReferenceDialog
        open={action === 'reference'}
        record={record}
        onClose={() => setAction(null)}
        onDone={refresh}
      />
    </div>
  )
}

type DialogProps = {
  open: boolean
  record: TenantApplication
  onClose: () => void
  onDone: () => Promise<void>
}

function ApproveDialog({ open, record, onClose, onDone }: DialogProps) {
  const [note, setNote] = useState('')
  const [rejectOthers, setRejectOthers] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const approve = useMutation({
    mutationFn: () =>
      applicationsApi.approve(record.id, { note: note || undefined, reject_others: rejectOthers }),
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
      title={`Approve ${record.full_name}`}
      description="This reserves the unit and creates their tenant record."
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
        <Alert tone="info" icon={<UserCheck className="h-4 w-4" />}>
          {record.full_name} is notified on WhatsApp, and unit {record.unit_number} moves to
          Reserved until the tenancy starts.
        </Alert>

        <Field label="Note" hint="Kept on the file — not sent to the applicant">
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>

        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 rounded border-slate-300"
            checked={rejectOthers}
            onChange={(event) => setRejectOthers(event.target.checked)}
          />
          <span>
            Tell the other applicants the unit is taken
            <span className="block text-xs text-slate-500">
              Closes the rest of the waiting list and sends each of them a message.
            </span>
          </span>
        </label>

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
    mutationFn: () => applicationsApi.reject(record.id, { reason, note: note || undefined }),
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
      title={`Reject ${record.full_name}`}
      description="The reason is sent to the applicant, so make it one you would say to their face."
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
        <Field label="Note" required={reason === 'other'}>
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function InterviewDialog({ open, record, onClose, onDone }: DialogProps) {
  const [when, setWhen] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const schedule = useMutation({
    mutationFn: () =>
      applicationsApi.interview(record.id, {
        scheduled_for: new Date(when).toISOString(),
        note: note || undefined,
      }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (scheduleError) => setError(errorMessage(scheduleError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Schedule an interview"
      description="The applicant gets the date and time on WhatsApp."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!when}
            loading={schedule.isPending}
            onClick={() => {
              setError(null)
              schedule.mutate()
            }}
          >
            Schedule
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="When" required>
          <Input
            type="datetime-local"
            value={when}
            onChange={(event) => setWhen(event.target.value)}
          />
        </Field>
        <Field label="Anything they should bring?">
          <Textarea
            placeholder="Please bring your original ID and your last three payslips."
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function GuarantorDialog({ open, record, onClose, onDone }: DialogProps) {
  const [form, setForm] = useState({
    full_name: '',
    relationship_to_applicant: '',
    phone_number: '',
    monthly_income: '',
    employer_name: '',
    national_id: '',
  })
  const [error, setError] = useState<string | null>(null)

  const add = useMutation({
    mutationFn: () =>
      applicationsApi.addGuarantor(record.id, {
        ...form,
        monthly_income: form.monthly_income || null,
        employer_name: form.employer_name || null,
        national_id: form.national_id || null,
      }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (addError) => setError(errorMessage(addError)),
  })

  const valid =
    form.full_name.trim().length > 1 &&
    form.relationship_to_applicant.trim().length > 1 &&
    form.phone_number.trim().length >= 10

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a guarantor"
      description="They get a WhatsApp asking them to confirm they accept."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={add.isPending}
            onClick={() => {
              setError(null)
              add.mutate()
            }}
          >
            Add and ask
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Full name" required>
            <Input
              value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            />
          </Field>
          <Field label="Relationship" required>
            <Input
              placeholder="Father, employer, sibling"
              value={form.relationship_to_applicant}
              onChange={(event) =>
                setForm({ ...form, relationship_to_applicant: event.target.value })
              }
            />
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Phone" required>
            <Input
              placeholder="+2547XXXXXXXX"
              value={form.phone_number}
              onChange={(event) => setForm({ ...form, phone_number: event.target.value })}
            />
          </Field>
          <Field label="National ID">
            <Input
              value={form.national_id}
              onChange={(event) => setForm({ ...form, national_id: event.target.value })}
            />
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Employer">
            <Input
              value={form.employer_name}
              onChange={(event) => setForm({ ...form, employer_name: event.target.value })}
            />
          </Field>
          <Field label="Monthly income (KES)">
            <Input
              type="number"
              min="0"
              value={form.monthly_income}
              onChange={(event) => setForm({ ...form, monthly_income: event.target.value })}
            />
          </Field>
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function ReferenceDialog({ open, record, onClose, onDone }: DialogProps) {
  const [form, setForm] = useState({
    landlord_name: record.current_landlord_name ?? '',
    landlord_phone: record.current_landlord_phone ?? '',
    property_reference: record.current_address ?? '',
  })
  const [error, setError] = useState<string | null>(null)

  const ask = useMutation({
    mutationFn: () =>
      applicationsApi.requestReference(record.id, {
        ...form,
        property_reference: form.property_reference || null,
      }),
    onSuccess: async () => {
      await onDone()
      onClose()
    },
    onError: (askError) => setError(errorMessage(askError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Ask a previous landlord"
      description="Two questions over WhatsApp: did they pay on time, and would you rent to them again?"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={form.landlord_name.length < 2 || form.landlord_phone.length < 10}
            loading={ask.isPending}
            onClick={() => {
              setError(null)
              ask.mutate()
            }}
          >
            Send the request
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Landlord name" required>
          <Input
            value={form.landlord_name}
            onChange={(event) => setForm({ ...form, landlord_name: event.target.value })}
          />
        </Field>
        <Field label="Their phone" required>
          <Input
            placeholder="+2547XXXXXXXX"
            value={form.landlord_phone}
            onChange={(event) => setForm({ ...form, landlord_phone: event.target.value })}
          />
        </Field>
        <Field label="Which property?" hint="Helps them remember the tenant">
          <Input
            value={form.property_reference}
            onChange={(event) => setForm({ ...form, property_reference: event.target.value })}
          />
        </Field>
        <Alert tone="info" icon={<ShieldCheck className="h-4 w-4" />}>
          If nobody answers within five days the request is closed and the score stops crediting it.
        </Alert>
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

/** Sends the deed of guarantee out for OTP-verified signing, once the guarantor
 *  has actually agreed to be one. */
function SignGuaranteeButton({
  applicationId,
  guarantorId,
  onDone,
}: {
  applicationId: string
  guarantorId: string
  onDone: () => Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)

  const send = useMutation({
    mutationFn: () => applicationsApi.sendGuaranteeForSigning(applicationId, guarantorId),
    onSuccess: onDone,
    onError: (sendError) => setError(errorMessage(sendError)),
  })

  return (
    <div className="text-right">
      <Button
        size="sm"
        variant="outline"
        loading={send.isPending}
        onClick={() => {
          setError(null)
          send.mutate()
        }}
      >
        Send guarantee to sign
      </Button>
      {error && <p className="mt-1 max-w-48 text-xs text-danger-700">{error}</p>}
    </div>
  )
}
