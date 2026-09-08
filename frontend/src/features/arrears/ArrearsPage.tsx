import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, Download, Eye, FileWarning, Send } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { arrearsApi, demandLettersApi, propertiesApi } from '@/api'
import type { AgingBuckets } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { API_BASE_URL } from '@/lib/api-client'
import { cn } from '@/lib/cn'
import { errorMessage, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

/** Colour-coded aging buckets (US-022) — the further right, the more urgent. */
const BUCKETS: { key: keyof AgingBuckets; label: string; className: string }[] = [
  { key: 'current', label: 'Current', className: 'bg-slate-100 text-slate-700' },
  { key: 'days_1_30', label: '1–30 days', className: 'bg-warn-50 text-warn-700' },
  { key: 'days_31_60', label: '31–60 days', className: 'bg-warn-100 text-warn-700' },
  { key: 'days_61_90', label: '61–90 days', className: 'bg-danger-50 text-danger-700' },
  { key: 'days_90_plus', label: '90+ days', className: 'bg-danger-100 text-danger-700' },
]

const BUCKET_TONE: Record<string, 'neutral' | 'warn' | 'danger'> = {
  current: 'neutral',
  days_1_30: 'warn',
  days_31_60: 'warn',
  days_61_90: 'danger',
  days_90_plus: 'danger',
}

export function ArrearsPage() {
  const [propertyId, setPropertyId] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const canRemind = useAuthStore((state) => state.user?.permissions?.includes('arrears:view'))

  const properties = useQuery({
    queryKey: queryKeys.properties({ forArrears: true }),
    queryFn: () => propertiesApi.list(),
  })

  const report = useQuery({
    queryKey: queryKeys.arrears({ propertyId }),
    queryFn: () => arrearsApi.report({ property_id: propertyId || undefined }),
  })

  const remind = useMutation({
    mutationFn: (tenancyIds: string[]) =>
      arrearsApi.remind({
        tenancy_ids: tenancyIds,
        property_id: propertyId || undefined,
      }),
    onSuccess: (result) => {
      setNotice({ tone: 'success', text: result.message })
      setSelected([])
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const issueLetter = useMutation({
    mutationFn: (tenancyId: string) => demandLettersApi.issue(tenancyId),
    onSuccess: (letter) => {
      setNotice({
        tone: 'success',
        text: `${letter.escalation} issued for ${kes(letter.total_owed)} — the tenant has until ${shortDate(letter.deadline)} and a copy is in their document vault.`,
      })
      window.open(letter.url, '_blank', 'noopener,noreferrer')
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  /** Renders the letter without filing or sending it, so it can be read first. */
  const previewLetter = useMutation({
    mutationFn: async (tenancyId: string) => {
      const blob = await demandLettersApi.preview(tenancyId)
      return URL.createObjectURL(blob)
    },
    onSuccess: (url) => {
      window.open(url, '_blank', 'noopener,noreferrer')
      // The tab has the bytes now; releasing the handle keeps memory honest.
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  if (report.isPending) return <PageLoader />
  if (report.isError) {
    return (
      <Alert tone="danger" title="Could not load the arrears report">
        {errorMessage(report.error)}
      </Alert>
    )
  }

  const data = report.data
  const allSelected = data.rows.length > 0 && selected.length === data.rows.length

  const exportParams = new URLSearchParams()
  if (propertyId) exportParams.set('property_id', propertyId)

  return (
    <div>
      <PageHeader
        title="Arrears"
        description="Who owes what, and for how long."
        actions={
          <>
            <a
              href={`${API_BASE_URL}${arrearsApi.exportCsvUrl}?${exportParams.toString()}`}
              className={linkButtonClass('outline')}
            >
              <Download className="h-4 w-4" />
              Export CSV
            </a>
            {canRemind && data.rows.length > 0 && (
              <Button
                icon={<Send className="h-4 w-4" />}
                loading={remind.isPending}
                onClick={() => remind.mutate(selected)}
              >
                {selected.length > 0
                  ? `Remind ${selected.length} tenant(s)`
                  : `Remind all ${data.tenants_in_arrears}`}
              </Button>
            )}
          </>
        }
      />

      {notice && (
        <Alert tone={notice.tone} className="mb-5">
          {notice.text}
        </Alert>
      )}

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total arrears"
          value={kes(data.total_arrears, { compact: true })}
          tone={Number(data.total_arrears) > 0 ? 'danger' : 'success'}
        />
        <StatCard label="Tenants behind" value={String(data.tenants_in_arrears)} />
        <StatCard
          label="Over 60 days"
          value={kes(
            Number(data.aging.days_61_90) + Number(data.aging.days_90_plus),
            { compact: true },
          )}
          tone="danger"
        />
        <StatCard
          label="Within 30 days"
          value={kes(data.aging.days_1_30, { compact: true })}
          tone="warn"
        />
      </div>

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Aging analysis</CardTitle>
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
        </CardHeader>
        <CardBody>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
            {BUCKETS.map((bucket) => (
              <div key={bucket.key} className={cn('rounded-lg p-3', bucket.className)}>
                <p className="text-xs font-medium">{bucket.label}</p>
                <p className="mt-1 text-lg font-semibold">
                  {kes(data.aging[bucket.key], { compact: true })}
                </p>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Defaulters</CardTitle>
          {data.rows.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                className="h-4 w-4 accent-brand-600"
                checked={allSelected}
                onChange={(event) =>
                  setSelected(event.target.checked ? data.rows.map((row) => row.tenancy_id) : [])
                }
              />
              Select all
            </label>
          )}
        </CardHeader>

        {data.rows.length ? (
          <Table>
            <thead>
              <tr>
                <Th className="w-10" />
                <Th>Tenant</Th>
                <Th>Unit</Th>
                <Th>Owed</Th>
                <Th>Overdue</Th>
                <Th>Last payment</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.tenancy_id} className="hover:bg-slate-50">
                  <Td>
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand-600"
                      checked={selected.includes(row.tenancy_id)}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, row.tenancy_id]
                            : current.filter((id) => id !== row.tenancy_id),
                        )
                      }
                      aria-label={`Select ${row.tenant_name}`}
                    />
                  </Td>
                  <Td>
                    <Link
                      to={`/tenants/${row.tenant_id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {row.tenant_name}
                    </Link>
                    <span className="block text-xs text-slate-400">{row.tenant_phone}</span>
                  </Td>
                  <Td className="text-slate-600">
                    {row.unit_number}
                    <span className="block text-xs text-slate-400">{row.property_name}</span>
                  </Td>
                  <Td className="font-semibold text-danger-700">{kes(row.amount_owed)}</Td>
                  <Td>
                    <Badge tone={BUCKET_TONE[row.bucket] ?? 'neutral'}>
                      {row.days_overdue} days
                    </Badge>
                    <span className="mt-0.5 block text-xs text-slate-400">
                      {row.invoice_count} invoice(s)
                    </span>
                  </Td>
                  <Td className="text-slate-600">
                    {row.last_payment_date ? shortDate(row.last_payment_date) : 'Never'}
                  </Td>
                  <Td>
                    {/* A formal demand is the document the Rent Restriction
                        Tribunal expects to have been served first, so it is
                        offered from 60 days rather than buried in a menu. */}
                    {row.days_overdue >= 60 && (
                      <div className="flex flex-wrap justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={previewLetter.isPending && previewLetter.variables === row.tenancy_id}
                          icon={<Eye className="h-3.5 w-3.5" />}
                          onClick={() => previewLetter.mutate(row.tenancy_id)}
                        >
                          Preview
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={issueLetter.isPending && issueLetter.variables === row.tenancy_id}
                          icon={<FileWarning className="h-3.5 w-3.5" />}
                          onClick={() => issueLetter.mutate(row.tenancy_id)}
                        >
                          Demand letter
                        </Button>
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<CheckCircle2 className="h-6 w-6" />}
            title="Nobody is in arrears"
            description="Every tenant is up to date. Nicely done."
          />
        )}
      </Card>
    </div>
  )
}
