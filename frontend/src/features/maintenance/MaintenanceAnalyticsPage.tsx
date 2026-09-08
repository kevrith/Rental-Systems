import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Clock, TrendingUp, Wallet, Wrench } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { maintenanceApi } from '@/api'
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
import { amount, errorMessage, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const WINDOWS = [
  { value: 3, label: 'Last 3 months' },
  { value: 6, label: 'Last 6 months' },
  { value: 12, label: 'Last 12 months' },
  { value: 24, label: 'Last 24 months' },
]

/** "2026-09" as the axis wants to read it. */
function monthLabel(value: string): string {
  const [year, month] = value.split('-')
  const date = new Date(Number(year), Number(month) - 1, 1)
  return date.toLocaleDateString('en-KE', { month: 'short', year: '2-digit' })
}

export function MaintenanceAnalyticsPage() {
  const [months, setMonths] = useState(12)

  const overview = useQuery({
    queryKey: queryKeys.maintenanceAnalytics(months),
    queryFn: () => maintenanceApi.analytics(months),
  })

  if (overview.isPending) return <PageLoader />
  if (overview.isError) {
    return (
      <Alert tone="danger" title="Could not load maintenance costs">
        {errorMessage(overview.error)}
      </Alert>
    )
  }

  const data = overview.data
  const trend = data.monthly_trend.map((point) => ({
    ...point,
    label: monthLabel(point.month),
  }))

  return (
    <div>
      <PageHeader
        title="Maintenance costs"
        description="Where the repair money goes, and which units keep asking for it."
        backTo="/maintenance"
        backLabel="All maintenance"
        actions={
          <Field className="w-48">
            <Select value={months} onChange={(event) => setMonths(Number(event.target.value))}>
              {WINDOWS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        }
      />

      {data.spike_alert && (
        <Alert
          tone="warn"
          className="mb-4"
          icon={<TrendingUp className="h-4 w-4" />}
          title="Spending is spiking"
        >
          This month is {kes(data.this_month_cost)} against a {kes(data.average_monthly_cost)}{' '}
          monthly average.
        </Alert>
      )}

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Spent this month"
          value={kes(data.this_month_cost)}
          hint={
            data.budget_used_percent !== null
              ? `${data.budget_used_percent}% of the ${kes(data.monthly_budget)} budget`
              : `${kes(data.average_monthly_cost)} monthly average`
          }
          tone={data.budget_used_percent !== null && data.budget_used_percent > 100 ? 'danger' : 'default'}
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Open jobs"
          value={String(data.open_jobs)}
          hint={`${data.awaiting_approval} waiting on approval`}
          icon={<Wrench className="h-4 w-4" />}
        />
        <StatCard
          label="Overdue"
          value={String(data.overdue_jobs)}
          tone={data.overdue_jobs > 0 ? 'danger' : 'default'}
          hint={data.overdue_jobs > 0 ? 'Past their expected completion date' : 'Nothing running late'}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <StatCard
          label="Average turnaround"
          value={
            data.average_completion_days === null ? '—' : `${data.average_completion_days} days`
          }
          hint="Report to completion"
          icon={<Clock className="h-4 w-4" />}
        />
      </div>

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>Monthly spend</CardTitle>
            <span className="text-sm text-slate-500">{kes(data.window_cost)} over the window</span>
          </CardHeader>
          <CardBody>
            {trend.length ? (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                    <CartesianGrid stroke={AXIS.grid} vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: AXIS.tick, fontSize: 12 }} tickLine={false} />
                    <YAxis
                      yAxisId="cost"
                      tick={{ fill: AXIS.tick, fontSize: 12 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value: number) => amount(value)}
                    />
                    <YAxis
                      yAxisId="jobs"
                      orientation="right"
                      tick={{ fill: AXIS.tick, fontSize: 12 }}
                      tickLine={false}
                      axisLine={false}
                      allowDecimals={false}
                    />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(value, name) =>
                        name === 'Jobs'
                          ? [String(value), String(name)]
                          : [kes(Number(value)), String(name)]
                      }
                    />
                    <Legend />
                    <Bar
                      yAxisId="cost"
                      dataKey="total_cost"
                      name="Spend"
                      fill={SERIES.other}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={48}
                    />
                    <Line
                      yAxisId="jobs"
                      type="monotone"
                      dataKey="jobs"
                      name="Jobs"
                      stroke={REFERENCE}
                      strokeWidth={2}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState
                icon={<Wallet className="h-6 w-6" />}
                title="No completed jobs yet"
                description="Costs appear here once jobs are completed with a final cost recorded."
              />
            )}
          </CardBody>
        </Card>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>By property</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              {data.by_property.length ? (
                <div className="overflow-x-auto">
                  <Table>
                    <thead>
                      <tr>
                        <Th>Property</Th>
                        <Th>This month</Th>
                        <Th>Window total</Th>
                        <Th>Budget</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.by_property.map((row) => (
                        <tr key={row.property_id}>
                          <Td>
                            <Link
                              to={`/properties/${row.property_id}`}
                              className="font-medium text-slate-800 hover:text-brand-700"
                            >
                              {row.property_name}
                            </Link>
                            <p className="text-xs text-slate-400">{row.jobs} job(s)</p>
                          </Td>
                          <Td>{kes(row.this_month_cost)}</Td>
                          <Td>{kes(row.total_cost)}</Td>
                          <Td>
                            {row.monthly_budget === null ? (
                              <span className="text-xs text-slate-400">Not set</span>
                            ) : (
                              <Badge
                                tone={row.over_budget ? 'danger' : 'success'}
                                className="whitespace-nowrap"
                              >
                                {amount(Math.abs(row.budget_variance ?? 0))}
                                {row.over_budget ? ' over' : ' left'}
                              </Badge>
                            )}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              ) : (
                <EmptyState
                  icon={<Wrench className="h-6 w-6" />}
                  title="Nothing spent yet"
                  description="No completed maintenance in this window."
                />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>What keeps breaking</CardTitle>
            </CardHeader>
            <CardBody>
              {data.by_category.length ? (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.by_category.map((row) => ({ ...row, label: humanize(row.category) }))}
                      layout="vertical"
                      margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
                    >
                      <CartesianGrid stroke={AXIS.grid} horizontal={false} />
                      <XAxis
                        type="number"
                        tick={{ fill: AXIS.tick, fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                        allowDecimals={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="label"
                        width={90}
                        tick={{ fill: AXIS.tick, fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip
                        contentStyle={TOOLTIP_STYLE}
                        formatter={(value, _name, entry) => [
                          `${value} job(s) · ${kes(Number(entry?.payload?.total_cost ?? 0))}`,
                          'Reported',
                        ]}
                      />
                      <Bar dataKey="jobs" radius={[0, 4, 4, 0]} maxBarSize={22}>
                        {data.by_category.map((row) => (
                          <Cell key={row.category} fill={SERIES.forecast} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyState
                  icon={<Wrench className="h-6 w-6" />}
                  title="No requests yet"
                  description="Categories appear once issues are reported."
                />
              )}
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Units eating their rent</CardTitle>
            <span className="text-sm text-slate-500">Maintenance as a share of rent collected</span>
          </CardHeader>
          <CardBody className="p-0">
            {data.expensive_units.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>Unit</Th>
                      <Th>Jobs</Th>
                      <Th>Spend</Th>
                      <Th>Monthly rent</Th>
                      <Th>Share of rent</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.expensive_units.map((row) => (
                      <tr key={row.unit_id}>
                        <Td>
                          <Link
                            to={`/units/${row.unit_id}`}
                            className="font-medium text-slate-800 hover:text-brand-700"
                          >
                            Unit {row.unit_number}
                          </Link>
                          <p className="text-xs text-slate-400">{row.property_name}</p>
                        </Td>
                        <Td>{row.jobs}</Td>
                        <Td>{kes(row.total_cost)}</Td>
                        <Td>{kes(row.monthly_rent)}</Td>
                        <Td>
                          {row.cost_to_rent_percent === null ? (
                            '—'
                          ) : (
                            <span
                              className={
                                row.needs_attention
                                  ? 'font-medium text-danger-700'
                                  : 'text-slate-700'
                              }
                            >
                              {row.cost_to_rent_percent.toFixed(1)}%
                            </span>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            ) : (
              <EmptyState
                icon={<Wrench className="h-6 w-6" />}
                title="No unit costs yet"
                description="Once jobs are completed, the units costing the most show up here."
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Who you use most</CardTitle>
            <Link to="/vendors" className="text-sm text-brand-600 hover:text-brand-700">
              All vendors
            </Link>
          </CardHeader>
          <CardBody className="p-0">
            {data.top_vendors.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>Vendor</Th>
                      <Th>Jobs</Th>
                      <Th>Average cost</Th>
                      <Th>Total billed</Th>
                      <Th>Rating</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_vendors.map((row) => (
                      <tr key={row.vendor_id}>
                        <Td>
                          <Link
                            to={`/vendors/${row.vendor_id}`}
                            className="font-medium text-slate-800 hover:text-brand-700"
                          >
                            {row.name}
                          </Link>
                          <p className="text-xs text-slate-400">
                            {row.specialties.map(humanize).join(', ')}
                          </p>
                        </Td>
                        <Td>{row.jobs_completed}</Td>
                        <Td>{kes(row.average_cost)}</Td>
                        <Td>{kes(row.total_billed)}</Td>
                        <Td>
                          {row.average_rating === null ? '—' : `${row.average_rating.toFixed(1)} / 5`}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            ) : (
              <EmptyState
                icon={<Wrench className="h-6 w-6" />}
                title="No vendor history yet"
                description="Assign vendors to jobs and their performance builds up here."
              />
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
