import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import type { OrgDetail } from '@/api/types'
import {
  Alert,
  Badge,
  Button,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { amount, errorMessage, humanize, relative, shortDate } from '@/lib/format'
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
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null) // unit id
  const [adding, setAdding] = useState(false)

  const q = useQuery({
    queryKey: queryKeys.internalOrgUnits(orgId),
    queryFn: () => internalApi.orgUnits(orgId),
  })
  const props = useQuery({
    queryKey: queryKeys.internalOrgProperties(orgId),
    queryFn: () => internalApi.orgProperties(orgId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: queryKeys.internalOrgUnits(orgId) })

  const del = useMutation({
    mutationFn: (id: string) => internalApi.deleteOrgUnit(orgId, id),
    onSuccess: invalidate,
  })

  if (q.isPending) return <PageLoader />
  const rows = q.data ?? []
  const properties = props.data ?? []

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setAdding(true)}>
          Add unit
        </Button>
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No units" description="This org has no units yet." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Unit</Th>
              <Th>Property</Th>
              <Th>Type</Th>
              <Th>Rent</Th>
              <Th>Status</Th>
              <Th>Added</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <Td className="font-medium text-slate-900 dark:text-slate-100">{u.unit_number}</Td>
                <Td className="text-sm text-slate-600 dark:text-slate-400">{u.property_name ?? '—'}</Td>
                <Td className="text-sm text-slate-500">{u.unit_type ?? '—'}{u.bedrooms ? ` · ${u.bedrooms}br` : ''}</Td>
                <Td className="tabular-nums text-slate-700 dark:text-slate-300">{amount(Number(u.monthly_rent))}</Td>
                <Td><Badge tone={STATUS_TONE[u.status] ?? 'neutral'}>{humanize(u.status)}</Badge></Td>
                <Td className="text-xs text-slate-400">{shortDate(u.created_at)}</Td>
                <Td>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(u.id)} />
                    <Button
                      size="sm" variant="ghost"
                      icon={<Trash2 className="h-3.5 w-3.5 text-danger-500" />}
                      loading={del.isPending}
                      onClick={() => { if (confirm(`Archive unit ${u.unit_number}?`)) del.mutate(u.id) }}
                    />
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {adding && (
        <UnitFormDialog
          orgId={orgId}
          properties={properties}
          onClose={() => setAdding(false)}
          onSaved={invalidate}
        />
      )}
      {editing && (
        <UnitFormDialog
          orgId={orgId}
          properties={properties}
          unit={rows.find((u) => u.id === editing)}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      )}
    </div>
  )
}

type UnitRow = { id: string; unit_number: string; property_name: string | null; property_id: string; status: string; monthly_rent: string; unit_type: string | null; bedrooms: number | null; created_at: string }

