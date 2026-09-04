import { useQuery } from '@tanstack/react-query'
import { Building2, MapPin, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { dashboardApi, propertiesApi } from '@/api'
import type { PropertySummary } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import { Badge, Card, EmptyState, Input, Skeleton, linkButtonClass } from '@/components/ui'
import { kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function PropertiesPage() {
  const [search, setSearch] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('property:manage'))

  const properties = useQuery({
    queryKey: queryKeys.properties({ search, includeArchived }),
    queryFn: () =>
      propertiesApi.list({ search: search || undefined, include_archived: includeArchived }),
  })

  const portfolio = useQuery({ queryKey: queryKeys.portfolio, queryFn: dashboardApi.portfolio })

  return (
    <div>
      <PageHeader
        title="Properties"
        description="Every building, block and asset you manage."
        actions={
          canManage && (
            <Link to="/properties/new" className={linkButtonClass()}>
              <Plus className="h-4 w-4" />
              Add property
            </Link>
          )
        }
      />

      {portfolio.data && (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Properties" value={String(portfolio.data.stats.total_properties)} />
          <StatCard label="Total units" value={String(portfolio.data.stats.total_units)} />
          <StatCard
            label="Occupancy"
            value={`${portfolio.data.stats.occupancy_rate}%`}
            tone={portfolio.data.stats.occupancy_rate >= 80 ? 'success' : 'warn'}
            hint={`${portfolio.data.stats.occupied_units} occupied · ${portfolio.data.stats.vacant_units} vacant`}
          />
          <StatCard
            label="Monthly rent potential"
            value={kes(portfolio.data.stats.monthly_rent_potential, { compact: true })}
            hint={`${kes(portfolio.data.stats.monthly_rent_contracted, { compact: true })} contracted`}
          />
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by name, address or reference"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 accent-brand-600"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          Show archived
        </label>
      </div>

      {properties.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-44" />
          ))}
        </div>
      ) : properties.data?.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {properties.data.map((property) => (
            <PropertyCard key={property.id} property={property} />
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Building2 className="h-6 w-6" />}
            title={search ? 'No properties match that search' : 'No properties yet'}
            description={
              search
                ? 'Try a different name, address or reference code.'
                : 'Add your first property to start tracking units, tenants and rent.'
            }
            action={
              canManage && !search ? (
                <Link to="/properties/new" className={linkButtonClass()}>
                  <Plus className="h-4 w-4" />
                  Add your first property
                </Link>
              ) : undefined
            }
          />
        </Card>
      )}
    </div>
  )
}

function PropertyCard({ property }: { property: PropertySummary }) {
  const cover = property.photos[0]

  return (
    <Link
      to={`/properties/${property.id}`}
      className="group overflow-hidden rounded-card border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="relative h-32 bg-slate-100">
        {cover ? (
          <img src={cover.url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-slate-300">
            <Building2 className="h-8 w-8" />
          </div>
        )}
        {property.is_archived && (
          <Badge tone="neutral" className="absolute left-2 top-2">
            Archived
          </Badge>
        )}
      </div>

      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-medium text-slate-900 group-hover:text-brand-700">
              {property.name}
            </p>
            <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-slate-500">
              <MapPin className="h-3 w-3 shrink-0" />
              {property.address}
            </p>
          </div>
          <Badge tone="brand">{property.reference_code}</Badge>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-center">
          <div>
            <p className="text-sm font-semibold text-slate-900">{property.total_units}</p>
            <p className="text-[11px] text-slate-500">Units</p>
          </div>
          <div>
            <p className="text-sm font-semibold text-money-700">{property.occupied_units}</p>
            <p className="text-[11px] text-slate-500">Occupied</p>
          </div>
          <div>
            <p className="text-sm font-semibold text-warn-700">{property.vacant_units}</p>
            <p className="text-[11px] text-slate-500">Vacant</p>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="text-slate-500">
            {property.total_units > 0 ? `${property.occupancy_rate}% occupied` : 'No units yet'}
          </span>
          <span className="font-medium text-slate-700">
            {kes(property.monthly_rent_potential, { compact: true })}/mo
          </span>
        </div>
      </div>
    </Link>
  )
}
