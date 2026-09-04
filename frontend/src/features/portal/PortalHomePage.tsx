import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  Home,
  LogOut,
  Smartphone,
  XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { portalApi } from '@/api'
import type { PaymentDetail } from '@/api/types'
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
  INVOICE_STATUS_TONE,
  Input,
  PageLoader,
  Skeleton,
  Spinner,
  Textarea,
  linkButtonClass,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

export function PortalHomePage() {
  const [payOpen, setPayOpen] = useState(false)
  const [vacateOpen, setVacateOpen] = useState(false)

  const home = useQuery({ queryKey: queryKeys.portalHome, queryFn: portalApi.home })
  const invoices = useQuery({ queryKey: queryKeys.portalInvoices, queryFn: portalApi.invoices })

  if (home.isPending) return <PageLoader />
  if (home.isError) {
    return (
      <Alert tone="danger" title="Could not load your portal">
        {errorMessage(home.error)}
      </Alert>
    )
  }

  const data = home.data
  const owing = Number(data.balance) > 0

  if (!data.tenancy_id) {
    return (
      <Card>
        <CardBody className="flex flex-col items-center gap-2 py-12 text-center">
          <Home className="h-8 w-8 text-slate-300" />
          <p className="font-medium text-slate-900">No active tenancy</p>
          <p className="max-w-sm text-sm text-slate-500">
            Your tenancy with {data.organization_name} has ended. You can still download your past
            documents and receipts.
          </p>
          <Link to="/portal/documents" className={`${linkButtonClass('outline')} mt-2`}>
            View my documents
          </Link>
        </CardBody>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      {/* Balance is the first thing a tenant opens this app to see. */}
      <Card className={owing ? 'border-danger-100' : 'border-money-100'}>
        <CardBody className="text-center">
          <p className="text-sm text-slate-500">
            {owing ? 'You currently owe' : 'Your balance'}
          </p>
          <p
            className={`mt-1 text-4xl font-semibold tracking-tight ${
              owing ? 'text-danger-700' : 'text-money-700'
            }`}
          >
            {kes(data.balance)}
          </p>
          {data.next_due_date && owing && (
            <p className="mt-1 flex items-center justify-center gap-1.5 text-sm text-slate-500">
              <CalendarClock className="h-4 w-4" />
              Due {shortDate(data.next_due_date)}
            </p>
          )}
          {!owing && (
            <p className="mt-1 flex items-center justify-center gap-1.5 text-sm text-money-700">
              <CheckCircle2 className="h-4 w-4" />
              You are fully paid up
            </p>
          )}

          <Button
            size="lg"
            variant={owing ? 'success' : 'outline'}
            className="mt-4 w-full justify-center"
            icon={<Smartphone className="h-5 w-5" />}
            onClick={() => setPayOpen(true)}
          >
            Pay rent with M-Pesa
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your home</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3 text-sm">
          <Row label="Property" value={data.property_name ?? '—'} />
          <Row label="Unit" value={data.unit_number ?? '—'} />
          <Row label="Monthly rent" value={data.monthly_rent ? kes(data.monthly_rent) : '—'} />
          <Row
            label="Lease ends"
            value={data.lease_end_date ? shortDate(data.lease_end_date) : 'Open-ended'}
          />
          <Row label="Managed by" value={data.organization_name} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent invoices</CardTitle>
          <Link to="/portal/payments" className="text-sm text-brand-600 hover:underline">
            Payment history
          </Link>
        </CardHeader>
        {invoices.isPending ? (
          <CardBody className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </CardBody>
        ) : invoices.data?.length ? (
          <ul className="divide-y divide-slate-100">
            {invoices.data.slice(0, 5).map((invoice) => (
              <li key={invoice.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">
                    {shortDate(invoice.period_start)}
                  </p>
                  <p className="text-xs text-slate-500">
                    {invoice.reference_code} · due {shortDate(invoice.due_date)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium">{kes(invoice.total)}</p>
                  <Badge tone={INVOICE_STATUS_TONE[invoice.status] ?? 'neutral'}>
                    {humanize(invoice.status)}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <CardBody>
            <p className="text-sm text-slate-500">No invoices have been issued yet.</p>
          </CardBody>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Link
          to="/portal/documents"
          className="flex flex-col items-center gap-1.5 rounded-card border border-slate-200 bg-white px-3 py-4 text-center text-xs font-medium text-slate-700 shadow-sm hover:border-brand-300"
        >
          <FileText className="h-5 w-5 text-brand-600" />
          My documents
        </Link>
        <button
          type="button"
          onClick={() => setVacateOpen(true)}
          className="flex flex-col items-center gap-1.5 rounded-card border border-slate-200 bg-white px-3 py-4 text-center text-xs font-medium text-slate-700 shadow-sm hover:border-brand-300"
        >
          <LogOut className="h-5 w-5 text-slate-400" />
          Give notice
        </button>
      </div>

      <PayDialog
        open={payOpen}
        onClose={() => setPayOpen(false)}
        balance={data.balance}
        phone={data.phone_number}
      />
      <VacateDialog open={vacateOpen} onClose={() => setVacateOpen(false)} />
    </div>
  )
}

/** Two taps to an M-Pesa prompt (US-029). */
function PayDialog({
  open,
  onClose,
  balance,
  phone,
}: {
  open: boolean
  onClose: () => void
  balance: string
  phone: string
}) {
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState(balance)
  const [paymentId, setPaymentId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setAmount(Number(balance) > 0 ? balance : '')
      setPaymentId(null)
      setError(null)
    }
  }, [open, balance])

  const pay = useMutation({
    mutationFn: () => portalApi.pay({ amount }),
    onSuccess: (result) => setPaymentId(result.payment_id),
    onError: (payError) => setError(errorMessage(payError)),
  })

  const status = useQuery({
    queryKey: ['portal', 'payment', paymentId],
    queryFn: () => portalApi.paymentStatus(paymentId!),
    enabled: Boolean(paymentId),
    refetchInterval: (query) => {
      const data = query.state.data as PaymentDetail | undefined
      return data && data.status !== 'pending' ? false : 4000
    },
  })

  useEffect(() => {
    if (status.data && status.data.status !== 'pending') {
      void queryClient.invalidateQueries({ queryKey: ['portal'] })
    }
  }, [status.data, queryClient])

  const settled = status.data && status.data.status !== 'pending'
  const confirmed = status.data?.status === 'confirmed'

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={settled ? (confirmed ? 'Payment received' : 'Payment not completed') : 'Pay your rent'}
      footer={
        settled ? (
          <Button onClick={onClose}>Done</Button>
        ) : paymentId ? (
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="success"
              disabled={!amount || Number(amount) <= 0}
              loading={pay.isPending}
              onClick={() => {
                setError(null)
                pay.mutate()
              }}
            >
              Send M-Pesa prompt
            </Button>
          </>
        )
      }
    >
      {settled ? (
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          {confirmed ? (
            <CheckCircle2 className="h-10 w-10 text-money-600" />
          ) : (
            <XCircle className="h-10 w-10 text-danger-600" />
          )}
          <p className="text-lg font-semibold text-slate-900">
            {confirmed ? kes(status.data!.amount) : humanize(status.data!.status)}
          </p>
          <p className="text-sm text-slate-500">
            {confirmed
              ? `Thank you. Your receipt ${status.data!.receipt?.reference_code ?? ''} has been sent to you on WhatsApp.`
              : (status.data!.failure_reason ?? 'The payment was not completed.')}
          </p>
          {status.data?.receipt_url && (
            <a
              href={status.data.receipt_url}
              target="_blank"
              rel="noreferrer"
              className={linkButtonClass('outline')}
            >
              <Download className="h-4 w-4" />
              Download receipt
            </a>
          )}
        </div>
      ) : paymentId ? (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <Clock className="h-10 w-10 text-warn-500" />
          <p className="font-medium text-slate-900">Check your phone</p>
          <p className="max-w-xs text-sm text-slate-500">
            An M-Pesa request has been sent to {phone}. Enter your PIN to complete the payment.
          </p>
          <Spinner />
        </div>
      ) : (
        <div className="space-y-4">
          <Field label="Amount to pay (KES)" required>
            <Input
              type="number"
              step="1"
              min="1"
              inputMode="numeric"
              className="text-lg"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>

          {Number(balance) > 0 && (
            <button
              type="button"
              onClick={() => setAmount(balance)}
              className="text-sm text-brand-600 hover:underline"
            >
              Pay the full balance of {kes(balance)}
            </button>
          )}

          <Alert tone="info" icon={<Smartphone className="h-4 w-4" />}>
            The prompt goes to {phone}. Your receipt arrives on WhatsApp within seconds of payment.
          </Alert>

          {error && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              {error}
            </Alert>
          )}
        </div>
      )}
    </Dialog>
  )
}

/** Digital notice to vacate (US-033). */
function VacateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [moveOutDate, setMoveOutDate] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const submit = useMutation({
    mutationFn: () =>
      portalApi.vacateNotice({ move_out_date: moveOutDate, reason: reason || undefined }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['portal'] })
      setDone(true)
    },
    onError: (submitError) => setError(errorMessage(submitError)),
  })

  const close = () => {
    setDone(false)
    setMoveOutDate('')
    setReason('')
    setError(null)
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title={done ? 'Notice submitted' : 'Give notice to vacate'}
      description={done ? undefined : 'Your landlord is notified immediately.'}
      footer={
        done ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              disabled={!moveOutDate}
              loading={submit.isPending}
              onClick={() => {
                setError(null)
                submit.mutate()
              }}
            >
              Submit notice
            </Button>
          </>
        )
      }
    >
      {done ? (
        <Alert tone="success" icon={<CheckCircle2 className="h-4 w-4" />}>
          Your notice has been recorded and a copy filed in your documents. A move-out inspection
          will be arranged before you leave.
        </Alert>
      ) : (
        <div className="space-y-4">
          <Field label="Intended move-out date" required>
            <Input
              type="date"
              value={moveOutDate}
              onChange={(event) => setMoveOutDate(event.target.value)}
            />
          </Field>
          <Field label="Reason (optional)">
            <Textarea
              placeholder="Relocating for work."
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
          <Alert tone="warn">
            Your lease sets a required notice period. Giving less notice may affect your deposit
            refund — your landlord will be shown how many days you gave.
          </Alert>
          {error && <Alert tone="danger">{error}</Alert>}
        </div>
      )}
    </Dialog>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">{value}</span>
    </div>
  )
}