function UnitFormDialog({
  orgId, properties, unit, onClose, onSaved,
}: {
  orgId: string
  properties: { id: string; name: string }[]
  unit?: UnitRow
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = Boolean(unit)
  const [form, setForm] = useState({
    property_id: unit?.property_id ?? properties[0]?.id ?? '',
    unit_number: unit?.unit_number ?? '',
    unit_type: unit?.unit_type ?? '',
    bedrooms: unit?.bedrooms?.toString() ?? '',
    monthly_rent: unit?.monthly_rent ?? '',
  })

  const save = useMutation({
    mutationFn: () =>
      isEdit
        ? internalApi.updateOrgUnit(orgId, unit!.id, {
            unit_number: form.unit_number || undefined,
            unit_type: form.unit_type || null,
            bedrooms: form.bedrooms ? Number(form.bedrooms) : null,
            monthly_rent: form.monthly_rent || undefined,
          })
        : internalApi.createOrgUnit(orgId, {
            property_id: form.property_id,
            unit_number: form.unit_number,
            unit_type: form.unit_type || null,
            bedrooms: form.bedrooms ? Number(form.bedrooms) : null,
            monthly_rent: form.monthly_rent || '0.00',
          }),
    onSuccess: () => { onSaved(); onClose() },
  })

  return (
    <Dialog open onClose={onClose} title={isEdit ? 'Edit unit' : 'Add unit'} size="sm">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        {!isEdit && (
          <Field label="Property">
            <Select value={form.property_id} onChange={(e) => setForm((f) => ({ ...f, property_id: e.target.value }))}>
              {properties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Unit number">
          <Input required value={form.unit_number} onChange={(e) => setForm((f) => ({ ...f, unit_number: e.target.value }))} />
        </Field>
        <Field label="Type (optional)">
          <Input value={form.unit_type} onChange={(e) => setForm((f) => ({ ...f, unit_type: e.target.value }))} placeholder="e.g. 1 bedroom" />
        </Field>
        <Field label="Bedrooms">
          <Input type="number" min={0} value={form.bedrooms} onChange={(e) => setForm((f) => ({ ...f, bedrooms: e.target.value }))} />
        </Field>
        <Field label="Monthly rent (KES)">
          <Input type="number" min={0} value={form.monthly_rent} onChange={(e) => setForm((f) => ({ ...f, monthly_rent: e.target.value }))} />
        </Field>
        {save.isError && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
        <Button type="submit" className="w-full" loading={save.isPending}>
          {isEdit ? 'Save changes' : 'Create unit'}
        </Button>
      </form>
    </Dialog>
  )
}

function TenantsPane({ orgId }: { orgId: string }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const q = useQuery({
    queryKey: queryKeys.internalOrgTenants(orgId),
    queryFn: () => internalApi.orgTenants(orgId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: queryKeys.internalOrgTenants(orgId) })

  const del = useMutation({
    mutationFn: (id: string) => internalApi.deleteOrgTenant(orgId, id),
    onSuccess: invalidate,
  })

  if (q.isPending) return <PageLoader />
  const rows = q.data ?? []

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setAdding(true)}>
          Add tenant
        </Button>
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No tenants" description="This org has no tenants yet." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Phone</Th>
              <Th>Email</Th>
              <Th>Added</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <Td className="font-medium text-slate-900 dark:text-slate-100">{t.full_name}</Td>
                <Td className="text-sm text-slate-600 dark:text-slate-400">{t.phone_number}</Td>
                <Td className="text-sm text-slate-500">{t.email ?? '—'}</Td>
                <Td className="text-xs text-slate-400">{shortDate(t.created_at)}</Td>
                <Td>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditing(t.id)} />
                    <Button
                      size="sm" variant="ghost"
                      icon={<Trash2 className="h-3.5 w-3.5 text-danger-500" />}
                      loading={del.isPending}
                      onClick={() => { if (confirm(`Archive tenant ${t.full_name}?`)) del.mutate(t.id) }}
                    />
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {adding && (
        <TenantFormDialog orgId={orgId} onClose={() => setAdding(false)} onSaved={invalidate} />
      )}
      {editing && (
        <TenantFormDialog
          orgId={orgId}
          tenant={rows.find((t) => t.id === editing)}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      )}
    </div>
  )
}

type TenantRow = { id: string; full_name: string; phone_number: string; email: string | null; created_at: string }

function TenantFormDialog({
  orgId, tenant, onClose, onSaved,
}: {
  orgId: string
  tenant?: TenantRow
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = Boolean(tenant)
  const [form, setForm] = useState({
    full_name: tenant?.full_name ?? '',
    phone_number: tenant?.phone_number ?? '',
    email: tenant?.email ?? '',
  })

  const save = useMutation({
    mutationFn: () =>
      isEdit
        ? internalApi.updateOrgTenant(orgId, tenant!.id, {
            full_name: form.full_name || undefined,
            phone_number: form.phone_number || undefined,
            email: form.email || null,
          })
        : internalApi.createOrgTenant(orgId, {
            full_name: form.full_name,
            phone_number: form.phone_number,
            email: form.email || null,
          }),
    onSuccess: () => { onSaved(); onClose() },
  })

  return (
    <Dialog open onClose={onClose} title={isEdit ? 'Edit tenant' : 'Add tenant'} size="sm">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <Field label="Full name">
          <Input required value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
        </Field>
        <Field label="Phone number">
          <Input required value={form.phone_number} onChange={(e) => setForm((f) => ({ ...f, phone_number: e.target.value }))} />
        </Field>
        <Field label="Email (optional)">
          <Input type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
        </Field>
        {save.isError && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
        <Button type="submit" className="w-full" loading={save.isPending}>
          {isEdit ? 'Save changes' : 'Create tenant'}
        </Button>
      </form>
    </Dialog>
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
