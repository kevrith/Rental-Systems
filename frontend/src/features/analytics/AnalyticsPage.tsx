import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Percent, Table2, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { analyticsApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Field,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { AXIS, REFERENCE, SERIES, TOOLTIP_STYLE } from '@/features/analytics/chart-theme'
import { PortfolioIntelligence } from '@/features/analytics/PortfolioIntelligence'
import { amount, errorMessage, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

type SortKey = 'collection_rate' | 'occupancy_rate' | 'collected_this_month' | 'total_maintenance_cost'

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'collection_rate', label: 'Collection rate' },
  { value: 'occupancy_rate', label: 'Occupancy' },
  { value: 'collected_this_month', label: 'Collected this month' },
  { value: 'total_maintenance_cost', label: 'Maintenance spend' },
]

const RENEWAL_STATE_LABEL: Record<string, string> = {
  none: 'No renewal offer',
  declined: 'Renewal declined',
  lapsed: 'Offer lapsed',
}

const RENEWAL_STATE_TONE: Record<string, 'warn' | 'danger'> = {
  none: 'warn',
  declined: 'danger',
  lapsed: 'danger',
}

/** A percentage bar that reads without needing the number decoded from colour. */
function RateBar({ value, tone }: { value: number; tone: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: tone }}
        />
      </div>
      <span className="tabular-nums text-sm text-slate-700">{value.toFixed(1)}%</span>
    </div>
  )
}

