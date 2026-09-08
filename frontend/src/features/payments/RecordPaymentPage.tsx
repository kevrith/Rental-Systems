import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Banknote,
  CheckCircle2,
  Clock,
  Download,
  Smartphone,
  XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { paymentsApi, tenanciesApi } from '@/api'
import type { PaymentDetail } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Select,
  Spinner,
  Tab,
  Tabs,
  Textarea,
  linkButtonClass,
} from '@/components/ui'
import { submitOrQueue } from '@/hooks/use-offline-queue'
import { errorMessage, kes, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

type Mode = 'mpesa' | 'manual'

export function RecordPaymentPage() {
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>('mpesa')
  const [tenancyId, setTenancyId] = useState(params.get('tenancy_id') ?? '')

  const tenancies = useQuery({
    queryKey: queryKeys.tenancies({ forPayment: true }),
    queryFn: () => tenanciesApi.list({ tenancy_status: 'active' }),
  })

  const selected = tenancies.data?.find((tenancy) => tenancy.id === tenancyId)

  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title="Record a payment" backTo="/payments" />

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Who is paying?</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <Field label="Tenancy" required>
            <Select value={tenancyId} onChange={(event) => setTenancyId(event.target.value)}>
              <option value="">Choose a tenancy</option>
              {tenancies.data?.map((tenancy) => (
                <option key={tenancy.id} value={tenancy.id}>
                  {tenancy.tenant_name} — {tenancy.property_name} unit {tenancy.unit_number}
                </option>
              ))}
            </Select>
          </Field>

          {selected && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
              <span className="text-slate-600">Outstanding balance</span>
              <span
                className={
                  Number(selected.balance) > 0
                    ? 'font-semibold text-danger-700'
                    : 'font-semibold text-money-700'
                }
              >
                {kes(selected.balance)}
              </span>
            </div>
          )}
        </CardBody>
      </Card>

      <Tabs value={mode} onChange={(value) => setMode(value as Mode)} className="mb-4">
        <Tab value="mpesa">M-Pesa prompt</Tab>
        <Tab value="manual">Cash or bank</Tab>
      </Tabs>

      {mode === 'mpesa' ? (
        <MpesaPanel tenancyId={tenancyId} suggested={selected?.balance} phone={selected?.tenant_phone} />
      ) : (
        <ManualPanel tenancyId={tenancyId} suggested={selected?.balance} />
      )}
    </div>
  )
}

