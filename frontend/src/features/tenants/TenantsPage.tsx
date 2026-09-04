import { useQuery } from '@tanstack/react-query'
import { Download, Plus, Search, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { propertiesApi, tenantsApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Card,
  EmptyState,
  Input,
  Select,
  Skeleton,
  TENANCY_STATUS_TONE,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { API_BASE_URL } from '@/lib/api-client'
import { humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const STATUS_FILTERS = [
  { value: '', label: 'All tenants' },
  { value: 'active', label: 'Active' },
  { value: 'expiring_soon', label: 'Expiring soon' },
  { value: 'notice_given', label: 'Notice given' },
  { value: 'expired', label: 'Expired' },
  { value: 'vacated', label: 'Vacated' },
]

export function TenantsPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [propertyId, setPropertyId] = useState('')
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('tenant:manage'))

  const properties = useQuery({
    queryKey: queryKeys.properties({ forTenantFilter: true }),
    queryFn: () => propertiesApi.list(),
  })

  const tenants = useQuery({
    queryKey: queryKeys.tenants({ search, status, propertyId }),
    queryFn: () =>
      tenantsApi.list({
        search: search || undefined,
        tenancy_status: status || undefined,
        property_id: propertyId || undefined,
      }),
  })

  // The CSV route streams a file, so it is a plain link rather than an XHR.
  const exportParams = new URLSearchParams()
  if (search) exportParams.set('search', search)
  if (status) exportParams.set('tenancy_status', status)
  if (propertyId) exportParams.set('property_id', propertyId)

  return (
    <div>
      <PageHeader
        title="Tenants"
        description="Everyone renting from you, with their unit and balance."
        actions={
          <>
            <a
              href={`${API_BASE_URL}${tenantsApi.exportCsvUrl}?${exportParams.toString()}`}
              className={linkButtonClass('outline')}
            >
              <Download className="h-4 w-4" />
              Export CSV
            </a>
            {canManage && (
              <Link to="/tenants/new" className={linkButtonClass()}>
                <Plus className="h-4 w-4" />
                Add tenant
              </Link>
            )}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by name, phone, ID, unit or property"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
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
          {STATUS_FILTERS.map((filter) => (
            <option key={filter.value} value={filter.value}>
              {filter.label}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        {tenants.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : tenants.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Tenant</Th>
                <Th>Unit</Th>
                <Th>Rent</Th>
                <Th>Lease ends</Th>
                <Th>Balance</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {tenants.data.map((tenant) => (
                <tr key={tenant.id} className="hover:bg-slate-50">
                  <Td>
                    <Link
                      to={`/tenants/${tenant.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {tenant.full_name}
                    </Link>
                    <span className="block text-xs text-slate-400">{tenant.phone_number}</span>
                  </Td>
                  <Td className="text-slate-600">
                    {tenant.unit_number ? (
                      <>
                        {tenant.unit_number}
                        <span className="block text-xs text-slate-400">{tenant.property_name}</span>
                      </>
                    ) : (
                      <span className="text-slate-400">No active unit</span>
                    )}
                  </Td>
                  <Td>{tenant.monthly_rent ? kes(tenant.monthly_rent) : '—'}</Td>
                  <Td className="text-slate-600">
                    {tenant.lease_end_date ? shortDate(tenant.lease_end_date) : '—'}
                  </Td>
                  <Td>
                    <span
                      className={
                        Number(tenant.balance) > 0
                          ? 'font-medium text-danger-700'
                          : 'text-money-700'
                      }
                    >
                      {kes(tenant.balance)}
                    </span>
                  </Td>
                  <Td>
                    {tenant.tenancy_status ? (
                      <Badge tone={TENANCY_STATUS_TONE[tenant.tenancy_status] ?? 'neutral'}>
                        {humanize(tenant.tenancy_status)}
                      </Badge>
                    ) : (
                      <Badge>Vacated</Badge>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<Users className="h-6 w-6" />}
            title={search || status ? 'No tenants match' : 'No tenants yet'}
            description={
              search || status
                ? 'Try a different search or filter.'
                : 'Add a tenant, then link them to a unit to create a tenancy.'
            }
            action={
              canManage && !search && !status ? (
                <Link to="/tenants/new" className={linkButtonClass()}>
                  <Plus className="h-4 w-4" />
                  Add your first tenant
                </Link>
              ) : undefined
            }
          />
        )}
      </Card>
    </div>
  )
}