export function AnalyticsPage() {
  const [months, setMonths] = useState(6)
  const [sortBy, setSortBy] = useState<SortKey>('collection_rate')
  const [showTable, setShowTable] = useState(false)

  const revenue = useQuery({
    queryKey: queryKeys.analyticsRevenue(months),
    queryFn: () => analyticsApi.revenue(months),
  })
  const performance = useQuery({
    queryKey: queryKeys.analyticsPerformance,
    queryFn: analyticsApi.propertyPerformance,
  })
  const forecast = useQuery({
    queryKey: queryKeys.analyticsForecast(3),
    queryFn: () => analyticsApi.cashFlowForecast(3),
  })
  const expiring = useQuery({
    queryKey: queryKeys.analyticsExpiring,
    queryFn: analyticsApi.expiringLeases,
  })
  const maintenance = useQuery({
    queryKey: queryKeys.analyticsMaintenance,
    queryFn: analyticsApi.maintenance,
  })
  const vacancyRisk = useQuery({
    queryKey: queryKeys.analyticsVacancyRisk,
    queryFn: () => analyticsApi.vacancyRisk(),
  })
  const rentReview = useQuery({
    queryKey: queryKeys.analyticsRentReview,
    queryFn: () => analyticsApi.rentReview(),
  })

  if (revenue.isPending) return <PageLoader />
  if (revenue.isError) return <Alert tone="danger">{errorMessage(revenue.error)}</Alert>

  const series = revenue.data.map((point) => ({
    month: point.month,
    Invoiced: point.expected,
    Collected: point.collected,
    rate: point.collection_rate,
  }))

  const totalCollected = series.reduce((sum, point) => sum + point.Collected, 0)
  const totalInvoiced = series.reduce((sum, point) => sum + point.Invoiced, 0)
  const overallRate = totalInvoiced ? (totalCollected / totalInvoiced) * 100 : 0
  const averageRate =
    series.length > 0 ? series.reduce((sum, point) => sum + point.rate, 0) / series.length : 0

  const latest = series.at(-1)
  const previous = series.at(-2)
  const movement =
    latest && previous && previous.Collected > 0
      ? ((latest.Collected - previous.Collected) / previous.Collected) * 100
      : null

  const rows = [...(performance.data ?? [])].sort(
    (a, b) => (b[sortBy] as number) - (a[sortBy] as number),
  )
  const best = rows[0]
  const worst = rows.length > 1 ? rows.at(-1) : undefined

  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Where the money came from, where it is going, and which properties carry the portfolio."
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={`Collected · last ${months} months`}
          value={kes(totalCollected, { compact: true })}
          hint={`of ${kes(totalInvoiced, { compact: true })} invoiced`}
        />
        <StatCard
          label="Collection rate"
          value={`${overallRate.toFixed(1)}%`}
          hint={`${averageRate.toFixed(1)}% average month`}
          tone={overallRate >= 90 ? 'success' : overallRate >= 75 ? 'warn' : 'danger'}
        />
        <StatCard
          label="This month vs last"
          value={movement === null ? '—' : `${movement >= 0 ? '+' : ''}${movement.toFixed(1)}%`}
          hint={latest ? `${kes(latest.Collected, { compact: true })} collected` : undefined}
          tone={movement === null ? 'default' : movement >= 0 ? 'success' : 'danger'}
          icon={
            movement === null ? undefined : movement >= 0 ? (
              <ArrowUpRight className="h-4 w-4" />
            ) : (
              <ArrowDownRight className="h-4 w-4" />
            )
          }
        />
        <StatCard
          label="Projected next month"
          value={
            forecast.data?.[0]
              ? kes(forecast.data[0].projected_income, { compact: true })
              : '—'
          }
          hint={
            forecast.data?.[0]
              ? `at ${forecast.data[0].collection_rate_assumption}% collection`
              : undefined
          }
        />
      </div>

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <Field label="Period" className="w-40">
          <Select
            value={String(months)}
            onChange={(event) => setMonths(Number(event.target.value))}
          >
            <option value="3">Last 3 months</option>
            <option value="6">Last 6 months</option>
            <option value="12">Last 12 months</option>
          </Select>
        </Field>
        <Field label="Rank properties by" className="w-56">
          <Select value={sortBy} onChange={(event) => setSortBy(event.target.value as SortKey)}>
            {SORTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <button
          type="button"
          onClick={() => setShowTable((open) => !open)}
          className="mb-2 inline-flex items-center gap-1.5 text-sm text-brand-700 hover:underline"
        >
          <Table2 className="h-4 w-4" />
          {showTable ? 'Hide' : 'Show'} the numbers behind the chart
        </button>
      </div>

      <div className="mb-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Invoiced against collected</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              The grey bar is what was billed; the green is what arrived.
            </p>
          </CardHeader>
          <CardBody>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={AXIS.grid} vertical={false} />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11, fill: AXIS.tick }}
                    tickLine={false}
                    axisLine={{ stroke: AXIS.grid }}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: AXIS.tick }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value: number) => amount(value)}
                    width={64}
                  />
                  <Tooltip
                    cursor={{ fill: 'rgb(15 23 42 / 0.04)' }}
                    formatter={(value) => kes(Number(value))}
                    contentStyle={TOOLTIP_STYLE}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Invoiced" fill={REFERENCE} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Collected" fill={SERIES.collected} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Collection rate</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Share of each month's billing that was actually paid.
            </p>
          </CardHeader>
          <CardBody>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={AXIS.grid} vertical={false} />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11, fill: AXIS.tick }}
                    tickLine={false}
                    axisLine={{ stroke: AXIS.grid }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: AXIS.tick }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value: number) => `${value}%`}
                    width={44}
                  />
                  <Tooltip
                    formatter={(value) => `${Number(value).toFixed(1)}%`}
                    contentStyle={TOOLTIP_STYLE}
                  />
                  <ReferenceLine
                    y={90}
                    stroke={REFERENCE}
                    strokeDasharray="4 4"
                    label={{ value: 'Target 90%', fontSize: 10, fill: AXIS.tick, position: 'right' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="rate"
                    name="Collection rate"
                    stroke={SERIES.collected}
                    strokeWidth={2}
                    dot={{ r: 4, strokeWidth: 0, fill: SERIES.collected }}
                    activeDot={{ r: 6, stroke: '#fff', strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      </div>

      {showTable && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle className="text-base">The numbers behind the charts</CardTitle>
          </CardHeader>
          <CardBody>
            <Table>
              <thead>
                <tr>
                  <Th>Month</Th>
                  <Th>Invoiced</Th>
                  <Th>Collected</Th>
                  <Th>Rate</Th>
                </tr>
              </thead>
              <tbody>
                {series.map((point) => (
                  <tr key={point.month}>
                    <Td>{point.month}</Td>
                    <Td className="tabular-nums">{kes(point.Invoiced)}</Td>
                    <Td className="tabular-nums">{kes(point.Collected)}</Td>
                    <Td className="tabular-nums">{point.rate.toFixed(1)}%</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      <div className="mb-5 grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Cash flow forecast</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Projected from the current rent roll at your recent collection rate — a plan, not a
              promise.
            </p>
          </CardHeader>
          <CardBody>
            {forecast.data && forecast.data.length > 0 ? (
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={forecast.data.map((point) => ({
                      month: point.month,
                      Projected: point.projected_income,
                    }))}
                    margin={{ top: 4, right: 8, bottom: 0, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={AXIS.grid} vertical={false} />
                    <XAxis
                      dataKey="month"
                      tick={{ fontSize: 11, fill: AXIS.tick }}
                      tickLine={false}
                      axisLine={{ stroke: AXIS.grid }}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: AXIS.tick }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value: number) => amount(value)}
                      width={64}
                    />
                    <Tooltip
                      cursor={{ fill: 'rgb(15 23 42 / 0.04)' }}
                      formatter={(value) => kes(Number(value))}
                      contentStyle={TOOLTIP_STYLE}
                    />
                    <Bar dataKey="Projected" fill={SERIES.forecast} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Not enough history to forecast yet.</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Coming up</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3 text-sm">
            <div>
              <p className="text-slate-500">Leases expiring</p>
              <ul className="mt-1 space-y-1">
                <li className="flex justify-between">
                  <span className="text-slate-600">Within 30 days</span>
                  <span className="font-medium">{expiring.data?.expiring_in_30_days ?? 0}</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-slate-600">Within 60 days</span>
                  <span className="font-medium">{expiring.data?.expiring_in_60_days ?? 0}</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-slate-600">Within 90 days</span>
                  <span className="font-medium">{expiring.data?.expiring_in_90_days ?? 0}</span>
                </li>
              </ul>
            </div>
            {maintenance.data && (
              <div className="border-t border-slate-100 pt-3">
                <p className="text-slate-500">Maintenance</p>
                <p className="mt-1 flex justify-between">
                  <span className="text-slate-600">This month</span>
                  <span className="font-medium">{kes(maintenance.data.this_month_cost)}</span>
                </p>
                <p className="flex justify-between">
                  <span className="text-slate-600">3-month average</span>
                  <span className="font-medium">{kes(maintenance.data.avg_monthly_cost_3m)}</span>
                </p>
                {maintenance.data.spike_alert && (
                  <Alert tone="warn" className="mt-2">
                    Spend this month is more than half again the recent average.
                  </Alert>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Property performance</CardTitle>
          <p className="mt-0.5 text-sm text-slate-500">
            {best && worst ? (
              <>
                <strong>{best.property_name}</strong> is collecting{' '}
                {best.collection_rate.toFixed(1)}% of what it bills;{' '}
                <strong>{worst.property_name}</strong> is at {worst.collection_rate.toFixed(1)}%.
              </>
            ) : (
              'Every property this month, ranked.'
            )}
          </p>
        </CardHeader>
        <CardBody>
          {rows.length === 0 ? (
            <EmptyState
              icon={<TrendingUp className="h-6 w-6" />}
              title="No properties yet"
              description="Performance appears once you have a property with units."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Property</Th>
                    <Th>Units</Th>
                    <Th>Occupancy</Th>
                    <Th>Collection rate</Th>
                    <Th>Collected</Th>
                    <Th>Invoiced</Th>
                    <Th>Maintenance</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.property_id}>
                      <Td>
                        <Link
                          to={`/properties/${row.property_id}`}
                          className="font-medium text-brand-700 hover:underline"
                        >
                          {row.property_name}
                        </Link>
                      </Td>
                      <Td className="tabular-nums">
                        {row.occupied_units}/{row.total_units}
                      </Td>
                      <Td>
                        <RateBar value={row.occupancy_rate} tone={SERIES.forecast} />
                      </Td>
                      <Td>
                        <RateBar
                          value={row.collection_rate}
                          tone={row.collection_rate >= 75 ? SERIES.collected : SERIES.other}
                        />
                      </Td>
                      <Td className="tabular-nums">{kes(row.collected_this_month)}</Td>
                      <Td className="tabular-nums text-slate-500">
                        {kes(row.expected_this_month)}
                      </Td>
                      <Td className="tabular-nums text-slate-500">
                        {kes(row.total_maintenance_cost)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Vacancy risk</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Leases ending within 90 days with no renewal offer on record.
            </p>
          </CardHeader>
          <CardBody>
            {vacancyRisk.data && vacancyRisk.data.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {vacancyRisk.data.slice(0, 8).map((row) => (
                  <li key={row.tenancy_id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-800">{row.tenant_name}</p>
                      <p className="truncate text-xs text-slate-500">
                        {row.property_name} · Unit {row.unit_number} · {kes(row.monthly_rent)}/mo
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm font-medium text-slate-800">
                        {row.days_until_expiry}d left
                      </p>
                      <Badge tone={RENEWAL_STATE_TONE[row.renewal_state]} className="mt-0.5">
                        {RENEWAL_STATE_LABEL[row.renewal_state]}
                      </Badge>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<AlertTriangle className="h-6 w-6" />}
                title="Nothing at risk"
                description="Every lease ending soon has a renewal offer out."
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Rent review suggestions</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Units unchanged for 12+ months, against the average for similar units in your own
              portfolio — an estimate, not market data.
            </p>
          </CardHeader>
          <CardBody>
            {rentReview.data && rentReview.data.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {rentReview.data.slice(0, 8).map((row) => (
                  <li key={row.tenancy_id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-800">{row.tenant_name}</p>
                      <p className="truncate text-xs text-slate-500">
                        {row.property_name} · Unit {row.unit_number} ·{' '}
                        {row.months_since_last_change} months unchanged
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm font-medium text-slate-800">{kes(row.monthly_rent)}</p>
                      <p
                        className={`text-xs ${row.percent_vs_portfolio_average < 0 ? 'text-amber-600' : 'text-slate-500'}`}
                      >
                        {row.percent_vs_portfolio_average >= 0 ? '+' : ''}
                        {row.percent_vs_portfolio_average}% vs. avg
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Percent className="h-6 w-6" />}
                title="Nothing to review"
                description="Every unit has had a rent review within the last year."
              />
            )}
          </CardBody>
        </Card>
      </div>

      <PortfolioIntelligence />
    </div>
  )
}
