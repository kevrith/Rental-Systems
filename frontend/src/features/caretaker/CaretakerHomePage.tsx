import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  CreditCard,
  DoorOpen,
  Droplets,
  Gauge,
  Wrench,
  Zap,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { caretakerApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  MAINTENANCE_STATUS_TONE,
  PRIORITY_TONE,
  Skeleton,
} from '@/components/ui'
import { OfflineBanner } from '@/components/SyncIndicator'
import { humanize, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

/**
 * The caretaker's home screen (US-024).
 *
 * Built for one thumb on a phone in a corridor: the three things they do most —
 * record a payment, take a meter reading, report a fault — are the first thing
 * on screen, above everything else.
 */
export function CaretakerHomePage() {
  const user = useAuthStore((state) => state.user)
  const tasks = useQuery({ queryKey: queryKeys.caretakerToday, queryFn: caretakerApi.today })

  const firstName = user?.full_name?.split(' ')[0] ?? 'there'

  return (
    <div>
      <OfflineBanner />

      <PageHeader
        title={`Hi ${firstName}`}
        description="Here's what needs doing today."
      />

      <div className="mb-6 grid grid-cols-3 gap-2">
        <QuickAction
          to="/payments/new"
          icon={<CreditCard className="h-5 w-5" />}
          label="Record payment"
        />
        <QuickAction
          to="/meter-readings/new"
          icon={<Gauge className="h-5 w-5" />}
          label="Meter reading"
        />
        <QuickAction
          to="/maintenance/new"
          icon={<Wrench className="h-5 w-5" />}
          label="Report issue"
        />
      </div>

      {tasks.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
      ) : tasks.data ? (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <SummaryTile
              icon={<DoorOpen className="h-4 w-4" />}
              value={tasks.data.units_vacant}
              label="Vacant units"
              to="/units?unit_status=vacant"
            />
            <SummaryTile
              icon={<AlertTriangle className="h-4 w-4" />}
              value={tasks.data.tenants_in_arrears}
              label="Tenants in arrears"
              to="/arrears"
              tone="danger"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Meter readings due</CardTitle>
              {tasks.data.readings_due.length > 0 && (
                <Badge tone="warn">{tasks.data.readings_due.length}</Badge>
              )}
            </CardHeader>
            {tasks.data.readings_due.length ? (
              <ul className="divide-y divide-slate-100">
                {tasks.data.readings_due.map((reading) => (
                  <li key={`${reading.unit_id}-${reading.meter_type}`}>
                    <Link
                      to={`/meter-readings/new?unit_id=${reading.unit_id}&meter_type=${reading.meter_type}`}
                      className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-slate-50"
                      data-touch-target
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        {reading.meter_type === 'water' ? (
                          <Droplets className="h-4 w-4 shrink-0 text-sky-500" />
                        ) : (
                          <Zap className="h-4 w-4 shrink-0 text-warn-500" />
                        )}
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-slate-900">
                            Unit {reading.unit_number}
                          </p>
                          <p className="truncate text-xs text-slate-500">{reading.property_name}</p>
                        </div>
                      </div>
                      <span className="shrink-0 text-xs text-slate-400">
                        Last: {reading.previous_reading}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                title="All readings taken"
                description="Every metered unit has a reading this month."
              />
            )}
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Open maintenance</CardTitle>
              <Link to="/maintenance" className="text-sm text-brand-600 hover:underline">
                View all
              </Link>
            </CardHeader>
            {tasks.data.open_maintenance.length ? (
              <ul className="divide-y divide-slate-100">
                {tasks.data.open_maintenance.map((request) => (
                  <li key={request.id}>
                    <Link
                      to={`/maintenance/${request.id}`}
                      className="flex items-start justify-between gap-3 px-5 py-3 hover:bg-slate-50"
                      data-touch-target
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {request.title}
                        </p>
                        <p className="truncate text-xs text-slate-500">
                          Unit {request.unit_number} · {relative(request.created_at)}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <Badge tone={PRIORITY_TONE[request.priority] ?? 'neutral'}>
                          {humanize(request.priority)}
                        </Badge>
                        <Badge tone={MAINTENANCE_STATUS_TONE[request.status] ?? 'neutral'}>
                          {humanize(request.status)}
                        </Badge>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Nothing outstanding" description="No open maintenance requests." />
            )}
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Your recent activity</CardTitle>
            </CardHeader>
            {tasks.data.recent_activity.length ? (
              <ul className="divide-y divide-slate-100">
                {tasks.data.recent_activity.map((entry) => (
                  <li key={entry.id} className="px-5 py-2.5">
                    <p className="text-sm text-slate-700">{entry.summary ?? entry.action}</p>
                    <p className="text-xs text-slate-400">{relative(entry.created_at)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <CardBody>
                <p className="text-sm text-slate-500">
                  Everything you record shows up here, and in your owner&apos;s daily summary.
                </p>
              </CardBody>
            )}
          </Card>
        </div>
      ) : null}
    </div>
  )
}

function QuickAction({
  to,
  icon,
  label,
}: {
  to: string
  icon: React.ReactNode
  label: string
}) {
  return (
    <Link
      to={to}
      data-touch-target
      className="flex flex-col items-center gap-1.5 rounded-card border border-slate-200 bg-white px-2 py-4 text-center text-xs font-medium text-slate-700 shadow-sm transition-colors hover:border-brand-300 hover:text-brand-700"
    >
      <span className="text-brand-600">{icon}</span>
      {label}
    </Link>
  )
}

function SummaryTile({
  icon,
  value,
  label,
  to,
  tone = 'default',
}: {
  icon: React.ReactNode
  value: number
  label: string
  to: string
  tone?: 'default' | 'danger'
}) {
  return (
    <Link
      to={to}
      className="rounded-card border border-slate-200 bg-white p-4 shadow-sm hover:border-brand-300"
    >
      <span className={tone === 'danger' ? 'text-danger-500' : 'text-slate-400'}>{icon}</span>
      <p
        className={`mt-1.5 text-2xl font-semibold ${
          tone === 'danger' && value > 0 ? 'text-danger-700' : 'text-slate-900'
        }`}
      >
        {value}
      </p>
      <p className="text-xs text-slate-500">{label}</p>
    </Link>
  )
}
