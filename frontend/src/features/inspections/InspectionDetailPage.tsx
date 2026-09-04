import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  CheckCircle2,
  Download,
  FileText,
  MapPin,
  Scale,
  TriangleAlert,
} from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { inspectionsApi } from '@/api'
import type { InspectionRoom } from '@/api/types'
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
  Textarea,
} from '@/components/ui'
import {
  CHANGE_LABEL,
  CHANGE_TONE,
  CONDITION_TONE,
} from '@/features/inspections/condition'
import { dateTime, errorMessage, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** One side of the comparison, or one room of a plain report. */
function RoomPanel({ room, label }: { room: InspectionRoom | null; label: string }) {
  return (
    <div className="rounded-card border border-slate-200 p-3">
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      {room === null ? (
        <p className="text-sm text-slate-400">Not recorded</p>
      ) : (
        <>
          {room.condition && (
            <Badge tone={CONDITION_TONE[room.condition]}>{humanize(room.condition)}</Badge>
          )}
          {room.notes && <p className="mt-2 text-sm text-slate-600">{room.notes}</p>}
          {room.photos && room.photos.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {room.photos.map((photo) => (
                <a key={photo.id} href={photo.url} target="_blank" rel="noopener noreferrer">
                  <img
                    src={photo.url}
                    alt={`${room.name} — ${photo.filename}`}
                    className="h-20 w-20 rounded-md border border-slate-200 object-cover"
                  />
                </a>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/**
 * Inspection review (US-050, US-051).
 *
 * For a move-out this is the comparison viewer: every room shown at move-in
 * beside the same room at move-out, with the ones that deteriorated called out —
 * that side-by-side is what a deposit deduction has to be justified against, so
 * the deduction form sits directly beneath it rather than on a separate screen.
 */
export function InspectionDetailPage() {
  const { inspectionId = '' } = useParams()
  const queryClient = useQueryClient()

  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [deductOpen, setDeductOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')

  const report = useQuery({
    queryKey: queryKeys.inspection(inspectionId),
    queryFn: () => inspectionsApi.get(inspectionId),
    enabled: Boolean(inspectionId),
  })

  const isMoveOut = report.data?.inspection_type === 'move_out'

  const comparison = useQuery({
    queryKey: queryKeys.inspectionComparison(inspectionId),
    queryFn: () => inspectionsApi.comparison(inspectionId),
    enabled: Boolean(inspectionId) && isMoveOut && report.data?.status === 'submitted',
  })

  const documents = useQuery({
    queryKey: ['inspections', inspectionId, 'documents'],
    queryFn: () => inspectionsApi.documents(inspectionId),
    enabled: Boolean(inspectionId) && report.data?.status === 'submitted',
  })

  const deduct = useMutation({
    mutationFn: () =>
      inspectionsApi.setDeduction(inspectionId, {
        deduction_amount: amount,
        deduction_notes: reason.trim(),
      }),
    onSuccess: async () => {
      setError(null)
      setNotice('Deduction recorded. It will appear on the tenant’s move-out statement.')
      setDeductOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['inspections', inspectionId] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (report.isPending) return <PageLoader />
  if (report.isError) return <Alert tone="danger">{errorMessage(report.error)}</Alert>

  const record = report.data
  const deposit = comparison.data?.deposit_held
  const overDeposit =
    deposit !== null && deposit !== undefined && Number(amount) > Number(deposit)

  return (
    <div>
      <PageHeader
        title={`${humanize(record.inspection_type)} inspection`}
        description={`${record.reference_code} · ${record.status === 'submitted' ? dateTime(record.submitted_at) : 'Draft'}`}
        backTo="/inspections"
        backLabel="Inspections"
        actions={
          <>
            {documents.data?.report && (
              <a
                href={documents.data.report.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                <Download className="h-4 w-4" />
                Report PDF
              </a>
            )}
            {documents.data?.comparison && (
              <a
                href={documents.data.comparison.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                <FileText className="h-4 w-4" />
                Comparison PDF
              </a>
            )}
          </>
        }
      />

      {error && <Alert tone="danger" className="mb-4">{error}</Alert>}
      {notice && <Alert tone="success" className="mb-4">{notice}</Alert>}

      <Card className="mb-4">
        <CardBody className="grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <p className="text-slate-500">Inspector</p>
            <p className="font-medium text-slate-900">{record.inspector_name ?? '—'}</p>
          </div>
          <div>
            <p className="text-slate-500">Rooms</p>
            <p className="font-medium text-slate-900">{record.rooms.length}</p>
          </div>
          <div>
            <p className="text-slate-500">Location</p>
            <p className="font-medium text-slate-900">
              {record.gps_latitude !== null && record.gps_longitude !== null ? (
                <>
                  <MapPin className="mr-1 inline h-3.5 w-3.5 text-slate-400" />
                  {record.gps_latitude.toFixed(4)}, {record.gps_longitude.toFixed(4)}
                </>
              ) : (
                '—'
              )}
            </p>
          </div>
          {record.notes && (
            <div className="sm:col-span-3">
              <p className="text-slate-500">Notes</p>
              <p className="text-slate-700">{record.notes}</p>
            </div>
          )}
        </CardBody>
      </Card>

      {isMoveOut && comparison.data ? (
        <>
          <Card className="mb-4">
            <CardHeader>
              <CardTitle>Move-in vs move-out</CardTitle>
              <p className="text-sm text-slate-500">
                {comparison.data.move_in
                  ? `Compared against ${comparison.data.move_in.reference_code} from ${dateTime(comparison.data.move_in.submitted_at)}.`
                  : 'There is no move-in inspection for this tenancy, so nothing can be compared — a deduction here would be hard to defend.'}
              </p>
            </CardHeader>
            <CardBody>
              {comparison.data.rooms_degraded > 0 ? (
                <Alert tone="warn" className="mb-4">
                  <TriangleAlert className="mr-1.5 inline h-4 w-4" />
                  {comparison.data.rooms_degraded} room
                  {comparison.data.rooms_degraded === 1 ? '' : 's'} in worse condition than at
                  move-in.
                </Alert>
              ) : (
                <Alert tone="success" className="mb-4">
                  <CheckCircle2 className="mr-1.5 inline h-4 w-4" />
                  No room came back worse than it went in.
                </Alert>
              )}

              <div className="space-y-4">
                {comparison.data.rooms.map((row) => (
                  <div key={row.name} className="rounded-card border border-slate-200 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="font-medium text-slate-900">{row.name}</h3>
                      <Badge tone={CHANGE_TONE[row.change]}>{CHANGE_LABEL[row.change]}</Badge>
                    </div>
                    <div className="grid items-start gap-3 sm:grid-cols-[1fr_auto_1fr]">
                      <RoomPanel room={row.before} label="At move-in" />
                      <ArrowRight className="mx-auto hidden h-4 w-4 self-center text-slate-300 sm:block" />
                      <RoomPanel room={row.after} label="At move-out" />
                    </div>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>
                <Scale className="mr-1.5 inline h-4 w-4 text-slate-400" />
                Deposit settlement
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <dl className="grid gap-3 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-slate-500">Deposit held</dt>
                  <dd className="font-semibold text-slate-900">
                    {comparison.data.deposit_held ? kes(comparison.data.deposit_held) : '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Deduction</dt>
                  <dd className="font-semibold text-danger-700">
                    {comparison.data.deposit_deduction
                      ? kes(comparison.data.deposit_deduction)
                      : 'None'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Refund due</dt>
                  <dd className="font-semibold text-money-700">
                    {comparison.data.deposit_held
                      ? kes(
                          Number(comparison.data.deposit_held) -
                            Number(comparison.data.deposit_deduction ?? 0),
                        )
                      : '—'}
                  </dd>
                </div>
              </dl>

              {comparison.data.deduction_notes && (
                <div className="rounded-card bg-slate-50 p-3 text-sm text-slate-700">
                  {comparison.data.deduction_notes}
                </div>
              )}

              <Button
                variant="secondary"
                onClick={() => {
                  setError(null)
                  setAmount(comparison.data?.deposit_deduction ?? '')
                  setReason(comparison.data?.deduction_notes ?? '')
                  setDeductOpen(true)
                }}
              >
                {comparison.data.deposit_deduction ? 'Change the deduction' : 'Deduct from deposit'}
              </Button>
            </CardBody>
          </Card>
        </>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Rooms</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {record.rooms.map((room) => (
              <RoomPanel key={room.name} room={room} label={room.name} />
            ))}
          </CardBody>
        </Card>
      )}

      <Dialog
        open={deductOpen}
        onClose={() => setDeductOpen(false)}
        title="Deduct from the deposit"
        description="The tenant sees this amount and the reason on their move-out statement, so be specific."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeductOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={deduct.isPending}
              disabled={!amount || Number(amount) < 0 || reason.trim().length < 5 || overDeposit}
              onClick={() => deduct.mutate()}
            >
              Record deduction
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field
            label="Amount (KES)"
            required
            error={overDeposit ? 'That is more than the deposit held.' : undefined}
          >
            <Input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              invalid={overDeposit}
            />
          </Field>
          <Field
            label="What it is for"
            required
            hint="Tie it to a room the comparison above shows deteriorated."
          >
            <Textarea
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="e.g. Repainting the living room — marked 'good' at move-in, 'poor' at move-out"
            />
          </Field>
        </div>
      </Dialog>
    </div>
  )
}
