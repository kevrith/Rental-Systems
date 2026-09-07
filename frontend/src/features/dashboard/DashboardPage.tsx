import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  CreditCard,
  DoorOpen,
  Plus,
  TrendingUp,
  UserPlus,
  Wrench,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { dashboardApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import { InspectionComplianceWidget } from '@/features/inspections/InspectionsPage'
import { PhoneVerificationBanner } from '@/features/auth/PhoneVerificationBanner'
import {
  Alert,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  linkButtonClass,
} from '@/components/ui'
import { amount, dateTime, errorMessage, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

/* Chart colours come from the design tokens so the dashboard matches the rest
   of the product and stays legible for the most common colour-vision types. */
const COLLECTED = '#2f9e6e'
const EXPECTED = '#94a3b8'
const OCCUPANCY_COLOURS = ['#2f9e6e', '#f0b429', '#dc4c48', '#6aa5ff']

export function DashboardPage() {
  const user = useAuthStore((state) => state.user)
  const canSeeFinancials = user?.permissions?.includes('financials:view')

  const financial = useQuery({
    queryKey: queryKeys.financial(6),
    queryFn: () => dashboardApi.financial(6),
    enabled: Boolean(canSeeFinancials),
  })

  const portfolio = useQuery({ queryKey: queryKeys.portfolio, queryFn: dashboardApi.portfolio })

  const firstName = user?.full_name?.split(' ')[0] ?? 'there'

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description="Here's how your portfolio is doing today."
      />

      <PhoneVerificationBanner />

      <div className="mb-6 empty:mb-0">
        <InspectionComplianceWidget />
      </div>

      {portfolio.data?.stats.total_properties === 0 && (
        <Card className="mb-6">
          <EmptyState
            icon={<Building2 className="h-6 w-6" />}
            title="Let's set up your portfolio"
            description="Add your first property, then its units. After that you can onboard tenants and start collecting rent through M-Pesa."
            action={
              <Link to="/properties/new" className={linkButtonClass()}>
                <Plus className="h-4 w-4" />
                Add your first property
              </Link>
            }
          />
        </Card>
      )}

      {canSeeFinancials && (
        <>
          {financial.isPending ? (
            <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-24" />
              ))}
            </div>
          ) : financial.isError ? (
            <Alert tone="danger" className="mb-6" title="Could not load your financials">
              {errorMessage(financial.error)}
            </Alert>
          ) : financial.data ? (
            <>
              <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  label="Expected this month"
                  value={kes(financial.data.expected_rent, { compact: true })}
                  hint="Contracted rent on live tenancies"
                  icon={<CalendarClock className="h-4 w-4" />}
                />
                <StatCard
                  label="Collected this month"
                  value={kes(financial.data.collected, { compact: true })}
                  tone="success"
                  hint={`${financial.data.collection_rate}% collection rate`}
                  icon={<CreditCard className="h-4 w-4" />}
                />
                <StatCard
                  label="Outstanding arrears"
                  value={kes(financial.data.total_arrears, { compact: true })}
                  tone={Number(financial.data.total_arrears) > 0 ? 'danger' : 'success'}
                  hint={`${financial.data.tenants_in_arrears} tenant(s) behind`}
                  icon={<AlertTriangle className="h-4 w-4" />}
                />
                <StatCard
                  label="Occupancy"
                  value={`${financial.data.occupancy_rate}%`}
                  tone={financial.data.occupancy_rate >= 80 ? 'success' : 'warn'}
                  hint={`${financial.data.occupied_units} of ${financial.data.total_units} units`}
                  icon={<TrendingUp className="h-4 w-4" />}
                />
              </div>

              <AttentionRow attention={financial.data.attention} />

              <div className="mb-5 grid gap-5 lg:grid-cols-3">
                <Card className="lg:col-span-2">
                  <CardHeader>
                    <div>
                      <CardTitle>Income — last 6 months</CardTitle>
                      <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">Invoiced against collected</p>
                    </div>
                  </CardHeader>
                  <CardBody>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={financial.data.monthly_chart.map((point) => ({
                            month: point.month,
                            Invoiced: Number(point.expected),
                            Collected: Number(point.collected),
                          }))}
                          margin={{ top: 4, right: 8, bottom: 0, left: 8 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                          <XAxis
                            dataKey="month"
                            tick={{ fontSize: 11, fill: '#64748b' }}
                            tickLine={false}
                            axisLine={{ stroke: '#e2e8f0' }}
                          />
                          <YAxis
                            tick={{ fontSize: 11, fill: '#64748b' }}
                            tickLine={false}
                            axisLine={false}
                            tickFormatter={(value: number) => amount(value)}
                            width={64}
                          />
                          <Tooltip
                            formatter={(value) => kes(Number(value))}
                            contentStyle={{
                              borderRadius: 8,
                              border: '1px solid #e2e8f0',
                              fontSize: 12,
                            }}
                          />
                          <Legend wrapperStyle={{ fontSize: 12 }} />
                          <Bar dataKey="Invoiced" fill={EXPECTED} radius={[4, 4, 0, 0]} />
                          <Bar dataKey="Collected" fill={COLLECTED} radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardBody>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Unit mix</CardTitle>
                  </CardHeader>
                  <CardBody>
                    <OccupancyChart stats={portfolio.data?.stats} />
                  </CardBody>
                </Card>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Top defaulters</CardTitle>
                    <Link
                      to="/arrears"
                      className="flex items-center gap-1 text-sm text-brand-600 hover:underline"
                    >
                      View arrears
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </CardHeader>
                  {financial.data.top_defaulters.length ? (
                    <ul className="divide-y divide-slate-100">
                      {financial.data.top_defaulters.map((defaulter) => (
                        <li
                          key={defaulter.tenancy_id}
                          className="flex items-center justify-between gap-3 px-5 py-3"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                              {defaulter.tenant_name}
                            </p>
                            <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                              {defaulter.property_name} · Unit {defaulter.unit_number}
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm font-semibold text-danger-700">
                              {kes(defaulter.amount_owed)}
                            </p>
                            <p className="text-xs text-slate-400 dark:text-slate-500">
                              {defaulter.days_overdue} days overdue
                            </p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState
                      title="Everyone is up to date"
                      description="No tenant currently owes rent."
                    />
                  )}
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Recent payments</CardTitle>
                    <Link
                      to="/payments"
                      className="flex items-center gap-1 text-sm text-brand-600 hover:underline"
                    >
                      All payments
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </CardHeader>
                  {financial.data.recent_payments.length ? (
                    <ul className="divide-y divide-slate-100">
                      {financial.data.recent_payments.map((payment) => (
                        <li
                          key={payment.id}
                          className="flex items-center justify-between gap-3 px-5 py-3"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                              {payment.tenant_name}
                            </p>
                            <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                              Unit {payment.unit_number} · {payment.method.replace('_', ' ')} ·{' '}
                              {dateTime(payment.paid_at)}
                            </p>
                          </div>
                          <p className="text-sm font-semibold text-money-700">
                            {kes(payment.amount)}
                          </p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState
                      title="No payments yet"
                      description="Payments appear here the moment they are confirmed."
                    />
                  )}
                </Card>
              </div>
            </>
          ) : null}
        </>
      )}

      <QuickActions />
    </div>
  )
}

function AttentionRow({
  attention,
}: {
  attention: { vacant: number; under_maintenance: number; vacating: number; leases_expiring: number }
}) {
  const items = [
    {
      label: 'Vacant units',
      value: attention.vacant,
      to: '/units?unit_status=vacant',
      icon: <DoorOpen className="h-4 w-4" />,
      tone: 'text-warn-700',
    },
    {
      label: 'Under maintenance',
      value: attention.under_maintenance,
      to: '/units?unit_status=under_maintenance',
      icon: <Wrench className="h-4 w-4" />,
      tone: 'text-danger-700',
    },
    {
      label: 'Vacating soon',
      value: attention.vacating,
      to: '/units?unit_status=vacating',
      icon: <CalendarClock className="h-4 w-4" />,
      tone: 'text-brand-700',
    },
    {
      label: 'Leases expiring',
      value: attention.leases_expiring,
      to: '/tenancies?tenancy_status=expiring_soon',
      icon: <AlertTriangle className="h-4 w-4" />,
      tone: 'text-warn-700',
    },
  ].filter((item) => item.value > 0)

  if (items.length === 0) return null

  return (
    <div className="mb-5 flex flex-wrap gap-2">
      {items.map((item) => (
        <Link
          key={item.label}
          to={item.to}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-brand-600"
        >
          <span className={item.tone}>{item.icon}</span>
          <span className="font-semibold text-slate-900 dark:text-slate-100">{item.value}</span>
          <span className="text-slate-600 dark:text-slate-400">{item.label}</span>
        </Link>
      ))}
    </div>
  )
}

function OccupancyChart({
  stats,
}: {
  stats?: {
    occupied_units: number
    vacant_units: number
    maintenance_units: number
    reserved_units: number
  }
}) {
  if (!stats) return <Skeleton className="h-48" />

  const data = [
    { name: 'Occupied', value: stats.occupied_units },
    { name: 'Vacant', value: stats.vacant_units },
    { name: 'Maintenance', value: stats.maintenance_units },
    { name: 'Reserved', value: stats.reserved_units },
  ].filter((entry) => entry.value > 0)

  if (data.length === 0) {
    return <p className="py-12 text-center text-sm text-slate-500 dark:text-slate-400">No units yet.</p>
  }

  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={45}
            outerRadius={70}
            paddingAngle={2}
          >
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={OCCUPANCY_COLOURS[index % OCCUPANCY_COLOURS.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => [`${Number(value)} unit(s)`, String(name)]}
            contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

function QuickActions() {
  const permissions = useAuthStore((state) => state.user?.permissions)

  const actions = [
    {
      to: '/properties/new',
      label: 'Add property',
      icon: <Building2 className="h-4 w-4" />,
      permission: 'property:manage',
    },
    {
      to: '/tenancies/new',
      label: 'Onboard a tenant',
      icon: <UserPlus className="h-4 w-4" />,
      permission: 'tenancy:manage',
    },
    {
      to: '/payments/new',
      label: 'Record a payment',
      icon: <CreditCard className="h-4 w-4" />,
      permission: 'payment:record',
    },
    {
      to: '/meter-readings/new',
      label: 'Record a meter reading',
      icon: <Wrench className="h-4 w-4" />,
      permission: 'meter_reading:record',
    },
  ].filter((action) => permissions?.includes(action.permission))

  if (actions.length === 0) return null

  return (
    <div className="mt-6">
      <p className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-300">Quick actions</p>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <Link key={action.to} to={action.to} className={linkButtonClass('outline')}>
            {action.icon}
            {action.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
