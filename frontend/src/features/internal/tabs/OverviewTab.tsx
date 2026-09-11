import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Building2,
  Home,
  ShieldOff,
  Users,
  Warehouse,
} from 'lucide-react'

import { internalApi } from '@/api'
import { Card, CardBody, PageLoader } from '@/components/ui'
import { queryKeys } from '@/lib/query-client'

function StatTile({
  label,
  value,
  sub,
  icon,
  tone = 'default',
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ReactNode
  tone?: 'default' | 'danger' | 'warn' | 'success'
}) {
  const toneClass = {
    default: 'bg-slate-50 border-slate-200 dark:bg-slate-800 dark:border-slate-700',
    danger: 'bg-danger-50 border-danger-200 dark:bg-danger-950 dark:border-danger-800',
    warn: 'bg-warn-50 border-warn-200 dark:bg-warn-950 dark:border-warn-800',
    success: 'bg-success-50 border-success-200 dark:bg-success-950 dark:border-success-800',
  }[tone]

  const iconClass = {
    default: 'text-slate-500 dark:text-slate-400',
    danger: 'text-danger-600 dark:text-danger-400',
    warn: 'text-warn-600 dark:text-warn-400',
    success: 'text-success-600 dark:text-success-400',
  }[tone]

  return (
    <div className={`rounded-xl border p-4 ${toneClass}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
          {sub && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{sub}</p>}
        </div>
        <span className={`mt-0.5 ${iconClass}`}>{icon}</span>
      </div>
    </div>
  )
}

function BreakdownBar({
  title,
  data,
  colorMap,
}: {
  title: string
  data: Record<string, number>
  colorMap: Record<string, string>
}) {
  const total = Object.values(data).reduce((s, v) => s + v, 0)
  if (total === 0) return null

  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {title}
      </p>
      <div className="flex h-3 w-full overflow-hidden rounded-full">
        {Object.entries(data).map(([key, count]) => (
          <div
            key={key}
            className={colorMap[key] ?? 'bg-slate-300'}
            style={{ width: `${(count / total) * 100}%` }}
            title={`${key}: ${count}`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-3">
        {Object.entries(data).map(([key, count]) => (
          <div key={key} className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
            <span className={`h-2.5 w-2.5 rounded-full ${colorMap[key] ?? 'bg-slate-300'}`} />
            <span className="capitalize">{key.replace(/_/g, ' ')}</span>
            <span className="font-semibold text-slate-900 dark:text-white">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const PLAN_COLORS: Record<string, string> = {
  trial: 'bg-slate-400',
  free: 'bg-slate-500',
  starter: 'bg-brand-400',
  professional: 'bg-brand-600',
  business: 'bg-brand-800',
}

const MODE_COLORS: Record<string, string> = {
  owner: 'bg-success-500',
  agency: 'bg-warn-500',
  dual: 'bg-brand-500',
}

export function OverviewTab() {
  const stats = useQuery({
    queryKey: queryKeys.internalPlatformStats,
    queryFn: internalApi.platformStats,
    refetchInterval: 60_000,
  })

  if (stats.isPending) return <PageLoader />
  const d = stats.data!

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile
          label="Organizations"
          value={d.total_organizations}
          sub={`${d.active_organizations} active`}
          icon={<Building2 className="h-5 w-5" />}
        />
        <StatTile
          label="Suspended"
          value={d.suspended_organizations}
          icon={<ShieldOff className="h-5 w-5" />}
          tone={d.suspended_organizations > 0 ? 'danger' : 'default'}
        />
        <StatTile
          label="Users"
          value={d.total_users}
          icon={<Users className="h-5 w-5" />}
        />
        <StatTile
          label="Units"
          value={d.total_units}
          icon={<Home className="h-5 w-5" />}
        />
        <StatTile
          label="Tenants"
          value={d.total_tenants}
          icon={<Warehouse className="h-5 w-5" />}
        />
        <StatTile
          label="Platform"
          value="Live"
          sub="All systems"
          icon={<Activity className="h-5 w-5" />}
          tone="success"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <Card>
          <CardBody className="space-y-4">
            <BreakdownBar
              title="Subscription plans"
              data={d.plan_breakdown}
              colorMap={PLAN_COLORS}
            />
          </CardBody>
        </Card>
        <Card>
          <CardBody className="space-y-4">
            <BreakdownBar
              title="Operating modes"
              data={d.mode_breakdown}
              colorMap={MODE_COLORS}
            />
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
