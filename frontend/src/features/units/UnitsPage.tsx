import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Layers, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { propertiesApi, unitsApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Card,
  EmptyState,
  Input,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  UNIT_STATUS_TONE,
  linkButtonClass,
} from '@/components/ui'
import { humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const STATUSES = ['vacant', 'occupied', 'under_maintenance', 'reserved', 'vacating']

export function UnitsPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [propertyId, setPropertyId] = useState('')
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('unit:manage'))

  const properties = useQuery({
    queryKey: queryKeys.properties({ forFilter: true }),
    queryFn: () => propertiesApi.list(),
  })

  const units = useQuery({
    queryKey: queryKeys.units({ search, status, propertyId }),
    queryFn: () =>
      unitsApi.list({
        search: search || undefined,
        unit_status: status || undefined,
        property_id: propertyId || undefined,
      }),
  })

  const propertyName = (id: string) =>
    properties.data?.find((property) => property.id === id)?.name ?? '—'

  return (
    <div>
      <PageHeader
        title="Units"
        description="Every rentable unit across your portfolio."
        actions={
          canManage && (
            <>
              <Link to="/units/bulk" className={linkButtonClass('outline')}>
                <Layers className="h-4 w-4" />
                Add many
              </Link>
              <Link to="/units/new" className={linkButtonClass()}>
                <Plus className="h-4 w-4" />
                Add unit
              </Link>
            </>
          )
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by unit number or reference"
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
          <option value="">Any status</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {humanize(value)}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        {units.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : units.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Unit</Th>
                <Th>Property</Th>
                <Th>Type</Th>
                <Th>Rent</Th>
                <Th>Deposit</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {units.data.map((unit) => (
                <tr key={unit.id} className="hover:bg-slate-50">
                  <Td>
                    <Link
                      to={`/units/${unit.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {unit.unit_number}
                    </Link>
                    <span className="block text-xs text-slate-400">{unit.reference_code}</span>
                  </Td>
                  <Td className="text-slate-600">{propertyName(unit.property_id)}</Td>
                  <Td className="text-slate-600">
                    {unit.unit_type ?? '—'}
                    {unit.bedrooms != null && (
                      <span className="block text-xs text-slate-400">
                        {unit.bedrooms} bed · {unit.bathrooms ?? 0} bath
                      </span>
                    )}
                  </Td>
                  <Td className="font-medium">{kes(unit.monthly_rent)}</Td>
                  <Td className="text-slate-600">{kes(unit.deposit_amount)}</Td>
                  <Td>
                    <Badge tone={UNIT_STATUS_TONE[unit.status] ?? 'neutral'}>
                      {humanize(unit.status)}
                    </Badge>
                    {unit.status === 'vacating' && unit.expected_vacancy_date && (
                      <span className="mt-0.5 block text-xs text-slate-400">
                        Free {shortDate(unit.expected_vacancy_date)}
                      </span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<ClipboardList className="h-6 w-6" />}
            title="No units match"
            description="Adjust the filters, or add units to a property."
          />
        )}
      </Card>
    </div>
  )
}
