import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import type { OrgDetail } from '@/api/types'
import { Badge, EmptyState, PageLoader, Table, Td, Th } from '@/components/ui'
import { amount, humanize, relative, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

type DrawerTab = 'units' | 'tenants' | 'payments' | 'demo'

const STATUS_TONE: Record<string, 'neutral' | 'success' | 'warn' | 'danger' | 'info'> = {
  vacant: 'warn',
  occupied: 'success',
  under_maintenance: 'danger',
  reserved: 'info',
  vacating: 'warn',
  confirmed: 'success',
  pending: 'warn',
  failed: 'danger',
  cancelled: 'neutral',
  reversed: 'neutral',
}

export function OrgDetailDrawer({ org, onClose }: { org: OrgDetail; onClose: () => void }) {
  const [tab, setTab] = useState<DrawerTab>('units')

  return (
    <div className="fixed inset-0 z-50 flex justify-end" aria-modal role="dialog">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      {/* Panel */}
      <div className="relative flex h-full w-full max-w-3xl flex-col bg-white shadow-2xl dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-4 dark:border-slate-700">
          <div>
            <p className="text-base font-semibold text-slate-900 dark:text-white">{org.name}</p>
            <p className="mt-0.5 font-mono text-xs text-slate-400">{org.id}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-slate-200 px-6 dark:border-slate-700">
          {(['units', 'tenants', 'payments', 'demo'] as DrawerTab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                tab === t
                  ? 'border-brand-600 text-brand-700 dark:border-brand-400 dark:text-brand-300'
                  : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {t === 'demo' ? 'Demo data' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {tab === 'units' && <UnitsPane orgId={org.id} />}
          {tab === 'tenants' && <TenantsPane orgId={org.id} />}
          {tab === 'payments' && <PaymentsPane orgId={org.id} />}
          {tab === 'demo' && <DemoPane orgId={org.id} />}
        </div>
      </div>
    </div>
  )
}

function UnitsPane({ orgId }: { orgId: string }) {
  const q = useQuery({
    queryKey: queryKeys.internalOrgUnits(orgId),
    queryFn: () => internalApi.orgUnits(orgId),
  })
  if (q.isPending) return <PageLoader />
  if (!q.data?.length) return <EmptyState title="No units" description="This org has no units yet." />
  return (
    <Table>
      <thead>
        <tr>
          <Th>Unit</Th>
          <Th>Property</Th>
          <Th>Type</Th>
          <Th>Rent</Th>
          <Th>Status</Th>
          <Th>Added</Th>
        </tr>
      </thead>
      <tbody>
        {q.data.map((u) => (
          <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
            <Td className="font-medium text-slate-900 dark:text-slate-100">{u.unit_number}</Td>
            <Td className="text-sm text-slate-600 dark:text-slate-400">{u.property_name ?? '—'}</Td>
            <Td className="text-sm text-slate-500">{u.unit_type ?? '—'}{u.bedrooms ? ` · ${u.bedrooms}br` : ''}</Td>
            <Td className="tabular-nums text-slate-700 dark:text-slate-300">{amount(Number(u.monthly_rent))}</Td>
            <Td><Badge tone={STATUS_TONE[u.status] ?? 'neutral'}>{humanize(u.status)}</Badge></Td>
            <Td className="text-xs text-slate-400">{shortDate(u.created_at)}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}

function TenantsPane({ orgId }: { orgId: string }) {
  const q = useQuery({
    queryKey: queryKeys.internalOrgTenants(orgId),
    queryFn: () => internalApi.orgTenants(orgId),
  })
  if (q.isPending) return <PageLoader />
  if (!q.data?.length) return <EmptyState title="No tenants" description="This org has no tenants yet." />
  return (
    <Table>
      <thead>
        <tr>
          <Th>Name</Th>
          <Th>Phone</Th>
          <Th>Email</Th>
          <Th>Added</Th>
        </tr>
      </thead>
      <tbody>
        {q.data.map((t) => (
          <tr key={t.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
            <Td className="font-medium text-slate-900 dark:text-slate-100">{t.full_name}</Td>
            <Td className="text-sm text-slate-600 dark:text-slate-400">{t.phone_number}</Td>
            <Td className="text-sm text-slate-500">{t.email ?? '—'}</Td>
            <Td className="text-xs text-slate-400">{shortDate(t.created_at)}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}

function PaymentsPane({ orgId }: { orgId: string }) {
  const q = useQuery({
    queryKey: queryKeys.internalOrgPayments(orgId),
    queryFn: () => internalApi.orgPayments(orgId),
  })
  if (q.isPending) return <PageLoader />
  if (!q.data?.length) return <EmptyState title="No payments" description="This org has no payments yet." />
  return (
    <Table>
      <thead>
        <tr>
          <Th>Reference</Th>
          <Th>Amount</Th>
          <Th>Method</Th>
          <Th>Status</Th>
          <Th>Paid</Th>
        </tr>
      </thead>
      <tbody>
        {q.data.map((p) => (
          <tr key={p.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
            <Td className="font-mono text-xs text-slate-500">{p.reference_code}</Td>
            <Td className="tabular-nums font-medium text-slate-900 dark:text-slate-100">{amount(Number(p.amount))}</Td>
            <Td className="text-sm text-slate-600 dark:text-slate-400">{humanize(p.method)}</Td>
            <Td><Badge tone={STATUS_TONE[p.status] ?? 'neutral'}>{humanize(p.status)}</Badge></Td>
            <Td className="text-xs text-slate-400">{p.paid_at ? relative(p.paid_at) : '—'}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}

function DemoPane({ orgId }: { orgId: string }) {
  const q = useQuery({
    queryKey: queryKeys.internalOrgDemoData(orgId),
    queryFn: () => internalApi.orgDemoData(orgId),
  })
  if (q.isPending) return <PageLoader />
  const d = q.data
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
        <div className={`h-3 w-3 rounded-full ${d?.loaded ? 'bg-warn-500' : 'bg-slate-300'}`} />
        <div>
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
            {d?.loaded ? 'Demo data is loaded' : 'No demo data'}
          </p>
          {d?.loaded && (
            <p className="text-xs text-slate-500">
              {d.row_count} rows · recipe: {d.recipe ?? '—'} · loaded {d.loaded_at ? shortDate(d.loaded_at) : '—'}
            </p>
          )}
        </div>
      </div>
      {d?.loaded && (
        <p className="text-xs text-slate-400">
          Demo data is visible to the account's users. It can only be removed by the account owner from their settings.
        </p>
      )}
    </div>
  )
}
