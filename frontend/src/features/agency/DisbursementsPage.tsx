import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Banknote,
  Calculator,
  CheckCircle2,
  FileText,
  Send,
  Smartphone,
  ThumbsUp,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { agencyApi } from '@/api'
import type { Disbursement } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import {
  CAN_PAY,
  CAN_REVIEW,
  DISBURSEMENT_STATUS_TONE,
} from '@/features/agency/disbursement-status'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** First and last day of the previous whole month — the usual payout period. */
function lastMonth(): { start: string; end: string } {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const end = new Date(now.getFullYear(), now.getMonth(), 0)
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  return { start: iso(start), end: iso(end) }
}

export function DisbursementsPage() {
  const queryClient = useQueryClient()
  const defaults = lastMonth()

  const [ownerId, setOwnerId] = useState('')
  const [periodStart, setPeriodStart] = useState(defaults.start)
  const [periodEnd, setPeriodEnd] = useState(defaults.end)
  const [error, setError] = useState<string | null>(null)

  const [payFor, setPayFor] = useState<Disbursement | null>(null)
  const [method, setMethod] = useState('bank_transfer')
  const [reference, setReference] = useState('')

  const [rejectFor, setRejectFor] = useState<Disbursement | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const owners = useQuery({ queryKey: queryKeys.ownerProfiles, queryFn: agencyApi.ownerProfiles })
  const disbursements = useQuery({
    queryKey: queryKeys.disbursements({ all: true }),
    queryFn: () => agencyApi.disbursements(),
  })

  const preview = useQuery({
    queryKey: ['agency', 'disbursement-preview', ownerId, periodStart, periodEnd],
    queryFn: () =>
      agencyApi.previewDisbursement({
        owner_profile_id: ownerId,
        period_start: periodStart,
        period_end: periodEnd,
      }),
    // Only ask once an owner is picked — the endpoint requires one.
    enabled: Boolean(ownerId && periodStart && periodEnd),
  })

  const create = useMutation({
    mutationFn: () =>
      agencyApi.createDisbursement({
        owner_profile_id: ownerId,
        period_start: periodStart,
        period_end: periodEnd,
      }),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const approve = useMutation({
    mutationFn: (id: string) => agencyApi.approveDisbursement(id),
    onSuccess: async (row) => {
      setError(null)
      setNotice(`${row.reference_code} approved — it can now be paid out.`)
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const reject = useMutation({
    mutationFn: (id: string) => agencyApi.rejectDisbursement(id, { reason: rejectReason.trim() }),
    onSuccess: async () => {
      setError(null)
      setRejectFor(null)
      setRejectReason('')
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const payViaMpesa = useMutation({
    mutationFn: (id: string) => agencyApi.payDisbursementViaMpesa(id),
    onSuccess: async (row) => {
      setError(null)
      setNotice(
        row.status === 'completed'
          ? `${row.reference_code} paid out and the statement has been sent.`
          : `${row.reference_code} is on its way — M-Pesa will confirm shortly.`,
      )
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  /** Statements are rendered on demand, so this fetches the link then opens it. */
  const openStatement = useMutation({
    mutationFn: (id: string) => agencyApi.disbursementStatement(id),
    onSuccess: (statement) => {
      setError(null)
      window.open(statement.url, '_blank', 'noopener,noreferrer')
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const markPaid = useMutation({
    mutationFn: (id: string) =>
      agencyApi.markDisbursementPaid(id, { payment_method: method, payment_reference: reference }),
    onSuccess: async () => {
      setPayFor(null)
      setReference('')
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (owners.isPending) return <PageLoader />

  const ownerList = owners.data ?? []
  const rows = disbursements.data ?? []
  const ownerName = (id: string) =>
    ownerList.find((owner) => owner.id === id)?.full_name ?? 'Unknown owner'

  return (
    <div>
      <PageHeader
        title="Disbursements"
        description="Work out what each owner is owed, approve it, then release the payout."
        backTo="/agency"
        backLabel="Agency"
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

      {ownerList.length === 0 ? (
        <EmptyState
          icon={<Banknote className="h-6 w-6" />}
          title="No owner clients yet"
          description="Disbursements are calculated per owner client. Add one first."
          action={
            <Link to="/agency/owners/new" className="text-brand-700 hover:underline">
              Add an owner client
            </Link>
          }
        />
      ) : (
        <>
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Calculate a payout</CardTitle>
              <CardDescription>
                Preview the breakdown before you commit it. Nothing is recorded until you create
                the disbursement.
              </CardDescription>
            </CardHeader>
            <CardBody className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Owner client" required>
                  <Select value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
                    <option value="">Choose an owner…</option>
                    {ownerList.map((owner) => (
                      <option key={owner.id} value={owner.id}>
                        {owner.full_name} ({owner.management_fee_percent}%)
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Period start" required>
                  <Input
                    type="date"
                    value={periodStart}
                    onChange={(event) => setPeriodStart(event.target.value)}
                  />
                </Field>
                <Field label="Period end" required>
                  <Input
                    type="date"
                    value={periodEnd}
                    onChange={(event) => setPeriodEnd(event.target.value)}
                  />
                </Field>
              </div>

              {!ownerId ? (
                <p className="text-sm text-slate-500">
                  <Calculator className="mr-1.5 inline h-4 w-4" />
                  Pick an owner to see what they are owed for this period.
                </p>
              ) : preview.isPending ? (
                <p className="text-sm text-slate-500">Calculating…</p>
              ) : preview.isError ? (
                <Alert tone="danger">{errorMessage(preview.error)}</Alert>
              ) : (
                <div className="rounded-card border border-slate-200 bg-slate-50 p-4">
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-600">
                        Gross rent collected
                        <span className="ml-1 text-xs text-slate-400">
                          ({preview.data.payment_count} payment
                          {preview.data.payment_count === 1 ? '' : 's'})
                        </span>
                      </dt>
                      <dd className="font-medium">{kes(preview.data.gross_rent)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-600">Management fee</dt>
                      <dd className="text-slate-700">−{kes(preview.data.management_fee)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-600">Maintenance costs</dt>
                      <dd className="text-slate-700">−{kes(preview.data.maintenance_costs)}</dd>
                    </div>
                    {preview.data.other_deductions > 0 && (
                      <div className="flex justify-between">
                        <dt className="text-slate-600">Other deductions</dt>
                        <dd className="text-slate-700">−{kes(preview.data.other_deductions)}</dd>
                      </div>
                    )}
                    <div className="flex justify-between border-t border-slate-200 pt-2 text-base">
                      <dt className="font-medium text-slate-900">Net payable</dt>
                      <dd className="font-semibold text-money-700">{kes(preview.data.net_amount)}</dd>
                    </div>
                  </dl>

                  <div className="mt-4 flex items-center gap-2">
                    <Button
                      loading={create.isPending}
                      disabled={preview.data.net_amount <= 0}
                      icon={<Send className="h-4 w-4" />}
                      onClick={() => {
                        setError(null)
                        create.mutate()
                      }}
                    >
                      Create disbursement
                    </Button>
                    {preview.data.net_amount <= 0 && (
                      <span className="text-xs text-slate-500">
                        Nothing to pay out for this period.
                      </span>
                    )}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>All disbursements</CardTitle>
            </CardHeader>
            <CardBody>
              {disbursements.isPending ? (
                <p className="text-sm text-slate-500">Loading…</p>
              ) : rows.length === 0 ? (
                <p className="text-sm text-slate-500">No disbursements recorded yet.</p>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Reference</Th>
                      <Th>Owner</Th>
                      <Th>Period</Th>
                      <Th>Net</Th>
                      <Th>Status</Th>
                      <Th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <Td className="font-medium">{row.reference_code}</Td>
                        <Td>
                          <Link
                            to={`/agency/owners/${row.owner_profile_id}`}
                            className="text-brand-700 hover:underline"
                          >
                            {ownerName(row.owner_profile_id)}
                          </Link>
                        </Td>
                        <Td className="text-xs text-slate-500">
                          {shortDate(row.period_start)} – {shortDate(row.period_end)}
                        </Td>
                        <Td className="font-semibold text-money-700">{kes(row.net_amount)}</Td>
                        <Td>
                          <Badge tone={DISBURSEMENT_STATUS_TONE[row.status]}>
                            {humanize(row.status)}
                          </Badge>
                          {row.paid_at && (
                            <p className="mt-0.5 text-xs text-slate-400">{dateTime(row.paid_at)}</p>
                          )}
                          {(row.rejection_reason || row.failure_reason) && (
                            <p className="mt-0.5 max-w-[16rem] text-xs text-danger-600">
                              {row.rejection_reason ?? row.failure_reason}
                            </p>
                          )}
                        </Td>
                        <Td>
                          <div className="flex flex-wrap items-center justify-end gap-1.5">
                            {CAN_REVIEW.includes(row.status) && (
                              <>
                                <Button
                                  size="sm"
                                  loading={approve.isPending && approve.variables === row.id}
                                  icon={<ThumbsUp className="h-3.5 w-3.5" />}
                                  onClick={() => {
                                    setError(null)
                                    setNotice(null)
                                    approve.mutate(row.id)
                                  }}
                                >
                                  Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  icon={<XCircle className="h-3.5 w-3.5" />}
                                  onClick={() => {
                                    setError(null)
                                    setRejectFor(row)
                                  }}
                                >
                                  Reject
                                </Button>
                              </>
                            )}
                            {CAN_PAY.includes(row.status) && (
                              <>
                                <Button
                                  size="sm"
                                  loading={payViaMpesa.isPending && payViaMpesa.variables === row.id}
                                  icon={<Smartphone className="h-3.5 w-3.5" />}
                                  onClick={() => {
                                    setError(null)
                                    setNotice(null)
                                    payViaMpesa.mutate(row.id)
                                  }}
                                >
                                  Send M-Pesa
                                </Button>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                                  onClick={() => {
                                    setError(null)
                                    setPayFor(row)
                                  }}
                                >
                                  Record payout
                                </Button>
                              </>
                            )}
                            {row.status === 'completed' && (
                              <Button
                                size="sm"
                                variant="ghost"
                                loading={openStatement.isPending && openStatement.variables === row.id}
                                icon={<FileText className="h-3.5 w-3.5" />}
                                onClick={() => {
                                  setError(null)
                                  openStatement.mutate(row.id)
                                }}
                              >
                                Statement
                              </Button>
                            )}
                          </div>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardBody>
          </Card>
        </>
      )}

      <Dialog
        open={payFor !== null}
        onClose={() => setPayFor(null)}
        title="Record a payout made elsewhere"
        description={
          payFor
            ? `${kes(payFor.net_amount)} to ${ownerName(payFor.owner_profile_id)}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setPayFor(null)}>
              Cancel
            </Button>
            <Button
              loading={markPaid.isPending}
              disabled={!reference.trim()}
              onClick={() => payFor && markPaid.mutate(payFor.id)}
            >
              Mark as paid
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="How it was sent" required>
            <Select value={method} onChange={(event) => setMethod(event.target.value)}>
              <option value="bank_transfer">Bank transfer</option>
              <option value="mpesa">M-Pesa (sent manually)</option>
              <option value="cheque">Cheque</option>
              <option value="cash">Cash</option>
            </Select>
          </Field>
          <Field
            label="Transaction reference"
            required
            hint="The owner will see this on their statement, so use the real reference."
          >
            <Input
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="e.g. QGH7X8K2LM"
            />
          </Field>
        </div>
      </Dialog>

      <Dialog
        open={rejectFor !== null}
        onClose={() => setRejectFor(null)}
        title="Send this back"
        description={
          rejectFor
            ? `${rejectFor.reference_code} for ${ownerName(rejectFor.owner_profile_id)}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setRejectFor(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={reject.isPending}
              disabled={rejectReason.trim().length < 3}
              onClick={() => rejectFor && reject.mutate(rejectFor.id)}
            >
              Reject
            </Button>
          </>
        }
      >
        <Field
          label="Why is it being rejected?"
          required
          hint="Recorded on the audit trail so the next reviewer knows what to fix."
        >
          <Textarea
            rows={3}
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            placeholder="e.g. February maintenance invoice is still missing"
          />
        </Field>
      </Dialog>
    </div>
  )
}