/** STK Push: prompt the tenant's phone, then poll until Daraja answers (US-019). */
function MpesaPanel({
  tenancyId,
  suggested,
  phone,
}: {
  tenancyId: string
  suggested?: string
  phone?: string | null
}) {
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [paymentId, setPaymentId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (suggested && Number(suggested) > 0) setAmount(suggested)
  }, [suggested])

  useEffect(() => {
    if (phone) setPhoneNumber(phone)
  }, [phone])

  const push = useMutation({
    mutationFn: () =>
      paymentsApi.stkPush({
        tenancy_id: tenancyId,
        amount,
        phone_number: phoneNumber || undefined,
      }),
    onSuccess: (result) => {
      setError(null)
      setPaymentId(result.payment.id)
      setMessage(result.message)
    },
    onError: (pushError) => setError(errorMessage(pushError)),
  })

  // Daraja confirms asynchronously, so poll the payment until it settles. The
  // callback usually arrives within seconds; this is what the caretaker watches.
  const status = useQuery({
    queryKey: queryKeys.payment(paymentId ?? ''),
    queryFn: () => paymentsApi.status(paymentId!),
    enabled: Boolean(paymentId),
    refetchInterval: (query) => {
      const data = query.state.data as PaymentDetail | undefined
      return data && data.status !== 'pending' ? false : 4000
    },
  })

  useEffect(() => {
    if (status.data && status.data.status !== 'pending') {
      void queryClient.invalidateQueries({ queryKey: ['payments'] })
      void queryClient.invalidateQueries({ queryKey: ['tenancies'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    }
  }, [status.data, queryClient])

  if (paymentId && status.data) {
    return <PaymentOutcome payment={status.data} onReset={() => setPaymentId(null)} />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Smartphone className="h-4 w-4 text-money-600" />
          Send an M-Pesa prompt
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <Field label="Amount (KES)" required>
          <Input
            type="number"
            step="1"
            min="1"
            placeholder="25000"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>

        <Field
          label="Phone number"
          hint="Defaults to the tenant's registered number."
        >
          <Input
            type="tel"
            placeholder="0712 345 678"
            value={phoneNumber}
            onChange={(event) => setPhoneNumber(event.target.value)}
          />
        </Field>

        {message && !paymentId && <Alert tone="info">{message}</Alert>}
        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}

        {paymentId && !status.data && (
          <Alert tone="info" icon={<Spinner className="h-4 w-4" />}>
            {message ?? 'Waiting for the tenant to enter their M-Pesa PIN…'}
          </Alert>
        )}

        <Button
          className="w-full justify-center"
          disabled={!tenancyId || !amount}
          loading={push.isPending}
          onClick={() => {
            setError(null)
            push.mutate()
          }}
        >
          Send payment request
        </Button>
      </CardBody>
    </Card>
  )
}

function PaymentOutcome({ payment, onReset }: { payment: PaymentDetail; onReset: () => void }) {
  if (payment.status === 'pending') {
    return (
      <Card>
        <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
          <Clock className="h-10 w-10 text-warn-500" />
          <p className="font-medium text-slate-900">Waiting for the tenant</p>
          <p className="max-w-sm text-sm text-slate-500">
            The M-Pesa prompt is on their phone. This page updates the moment they enter their PIN.
          </p>
          <Spinner className="mt-1" />
        </CardBody>
      </Card>
    )
  }

  const confirmed = payment.status === 'confirmed'

  return (
    <Card>
      <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
        {confirmed ? (
          <CheckCircle2 className="h-10 w-10 text-money-600" />
        ) : (
          <XCircle className="h-10 w-10 text-danger-600" />
        )}
        <p className="text-lg font-semibold text-slate-900">
          {confirmed ? `${kes(payment.amount)} received` : `Payment ${payment.status}`}
        </p>
        <p className="max-w-sm text-sm text-slate-500">
          {confirmed
            ? `M-Pesa reference ${payment.mpesa_receipt}. The receipt has been sent to the tenant on WhatsApp and SMS.`
            : (payment.failure_reason ?? 'The tenant did not complete the payment.')}
        </p>

        <div className="mt-2 flex flex-wrap justify-center gap-2">
          {payment.receipt_url && (
            <a
              href={payment.receipt_url}
              target="_blank"
              rel="noreferrer"
              className={linkButtonClass('outline')}
            >
              <Download className="h-4 w-4" />
              Download receipt
            </a>
          )}
          <Button variant={confirmed ? 'ghost' : 'primary'} onClick={onReset}>
            {confirmed ? 'Record another' : 'Try again'}
          </Button>
          <Link to="/payments" className={linkButtonClass('ghost')}>
            All payments
          </Link>
        </div>
      </CardBody>
    </Card>
  )
}

/** Cash, bank transfer or cheque collected off-platform (US-020). */
function ManualPanel({ tenancyId, suggested }: { tenancyId: string; suggested?: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('cash')
  const [paymentDate, setPaymentDate] = useState(today())
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [queued, setQueued] = useState(false)

  useEffect(() => {
    if (suggested && Number(suggested) > 0) setAmount(suggested)
  }, [suggested])

  const record = useMutation({
    mutationFn: async () => {
      const body = {
        tenancy_id: tenancyId,
        amount,
        payment_date: paymentDate,
        method,
        reference: reference || null,
        notes: notes || null,
      }
      // Caretakers collect cash in places with no signal — never lose the entry.
      return submitOrQueue({
        run: () => paymentsApi.record(body),
        method: 'POST',
        url: '/payments',
        body,
        label: `Payment of ${kes(amount)}`,
      })
    },
    onSuccess: async (result) => {
      if (result.queued) {
        setQueued(true)
        return
      }
      await queryClient.invalidateQueries({ queryKey: ['payments'] })
      await queryClient.invalidateQueries({ queryKey: ['tenancies'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      navigate(`/payments/${result.data!.id}`)
    },
    onError: (recordError) => setError(errorMessage(recordError)),
  })

  if (queued) {
    return (
      <Card>
        <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
          <Clock className="h-10 w-10 text-warn-500" />
          <p className="font-medium text-slate-900">Saved on this device</p>
          <p className="max-w-sm text-sm text-slate-500">
            You are offline. This payment of {kes(amount)} is queued and will be sent — with the
            tenant&apos;s receipt — as soon as you reconnect.
          </p>
          <Link to="/payments" className={linkButtonClass('outline')}>
            Back to payments
          </Link>
        </CardBody>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Banknote className="h-4 w-4 text-slate-500" />
          Record money already collected
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Amount (KES)" required>
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="25000"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
          <Field label="Method" required>
            <Select value={method} onChange={(event) => setMethod(event.target.value)}>
              <option value="cash">Cash</option>
              <option value="bank_transfer">Bank transfer</option>
              <option value="cheque">Cheque</option>
              <option value="mpesa">M-Pesa (paid directly)</option>
            </Select>
          </Field>
          <Field label="Date received" required>
            <Input
              type="date"
              max={today()}
              value={paymentDate}
              onChange={(event) => setPaymentDate(event.target.value)}
            />
          </Field>
          <Field
            label="Reference"
            hint={method === 'mpesa' ? 'The M-Pesa code from the tenant.' : 'Optional.'}
          >
            <Input
              placeholder={method === 'mpesa' ? 'SLK7RT91XZ' : 'Slip number'}
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            />
          </Field>
        </div>

        <Field label="Notes">
          <Textarea
            placeholder="Collected at the gate on Saturday morning."
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>

        <Alert tone="info">
          The tenant gets an instant WhatsApp and SMS confirmation naming you as the person who
          recorded it, plus a signed PDF receipt.
        </Alert>

        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}

        <Button
          className="w-full justify-center"
          disabled={!tenancyId || !amount}
          loading={record.isPending}
          onClick={() => {
            setError(null)
            record.mutate()
          }}
        >
          Record payment
        </Button>
      </CardBody>
    </Card>
  )
}
