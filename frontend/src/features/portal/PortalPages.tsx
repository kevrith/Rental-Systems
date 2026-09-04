import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CreditCard,
  Download,
  FileText,
  Plus,
  Star,
  Wrench,
} from 'lucide-react'
import { useState } from 'react'

import { portalApi } from '@/api'
import type { MaintenanceRequest, MaintenanceStatus } from '@/api/types'
import { FileUpload, type UploadedFile } from '@/components/FileUpload'
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
  PAYMENT_STATUS_TONE,
  PRIORITY_TONE,
  Select,
  Skeleton,
  Textarea,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const CATEGORIES = ['plumbing', 'electrical', 'structural', 'appliance', 'security', 'other']

export function PortalPaymentsPage() {
  const payments = useQuery({ queryKey: queryKeys.portalPayments, queryFn: portalApi.payments })

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-slate-900">Payment history</h1>

      <Card>
        {payments.isPending ? (
          <CardBody className="space-y-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-14" />
            ))}
          </CardBody>
        ) : payments.data?.length ? (
          <ul className="divide-y divide-slate-100">
            {payments.data.map((payment) => (
              <li key={payment.id} className="flex items-start justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{kes(payment.amount)}</p>
                  <p className="text-xs text-slate-500">
                    {humanize(payment.method)}
                    {payment.mpesa_receipt && ` · ${payment.mpesa_receipt}`}
                  </p>
                  <p className="text-xs text-slate-400">
                    {payment.paid_at ? dateTime(payment.paid_at) : shortDate(payment.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <Badge tone={PAYMENT_STATUS_TONE[payment.status] ?? 'neutral'}>
                    {humanize(payment.status)}
                  </Badge>
                  {payment.receipt_url && (
                    <a
                      href={payment.receipt_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Receipt
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<CreditCard className="h-6 w-6" />}
            title="No payments yet"
            description="Your payments and receipts appear here."
          />
        )}
      </Card>
    </div>
  )
}

export function PortalDocumentsPage() {
  const documents = useQuery({ queryKey: queryKeys.portalDocuments, queryFn: portalApi.documents })

  const byCategory = (documents.data ?? []).reduce<Record<string, typeof documents.data>>(
    (groups, document) => {
      const key = document.category
      groups[key] = [...(groups[key] ?? []), document]
      return groups
    },
    {} as Record<string, typeof documents.data>,
  )

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-slate-900">My documents</h1>

      {documents.isPending ? (
        <Card>
          <CardBody className="space-y-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </CardBody>
        </Card>
      ) : documents.data?.length ? (
        Object.entries(byCategory).map(([category, items]) => (
          <Card key={category}>
            <CardHeader>
              <CardTitle>{humanize(category)}</CardTitle>
              <span className="text-xs text-slate-500">{items?.length ?? 0}</span>
            </CardHeader>
            <ul className="divide-y divide-slate-100">
              {items?.map((document) => (
                <li key={document.id}>
                  <a
                    href={document.url}
                    target="_blank"
                    rel="noreferrer"
                    data-touch-target
                    className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                      <div className="min-w-0">
                        <p className="truncate text-sm text-slate-900">{document.filename}</p>
                        <p className="text-xs text-slate-400">{shortDate(document.created_at)}</p>
                      </div>
                    </div>
                    <Download className="h-4 w-4 shrink-0 text-brand-600" />
                  </a>
                </li>
              ))}
            </ul>
          </Card>
        ))
      ) : (
        <Card>
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="No documents yet"
            description="Your lease, receipts and notices are filed here automatically."
          />
        </Card>
      )}
    </div>
  )
}

export function PortalMaintenancePage() {
  const [open, setOpen] = useState(false)
  const requests = useQuery({
    queryKey: queryKeys.portalMaintenance,
    queryFn: portalApi.maintenance,
  })

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900">Maintenance</h1>
        <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
          Report
        </Button>
      </div>

      {requests.isPending ? (
        <Card>
          <CardBody className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </CardBody>
        </Card>
      ) : requests.data?.length ? (
        <div className="space-y-3">
          {requests.data.map((request) => (
            <Card key={request.id}>
              <CardBody>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{request.title}</p>
                    <p className="mt-0.5 text-sm text-slate-600">{request.description}</p>
                    <p className="mt-1.5 text-xs text-slate-400">
                      {request.reference_code} · {shortDate(request.created_at)}
                    </p>
                    {request.info_requested && (
                      <p className="mt-2 rounded-lg bg-warn-50 p-2 text-xs text-warn-700">
                        Your landlord asked: {request.info_requested}
                      </p>
                    )}
                    {request.rejection_reason && (
                      <p className="mt-2 rounded-lg bg-danger-50 p-2 text-xs text-danger-700">
                        Not approved — {humanize(request.rejection_reason)}
                        {request.rejection_note ? `. ${request.rejection_note}` : ''}
                      </p>
                    )}
                    {request.resolution_notes && (
                      <p className="mt-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-600">
                        {request.resolution_notes}
                      </p>
                    )}
                    <MaintenanceProgress status={request.status} />
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <Badge tone={MAINTENANCE_STATUS_TONE[request.status] ?? 'neutral'}>
                      {humanize(request.status)}
                    </Badge>
                    <Badge tone={PRIORITY_TONE[request.priority] ?? 'neutral'}>
                      {humanize(request.priority)}
                    </Badge>
                  </div>
                </div>

                <RateJob request={request} />
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Wrench className="h-6 w-6" />}
            title="Nothing reported"
            description="Report a problem and your landlord is notified straight away."
            action={
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>
                Report an issue
              </Button>
            }
          />
        </Card>
      )}

      <ReportDialog open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

/** The tenant-facing version of the lifecycle: five steps, no jargon (US-063). */
const PROGRESS_STEPS = [
  { key: 'submitted', label: 'Reported' },
  { key: 'under_review', label: 'Reviewed' },
  { key: 'approved', label: 'Approved' },
  { key: 'in_progress', label: 'Being fixed' },
  { key: 'completed', label: 'Done' },
]

function MaintenanceProgress({ status }: { status: MaintenanceStatus }) {
  if (status === 'rejected' || status === 'cancelled') return null

  const reached: Record<MaintenanceStatus, number> = {
    submitted: 0,
    under_review: 1,
    approved: 2,
    assigned: 2,
    in_progress: 3,
    completed: 4,
    closed: 4,
    rejected: 0,
    cancelled: 0,
  }
  const current = reached[status] ?? 0

  return (
    <ol className="mt-3 flex items-center gap-1">
      {PROGRESS_STEPS.map((step, index) => (
        <li key={step.key} className="flex flex-1 flex-col gap-1">
          <span
            className={
              index <= current ? 'h-1 rounded-full bg-brand-500' : 'h-1 rounded-full bg-slate-200'
            }
          />
          <span
            className={
              index <= current ? 'text-[10px] text-slate-600' : 'text-[10px] text-slate-300'
            }
          >
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  )
}

function RateJob({ request }: { request: MaintenanceRequest }) {
  const queryClient = useQueryClient()
  const [rating, setRating] = useState<number | null>(null)
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState<string | null>(null)

  const rate = useMutation({
    mutationFn: () =>
      portalApi.rateMaintenance(request.id, {
        rating: rating!,
        feedback: feedback || undefined,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.portalMaintenance }),
    onError: (rateError) => setError(errorMessage(rateError)),
  })

  const finished = request.status === 'completed' || request.status === 'closed'
  if (!finished) return null

  if (request.tenant_rating) {
    return (
      <p className="mt-3 flex items-center gap-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <Star className="h-3.5 w-3.5 fill-warn-400 text-warn-400" />
        You rated this {request.tenant_rating} out of 5. Thank you.
      </p>
    )
  }

  return (
    <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
      <p className="text-xs text-slate-500">How did this repair go?</p>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            aria-label={`${value} star${value === 1 ? '' : 's'}`}
            onClick={() => setRating(value === rating ? null : value)}
            className="rounded-lg p-0.5"
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

      {rating !== null && (
        <>
          <Textarea
            placeholder="Anything you would like the landlord to know? (optional)"
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
          />
          <Button size="sm" loading={rate.isPending} onClick={() => {
            setError(null)
            rate.mutate()
          }}>
            Send feedback
          </Button>
        </>
      )}

      {error && <Alert tone="danger">{error}</Alert>}
    </div>
  )
}

function ReportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('other')
  const [priority, setPriority] = useState('routine')
  const [photos, setPhotos] = useState<UploadedFile[]>([])
  const [error, setError] = useState<string | null>(null)

  const photoRequired = priority !== 'routine'

  const create = useMutation({
    mutationFn: () =>
      portalApi.createMaintenance({
        title,
        description,
        category,
        priority,
        photo_file_ids: photos.map((photo) => photo.id),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.portalMaintenance })
      close()
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  const close = () => {
    setTitle('')
    setDescription('')
    setCategory('other')
    setPriority('routine')
    setPhotos([])
    setError(null)
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Report a problem"
      description="Your landlord and caretaker are notified immediately."
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            disabled={!title || !description || (photoRequired && photos.length === 0)}
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Submit
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="What's wrong?" required>
          <Input
            placeholder="Kitchen tap leaking"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>

        <Field label="Tell us more" required>
          <Textarea
            placeholder="It has been dripping since Tuesday and the cabinet is getting wet."
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <Select value={category} onChange={(event) => setCategory(event.target.value)}>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {humanize(value)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="How urgent?">
            <Select value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="routine">Routine</option>
              <option value="urgent">Urgent</option>
              <option value="emergency">Emergency</option>
            </Select>
          </Field>
        </div>

        <FileUpload
          value={photos}
          onChange={setPhotos}
          category="maintenance"
          max={3}
          label={`Photos${photoRequired ? ' (required)' : ''}`}
          hint={
            photoRequired
              ? 'A photo is required for urgent and emergency reports.'
              : 'A photo helps get it fixed faster.'
          }
        />

        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}
      </div>
    </Dialog>
  )
}
