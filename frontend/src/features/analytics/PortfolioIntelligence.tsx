import { useQuery } from '@tanstack/react-query'
import { Droplets, TrendingDown, UserMinus, Zap } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { analyticsApi } from '@/api'
import type { PaymentSegment } from '@/api/types'
import { StatCard } from '@/components/PageHeader'
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  Table,
  Td,
  Th,
  type BadgeTone,
} from '@/components/ui'
import { AXIS, SERIES, TOOLTIP_STYLE } from '@/features/analytics/chart-theme'
import { amount, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/**
 * The three Module 12 reports that were promised and never computed: utility
 * intelligence, payment-behaviour segmentation, and tenant turnover.
 *
 * Only the utility trend gets a chart. The behaviour segments are an ordered
 * severity scale, not five independent identities — painting them five
 * categorical hues would both misrepresent the data and break the palette the
 * theme comment already warns about. They get counts and a table instead, which
 * is what a landlord actually reads them off. Turnover is a single headline
 * number plus a per-property breakdown, for the same reason.
 */

const SEGMENT_LABEL: Record<PaymentSegment, string> = {
  on_time: 'Pay on time',
  occasionally_late: 'Occasionally late',
  chronically_late: 'Chronically late',
  non_paying: 'Not paying',
  no_history: 'No history yet',
}

// Severity, not identity — so these are status tones, which ship with a label
// beside them rather than standing alone as colour.
const SEGMENT_TONE: Record<PaymentSegment, BadgeTone> = {
  on_time: 'success',
  occasionally_late: 'warn',
  chronically_late: 'warn',
  non_paying: 'danger',
  no_history: 'neutral',
}

const SEGMENT_ORDER: PaymentSegment[] = [
  'non_paying',
  'chronically_late',
  'occasionally_late',
  'on_time',
  'no_history',
]

export function PortfolioIntelligence() {
  const utilities = useQuery({
    queryKey: queryKeys.analyticsUtilities(6),
    queryFn: () => analyticsApi.utilities(6),
  })
  const behaviour = useQuery({
    queryKey: queryKeys.analyticsBehaviour(6),
    queryFn: () => analyticsApi.paymentBehaviour(6),
  })
  const turnover = useQuery({
    queryKey: queryKeys.analyticsTurnover(12),
    queryFn: () => analyticsApi.turnover(12),
  })

  const efficiency = utilities.data?.billing_efficiency
  const flagged = utilities.data?.high_consumption_units ?? []
  const worstPayers = (behaviour.data?.tenancies ?? []).filter(
    (row) => row.segment === 'non_paying' || row.segment === 'chronically_late',
  )

  return (
    <div className="mt-6 space-y-6">
      {/* ------------------------------------------------------ utilities */}

      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">Utilities</h2>

        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          {utilities.isPending ? (
            <>
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </>
          ) : (
            <>
              <StatCard
                label="Read but never billed"
                value={kes(efficiency?.amount_unbilled ?? 0)}
                hint="Consumption measured and not yet charged to anyone"
                tone={(efficiency?.amount_unbilled ?? 0) > 0 ? 'warn' : 'success'}
                icon={<TrendingDown className="h-4 w-4" />}
              />
              <StatCard
                label="Readings billed"
                value={`${efficiency?.billed_percent ?? 0}%`}
                hint={`${efficiency?.readings_billed ?? 0} of ${efficiency?.readings_taken ?? 0} readings`}
              />
              <StatCard
                label="Units consuming heavily"
                value={String(flagged.length)}
                hint="Well above their peers — a leak, or a sub-let"
                tone={flagged.length > 0 ? 'warn' : 'default'}
                icon={<Droplets className="h-4 w-4" />}
              />
            </>
          )}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Consumption over time</CardTitle>
              <p className="text-xs text-slate-500">
                Units consumed per month across the whole portfolio.
              </p>
            </CardHeader>
            <CardBody>
              {utilities.isPending ? (
                <Skeleton className="h-64" />
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={utilities.data?.trend ?? []}
                      margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid stroke={AXIS.grid} vertical={false} />
                      <XAxis
                        dataKey="month"
                        stroke={AXIS.tick}
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        stroke={AXIS.tick}
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(value) => amount(Number(value))}
                      />
                      <Tooltip
                        cursor={{ fill: 'rgb(15 23 42 / 0.04)' }}
                        contentStyle={TOOLTIP_STYLE}
                        formatter={(value) => `${amount(Number(value))} units`}
                      />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                      <Bar
                        dataKey="water_consumption"
                        name="Water"
                        fill={SERIES.forecast}
                        radius={[4, 4, 0, 0]}
                      />
                      <Bar
                        dataKey="electricity_consumption"
                        name="Electricity"
                        fill={SERIES.other}
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Units well above their peers</CardTitle>
              <p className="text-xs text-slate-500">
                Compared with other units in the same property, or the whole portfolio where
                there are too few to compare against.
              </p>
            </CardHeader>
            <CardBody>
              {flagged.length === 0 ? (
                <EmptyState
                  icon={<Droplets className="h-6 w-6" />}
                  title="Nothing unusual"
                  description="No unit is consuming materially more than its neighbours."
                />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {flagged.slice(0, 8).map((row) => (
                    <li
                      key={`${row.unit_id}-${row.meter_type}`}
                      className="flex items-center justify-between gap-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="flex items-center gap-1.5 truncate text-sm font-medium text-slate-800">
                          {row.meter_type === 'water' ? (
                            <Droplets className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                          ) : (
                            <Zap className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                          )}
                          {row.property_name} · Unit {row.unit_number}
                        </p>
                        <p className="truncate text-xs text-slate-500">
                          {amount(row.consumption)} units on {shortDate(row.reading_date)} ·{' '}
                          {row.peer_scope === 'property' ? 'property' : 'portfolio'} average{' '}
                          {amount(row.peer_average)}
                        </p>
                      </div>
                      <Badge tone="warn">+{row.percent_above_average}%</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      {/* --------------------------------------------- payment behaviour */}

      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">How tenants pay</h2>
        <p className="mb-3 text-sm text-slate-600">
          Arrears tells you who owes money today. This tells you who is a problem — a tenant who
          clears every invoice three weeks late never shows up in arrears yet costs the same
          cash-flow pain every month.
        </p>

        <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {behaviour.isPending
            ? SEGMENT_ORDER.map((segment) => <Skeleton key={segment} className="h-20" />)
            : SEGMENT_ORDER.map((segment) => (
                <div
                  key={segment}
                  className="rounded-card border border-slate-200 bg-white p-3 text-center"
                >
                  <p className="text-2xl font-semibold tracking-tight text-slate-900">
                    {behaviour.data?.segments[segment] ?? 0}
                  </p>
                  <Badge tone={SEGMENT_TONE[segment]} className="mt-1">
                    {SEGMENT_LABEL[segment]}
                  </Badge>
                </div>
              ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Tenants worth chasing</CardTitle>
          </CardHeader>
          <CardBody>
            {worstPayers.length === 0 ? (
              <EmptyState
                icon={<UserMinus className="h-6 w-6" />}
                title="Everyone is paying"
                description="No tenant is chronically late or in arrears over the last six months."
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>Tenant</Th>
                      <Th>Where</Th>
                      <Th>Pattern</Th>
                      <Th className="text-right">Typically late by</Th>
                      <Th className="text-right">Outstanding</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {worstPayers.slice(0, 12).map((row) => (
                      <tr key={row.tenancy_id}>
                        <Td className="font-medium text-slate-800">{row.tenant_name}</Td>
                        <Td className="text-slate-500">
                          {row.property_name} · {row.unit_number}
                        </Td>
                        <Td>
                          <Badge tone={SEGMENT_TONE[row.segment]}>
                            {SEGMENT_LABEL[row.segment]}
                          </Badge>
                        </Td>
                        <Td className="text-right tabular-nums">
                          {row.paid_late > 0 ? `${row.average_days_late} days` : '—'}
                        </Td>
                        <Td className="text-right tabular-nums">{kes(row.outstanding_balance)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* ------------------------------------------------------ turnover */}

      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">Turnover</h2>

        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          {turnover.isPending ? (
            <>
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </>
          ) : (
            <>
              <StatCard
                label="Turnover this year"
                value={`${turnover.data?.turnover_rate_percent ?? 0}%`}
                hint={`${turnover.data?.moved_out ?? 0} of ${turnover.data?.tenancies_held ?? 0} tenancies ended`}
                tone={(turnover.data?.turnover_rate_percent ?? 0) > 30 ? 'warn' : 'default'}
                icon={<UserMinus className="h-4 w-4" />}
              />
              <StatCard
                label="Average stay"
                value={
                  turnover.data?.average_tenancy_months
                    ? `${turnover.data.average_tenancy_months} months`
                    : '—'
                }
                hint="Among tenancies that ended this year"
              />
              <StatCard
                label="Average stay, all time"
                value={
                  turnover.data?.average_tenancy_months_all_time
                    ? `${turnover.data.average_tenancy_months_all_time} months`
                    : '—'
                }
                hint={`Across ${turnover.data?.tenancies_ever_ended ?? 0} tenancies ever ended`}
              />
            </>
          )}
        </div>

        {(turnover.data?.properties ?? []).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>By property</CardTitle>
              <p className="text-xs text-slate-500">
                Measured against tenancies actually held, not unit count — an empty unit has
                nobody in it to leave.
              </p>
            </CardHeader>
            <CardBody>
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>Property</Th>
                      <Th className="text-right">Active</Th>
                      <Th className="text-right">Moved out</Th>
                      <Th className="text-right">Turnover</Th>
                      <Th className="text-right">Average stay</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(turnover.data?.properties ?? []).map((row) => (
                      <tr key={row.property_id}>
                        <Td className="font-medium text-slate-800">{row.property_name}</Td>
                        <Td className="text-right tabular-nums">{row.active_tenancies}</Td>
                        <Td className="text-right tabular-nums">{row.moved_out}</Td>
                        <Td className="text-right tabular-nums">{row.turnover_rate_percent}%</Td>
                        <Td className="text-right tabular-nums">
                          {row.average_tenancy_months ? `${row.average_tenancy_months} mo` : '—'}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  )
}
