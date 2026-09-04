import { useQuery } from '@tanstack/react-query'
import { Download, ShieldCheck } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { paymentsApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  PAYMENT_STATUS_TONE,
  PageLoader,
  linkButtonClass,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

export function PaymentDetailPage() {
  const { paymentId } = useParams<{ paymentId: string }>()

  const payment = useQuery({
    queryKey: queryKeys.payment(paymentId!),
    queryFn: () => paymentsApi.get(paymentId!),
    enabled: Boolean(paymentId),
  })

  if (payment.isPending) return <PageLoader />
  if (payment.isError) {
    return (
      <Alert tone="danger" title="Could not load this payment">
        {errorMessage(payment.error)}
      </Alert>
    )
  }

  const record = payment.data

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title={kes(record.amount)}
        description={`${record.reference_code} · ${humanize(record.method)}`}
        backTo="/payments"
        backLabel="All payments"
        actions={
          record.receipt_url && (
            <a
              href={record.receipt_url}
              target="_blank"
              rel="noreferrer"
              className={linkButtonClass()}
            >
              <Download className="h-4 w-4" />
              Download receipt
            </a>
          )
        }
      />

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>Payment</CardTitle>
            <Badge tone={PAYMENT_STATUS_TONE[record.status] ?? 'neutral'}>
              {humanize(record.status)}
            </Badge>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Detail label="Amount" value={kes(record.amount)} />
            <Detail label="Method" value={humanize(record.method)} />
            <Detail label="Date received" value={shortDate(record.payment_date)} />
            <Detail label="Confirmed at" value={record.paid_at ? dateTime(record.paid_at) : '—'} />
            {record.mpesa_receipt && (
              <Detail label="M-Pesa reference" value={record.mpesa_receipt} />
            )}
            {record.phone_number && <Detail label="Paid from" value={record.phone_number} />}
            {record.recorded_by_name && (
              <Detail label="Recorded by" value={record.recorded_by_name} />
            )}
          </CardBody>
        </Card>

        {record.failure_reason && (
          <Alert tone="danger" title="This payment did not complete">
            {record.failure_reason}
          </Alert>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Applied to</CardTitle>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Detail label="Tenant" value={record.tenant_name ?? '—'} />
            <Detail
              label="Unit"
              value={`${record.property_name ?? ''}${record.unit_number ? ` · ${record.unit_number}` : ''}`}
            />
          </CardBody>
        </Card>

        {record.receipt && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-money-600" />
                Receipt
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="grid gap-4 sm:grid-cols-2">
                <Detail label="Receipt number" value={record.receipt.reference_code} />
                <Detail label="Issued" value={dateTime(record.receipt.issued_at)} />
                <Detail
                  label="Balance after payment"
                  value={kes(record.receipt.balance_after)}
                />
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Verification code</p>
                <p className="mt-0.5 break-all font-mono text-xs text-slate-700">
                  {record.receipt.signature}
                </p>
                <p className="mt-1.5 text-xs text-slate-500">
                  This receipt is cryptographically signed. Any alteration to the PDF invalidates
                  the code above.
                </p>
              </div>
            </CardBody>
          </Card>
        )}
      </div>
    </div>
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
