import { useQuery } from '@tanstack/react-query'
import { FileText, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { tenanciesApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Card,
  EmptyState,
  Select,
  Skeleton,
  TENANCY_STATUS_TONE,
  Tab,
  Table,
  Tabs,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const TABS = [
  { key: '', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'expiring_soon', label: 'Expiring soon' },
  { key: 'notice_given', label: 'Notice given' },
  { key: 'expired', label: 'Expired' },
  { key: 'vacated', label: 'Vacated' },
]

export function TenanciesPage() {
  const [status, setStatus] = useState('')
  const [expiringWithin, setExpiringWithin] = useState('')
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('tenancy:manage'))

  const tenancies = useQuery({
    queryKey: queryKeys.tenancies({ status, expiringWithin }),
    queryFn: () =>
      tenanciesApi.list({
        tenancy_status: status || undefined,
        expiring_within_days: expiringWithin ? Number(expiringWithin) : undefined,
      }),
  })

  return (
    <div>
      <PageHeader
        title="Tenancies"
        description="Every rental agreement, and where it is in its life."
        actions={
          canManage && (
            <Link to="/tenancies/new" className={linkButtonClass()}>
              <Plus className="h-4 w-4" />
              New tenancy
            </Link>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={status} onChange={setStatus}>
          {TABS.map((tab) => (
            <Tab key={tab.key} value={tab.key}>
              {tab.label}
            </Tab>
          ))}
        </Tabs>

        <Select
          className="w-auto min-w-44"
          value={expiringWithin}
          onChange={(event) => setExpiringWithin(event.target.value)}
        >
          <option value="">Any expiry</option>
          <option value="14">Expiring in 14 days</option>
          <option value="30">Expiring in 30 days</option>
          <option value="60">Expiring in 60 days</option>
          <option value="90">Expiring in 90 days</option>
        </Select>
      </div>

      <Card>
        {tenancies.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : tenancies.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Tenant</Th>
                <Th>Unit</Th>
                <Th>Term</Th>
                <Th>Rent</Th>
                <Th>Balance</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {tenancies.data.map((tenancy) => (
                <tr key={tenancy.id} className="hover:bg-slate-50">
                  <Td>
                    <Link
                      to={`/tenancies/${tenancy.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {tenancy.tenant_name}
                    </Link>
                    <span className="block text-xs text-slate-400">{tenancy.reference_code}</span>
                  </Td>
                  <Td className="text-slate-600">
                    {tenancy.unit_number}
                    <span className="block text-xs text-slate-400">{tenancy.property_name}</span>
                  </Td>
                  <Td className="text-slate-600">
                    {shortDate(tenancy.start_date)}
                    <span className="block text-xs text-slate-400">
                      {tenancy.is_open_ended
                        ? 'Open-ended'
                        : `to ${shortDate(tenancy.end_date)}${
                            tenancy.days_to_expiry != null && tenancy.days_to_expiry >= 0
                              ? ` · ${tenancy.days_to_expiry}d left`
                              : ''
                          }`}
                    </span>
                  </Td>
                  <Td className="font-medium">{kes(tenancy.monthly_rent)}</Td>
                  <Td>
                    <span
                      className={
                        Number(tenancy.balance) > 0
                          ? 'font-medium text-danger-700'
                          : 'text-money-700'
                      }
                    >
                      {kes(tenancy.balance)}
                    </span>
                  </Td>
                  <Td>
                    <Badge tone={TENANCY_STATUS_TONE[tenancy.status] ?? 'neutral'}>
                      {humanize(tenancy.status)}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="No tenancies here"
            description="Create a tenancy to link a tenant to a unit."
            action={
              canManage ? (
                <Link to="/tenancies/new" className={linkButtonClass()}>
                  <Plus className="h-4 w-4" />
                  New tenancy
                </Link>
              ) : undefined
            }
          />
        )}
      </Card>
    </div>
  )
}
