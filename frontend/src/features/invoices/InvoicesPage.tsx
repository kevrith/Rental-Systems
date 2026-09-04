import { useQuery } from '@tanstack/react-query'
import { Download, Receipt } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { invoicesApi, propertiesApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  INVOICE_STATUS_TONE,
  PageLoader,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

export function InvoicesPage() {
  const [status, setStatus] = useState('')
  const [propertyId, setPropertyId] = useState('')

  const properties = useQuery({
    queryKey: queryKeys.properties({ forInvoices: true }),
    queryFn: () => propertiesApi.list(),
  })

  const invoices = useQuery({
    queryKey: queryKeys.invoices({ status, propertyId }),
    queryFn: () =>
      invoicesApi.list({
        invoice_status: status || undefined,
        property_id: propertyId || undefined,
        limit: 200,
      }),
  })

  return (
    <div>
      <PageHeader
        title="Invoices"
        description="Raised automatically on each tenancy's billing day."
      />

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
          <option value="pending">Pending</option>
          <option value="partially_paid">Partially paid</option>
          <option value="overdue">Overdue</option>
          <option value="paid">Paid</option>
          <option value="cancelled">Cancelled</option>
        </Select>
      </div>

      <Card>
        {invoices.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : invoices.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Invoice</Th>
                <Th>Tenant</Th>
                <Th>Period</Th>
                <Th>Due</Th>
                <Th>Total</Th>
                <Th>Balance</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {invoices.data.map((invoice) => (
                <tr key={invoice.id} className="hover:bg-slate-50">
                  <Td>
                    <Link
                      to={`/invoices/${invoice.id}`}
                      className="font-mono text-xs font-medium text-brand-700 hover:underline"
                    >
                      {invoice.reference_code}
                    </Link>
                  </Td>
                  <Td>
                    {invoice.tenant_name}
                    <span className="block text-xs text-slate-400">
                      {invoice.property_name} · {invoice.unit_number}
                    </span>
                  </Td>
                  <Td className="text-slate-600">{shortDate(invoice.period_start)}</Td>
                  <Td className="text-slate-600">{shortDate(invoice.due_date)}</Td>
                  <Td className="font-medium">{kes(invoice.total)}</Td>
                  <Td>
                    <span
                      className={
                        Number(invoice.balance) > 0
                          ? 'font-medium text-danger-700'
                          : 'text-money-700'
                      }
                    >
                      {kes(invoice.balance)}
                    </span>
                  </Td>
                  <Td>
                    <Badge tone={INVOICE_STATUS_TONE[invoice.status] ?? 'neutral'}>
                      {humanize(invoice.status)}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<Receipt className="h-6 w-6" />}
            title="No invoices yet"
            description="Invoices are generated automatically on each tenancy's billing day."
          />
        )}
      </Card>
    </div>
  )
}

export function InvoiceDetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()

  const invoice = useQuery({
    queryKey: queryKeys.invoice(invoiceId!),
    queryFn: () => invoicesApi.get(invoiceId!),
    enabled: Boolean(invoiceId),
  })

  if (invoice.isPending) return <PageLoader />
  if (invoice.isError) {
    return (
      <Alert tone="danger" title="Could not load this invoice">
        {errorMessage(invoice.error)}
      </Alert>
    )
  }

  const record = invoice.data

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title={record.reference_code}
        description={`${record.tenant_name} · ${record.property_name} unit ${record.unit_number}`}
        backTo="/invoices"
        backLabel="All invoices"
        actions={
          record.document_url && (
            <a
              href={record.document_url}
              target="_blank"
              rel="noreferrer"
              className={linkButtonClass('outline')}
            >
              <Download className="h-4 w-4" />
              Download PDF
            </a>
          )
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>
            {shortDate(record.period_start)} – {shortDate(record.period_end)}
          </CardTitle>
          <Badge tone={INVOICE_STATUS_TONE[record.status] ?? 'neutral'}>
            {humanize(record.status)}
          </Badge>
        </CardHeader>

        <Table>
          <thead>
            <tr>
              <Th>Description</Th>
              <Th className="text-right">Qty</Th>
              <Th className="text-right">Rate</Th>
              <Th className="text-right">Amount</Th>
            </tr>
          </thead>
          <tbody>
            {record.line_items.map((item) => (
              <tr key={item.id}>
                <Td>
                  {item.description}
                  <Badge className="ml-2" tone={item.kind === 'arrears' ? 'danger' : 'neutral'}>
                    {humanize(item.kind)}
                  </Badge>
                </Td>
                <Td className="text-right text-slate-600">{Number(item.quantity)}</Td>
                <Td className="text-right text-slate-600">{kes(item.unit_amount)}</Td>
                <Td className="text-right font-medium">{kes(item.amount)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>

        <CardBody className="space-y-2 border-t border-slate-100 text-sm">
          <Row label="Total" value={kes(record.total)} />
          {Number(record.amount_paid) > 0 && (
            <Row label="Paid to date" value={`(${kes(record.amount_paid)})`} tone="money" />
          )}
          <Row
            label="Balance due"
            value={kes(record.balance)}
            bold
            tone={Number(record.balance) > 0 ? 'danger' : 'money'}
          />
          <p className="pt-2 text-xs text-slate-500">
            Issued {shortDate(record.issue_date)} · due {shortDate(record.due_date)}
          </p>
        </CardBody>
      </Card>
    </div>
  )
}

function Row({
  label,
  value,
  bold,
  tone,
}: {
  label: string
  value: string
  bold?: boolean
  tone?: 'money' | 'danger'
}) {
  const toneClass =
    tone === 'danger' ? 'text-danger-700' : tone === 'money' ? 'text-money-700' : 'text-slate-800'
  return (
    <div className="flex items-center justify-between">
      <span className={bold ? 'font-semibold text-slate-900' : 'text-slate-600'}>{label}</span>
      <span className={`${bold ? 'text-base font-semibold' : ''} ${toneClass}`}>{value}</span>
    </div>
  )
}
