import { useQuery } from '@tanstack/react-query'
import { CreditCard, Download, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { paymentsApi, propertiesApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import { PendingApprovalPanel } from '@/features/payments/PendingApprovalPanel'
import {
  Badge,
  Card,
  EmptyState,
  PAYMENT_STATUS_TONE,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { dateTime, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function PaymentsPage() {
  const [params] = useSearchParams()
  const [status, setStatus] = useState('')
  const [propertyId, setPropertyId] = useState('')
  const tenancyId = params.get('tenancy_id') ?? undefined
  const canRecord = useAuthStore((state) => state.user?.permissions?.includes('payment:record'))

  const properties = useQuery({
    queryKey: queryKeys.properties({ forPayments: true }),
    queryFn: () => propertiesApi.list(),
  })

  const payments = useQuery({
    queryKey: queryKeys.payments({ status, propertyId, tenancyId }),
    queryFn: () =>
      paymentsApi.list({
        payment_status: status || undefined,
        property_id: propertyId || undefined,
        tenancy_id: tenancyId,
        limit: 200,
      }),
  })

  return (
    <div>
      <PageHeader
        title="Payments"
        description="Every rent payment, however it was collected."
        actions={
          canRecord && (
            <>
              <Link to="/payments/bank-statements" className={linkButtonClass('outline')}>
                Bank reconciliation
              </Link>
              <Link to="/payments/new" className={linkButtonClass()}>
                <Plus className="h-4 w-4" />
                Record payment
              </Link>
            </>
          )
        }
      />

      {/* Held cash first: it is money the books do not yet know about. */}
      <PendingApprovalPanel />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select
          className="w-auto min-w-40"
          value={propertyId}
          onChange={(event) => setPropertyId(event.target.value)}
        >
          <option value="">All properties</option>
          {properties.data?.map((property) => (
            <option key={property.id} value={property.id}>
              {property.name}
            </option>
          ))}
        </Select>
        <Select
          className="w-auto min-w-36"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="">Any status</option>
          <option value="confirmed">Confirmed</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </Select>
      </div>

      <Card>
        {payments.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : payments.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Reference</Th>
                <Th>Tenant</Th>
                <Th>Amount</Th>
                <Th>Method</Th>
                <Th>Date</Th>
                <Th>Status</Th>
                <Th>Receipt</Th>
              </tr>
            </thead>
            <tbody>
              {payments.data.map((payment) => (
                <tr key={payment.id} className="hover:bg-slate-50">
                  <Td>
                    <Link
                      to={`/payments/${payment.id}`}
                      className="font-mono text-xs font-medium text-brand-700 hover:underline"
                    >
                      {payment.reference_code}
                    </Link>
                    {payment.mpesa_receipt && (
                      <span className="block font-mono text-[11px] text-slate-400">
                        {payment.mpesa_receipt}
                      </span>
                    )}
                  </Td>
                  <Td>
                    {payment.tenant_name}
                    <span className="block text-xs text-slate-400">
                      {payment.property_name} · {payment.unit_number}
                    </span>
                  </Td>
                  <Td className="font-medium">{kes(payment.amount)}</Td>
                  <Td className="text-slate-600">{humanize(payment.method)}</Td>
                  <Td className="text-slate-600">
                    {payment.paid_at ? dateTime(payment.paid_at) : '—'}
                  </Td>
                  <Td>
                    <Badge tone={PAYMENT_STATUS_TONE[payment.status] ?? 'neutral'}>
                      {humanize(payment.status)}
                    </Badge>
                    {payment.failure_reason && (
                      <span className="mt-0.5 block max-w-40 truncate text-xs text-danger-600">
                        {payment.failure_reason}
                      </span>
                    )}
                  </Td>
                  <Td>
                    {payment.receipt_url ? (
                      <a
                        href={payment.receipt_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
                      >
                        <Download className="h-3.5 w-3.5" />
                        {payment.receipt?.reference_code}
                      </a>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<CreditCard className="h-6 w-6" />}
            title="No payments yet"
            description="Record a cash payment, or send an M-Pesa prompt to a tenant."
            action={
              canRecord ? (
                <Link to="/payments/new" className={linkButtonClass()}>
                  <Plus className="h-4 w-4" />
                  Record a payment
                </Link>
              ) : undefined
            }
          />
        )}
      </Card>
    </div>
  )
}
