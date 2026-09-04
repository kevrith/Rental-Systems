import { useQuery } from '@tanstack/react-query'
import { Clock, Info, UserRound } from 'lucide-react'
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { caretakerPerformanceApi } from '@/api'
import type { CaretakerScore, PerformanceBand } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  Field,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
  type BadgeTone,
} from '@/components/ui'
import { AXIS, REFERENCE, SERIES, TOOLTIP_STYLE } from '@/features/analytics/chart-theme'
import { cn } from '@/lib/cn'
import { dateTime, errorMessage, kes, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const BAND_TONE: Record<PerformanceBand, BadgeTone> = {
  good: 'success',
  watch: 'warn',
  poor: 'danger',
  no_data: 'neutral',
}

const BAND_LABEL: Record<PerformanceBand, string> = {
  good: 'On top of it',
  watch: 'Needs a word',
  poor: 'Underperforming',
  no_data: 'No data yet',
}

const METRIC_LABELS: Record<string, string> = {
  meter_compliance: 'Meter readings',
  inspection_completion: 'Inspections finished',
  maintenance_response: 'Response time',
  cash_discipline: 'Cash traceability',
}

/** A 0–100 metric shown as a bar with its number, never colour alone. */
function MetricBar({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-sm text-slate-600">{label}</span>
        <span className="text-sm font-medium tabular-nums text-slate-800">
          {value === null ? 'No data' : `${value.toFixed(0)}%`}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full"
          style={{
            width: `${value ?? 0}%`,
            background: value === null ? '#cbd5e1' : value >= 80 ? SERIES.collected : value >= 60 ? SERIES.other : '#c0392b',
          }}
        />
      </div>
    </div>
  )
}

/**
 * Caretaker performance (US-058).
 *
 * The point is to make accountability objective: every number here comes from
 * work the caretaker either did or did not do on properties they were actually
 * assigned. A metric with no denominator — no metered units, no inspections due —
 * reads "no data" and is dropped from the score rather than counted as a zero,
 * so nobody is marked down for work that never existed.
 */
export function CaretakerPerformancePage() {
  const [windowDays, setWindowDays] = useState(30)
  const [detailFor, setDetailFor] = useState<CaretakerScore | null>(null)

  const scores = useQuery({
    queryKey: queryKeys.caretakerScores(windowDays),
    queryFn: () => caretakerPerformanceApi.list(windowDays),
  })

  const detail = useQuery({
    queryKey: queryKeys.caretakerScore(detailFor?.user_id ?? '', windowDays),
    queryFn: () => caretakerPerformanceApi.detail(detailFor!.user_id, windowDays),
    enabled: detailFor !== null,
  })

  const openJobs = useQuery({
    queryKey: ['caretaker', 'open-jobs', detailFor?.user_id],
    queryFn: () => caretakerPerformanceApi.openJobs(detailFor!.user_id),
    enabled: detailFor !== null,
  })

  if (scores.isPending) return <PageLoader />
  if (scores.isError) return <Alert tone="danger">{errorMessage(scores.error)}</Alert>

  const rows = scores.data

  return (
    <div>
      <PageHeader
        title="Caretaker performance"
        description="Objective numbers, so a conversation about performance is about the work rather than the impression."
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label="Window" className="w-48">
          <Select
            value={String(windowDays)}
            onChange={(event) => setWindowDays(Number(event.target.value))}
          >
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="180">Last 6 months</option>
          </Select>
        </Field>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={<UserRound className="h-6 w-6" />}
          title="No caretakers yet"
          description="Invite a caretaker and assign them properties; their numbers build from the work they record."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Everyone, whoever needs attention first</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Caretaker</Th>
                    <Th>Score</Th>
                    <Th>Meters</Th>
                    <Th>Inspections</Th>
                    <Th>Response</Th>
                    <Th>Cash</Th>
                    <Th>Last seen</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.user_id}>
                      <Td>
                        <button
                          type="button"
                          onClick={() => setDetailFor(row)}
                          className="font-medium text-brand-700 hover:underline"
                        >
                          {row.full_name}
                        </button>
                        <p className="text-xs text-slate-400">
                          {row.property_count} propert
                          {row.property_count === 1 ? 'y' : 'ies'} · {row.unit_count} units
                        </p>
                      </Td>
                      <Td>
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              'text-lg font-semibold tabular-nums',
                              row.band === 'good'
                                ? 'text-money-700'
                                : row.band === 'watch'
                                  ? 'text-warn-700'
                                  : row.band === 'poor'
                                    ? 'text-danger-700'
                                    : 'text-slate-400',
                            )}
                          >
                            {row.score === null ? '—' : row.score.toFixed(0)}
                          </span>
                          <Badge tone={BAND_TONE[row.band]}>{BAND_LABEL[row.band]}</Badge>
                        </div>
                      </Td>
                      {(
                        [
                          'meter_compliance',
                          'inspection_completion',
                          'maintenance_response',
                          'cash_discipline',
                        ] as const
                      ).map((key) => (
                        <Td key={key} className="tabular-nums text-slate-600">
                          {row.metrics[key] === null ? (
                            <span className="text-slate-400">—</span>
                          ) : (
                            `${row.metrics[key]!.toFixed(0)}%`
                          )}
                        </Td>
                      ))}
                      <Td className="text-sm text-slate-500">
                        {row.last_login_at ? relative(row.last_login_at) : 'Never signed in'}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>

            <p className="mt-3 text-xs text-slate-500">
              <Info className="mr-1 inline h-3.5 w-3.5" />
              The score weights meter readings 35%, inspections 25%, response time 25% and cash
              traceability 15%. A dash means there was nothing of that kind to do in this window,
              and it is left out of the score rather than counted against them.
            </p>
          </CardBody>
        </Card>
      )}

      <Dialog
        open={detailFor !== null}
        onClose={() => setDetailFor(null)}
        title={detailFor?.full_name ?? ''}
        description={
          detailFor
            ? `${detailFor.property_count} properties · ${detailFor.unit_count} units · last ${windowDays} days`
            : undefined
        }
        size="lg"
        footer={null}
      >
        {detail.isPending ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : detail.data ? (
          <div className="space-y-5">
            <div className="space-y-3">
              {Object.entries(detail.data.metrics).map(([key, value]) => (
                <MetricBar key={key} label={METRIC_LABELS[key] ?? key} value={value} />
              ))}
            </div>

            <dl className="grid grid-cols-2 gap-3 rounded-card bg-slate-50 p-3 text-sm">
              <div>
                <dt className="text-slate-500">Meter readings</dt>
                <dd className="font-medium">
                  {detail.data.detail.readings_taken} of {detail.data.detail.readings_due} due
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Inspections</dt>
                <dd className="font-medium">
                  {detail.data.detail.inspections_submitted} submitted of{' '}
                  {detail.data.detail.inspections_started} started
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Average first response</dt>
                <dd className="font-medium">
                  {detail.data.detail.average_response_hours === null
                    ? 'No requests'
                    : `${detail.data.detail.average_response_hours.toFixed(1)} hours`}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Cash held vs traceable</dt>
                <dd className="font-medium">
                  {kes(detail.data.detail.cash_collected)} /{' '}
                  {kes(detail.data.detail.traceable_collected)}
                </dd>
              </div>
            </dl>

            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">
                Trend — are they improving?
              </p>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={detail.data.trend}
                    margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                  >
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
                      width={36}
                    />
                    <Tooltip
                      formatter={(value) => (value === null ? 'No data' : `${value}`)}
                      contentStyle={TOOLTIP_STYLE}
                    />
                    <ReferenceLine y={80} stroke={REFERENCE} strokeDasharray="4 4" />
                    <Line
                      type="monotone"
                      dataKey="score"
                      name="Score"
                      stroke={SERIES.collected}
                      strokeWidth={2}
                      dot={{ r: 4, strokeWidth: 0, fill: SERIES.collected }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {(openJobs.data ?? []).length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">
                  <Clock className="mr-1 inline h-4 w-4 text-slate-400" />
                  Unacknowledged jobs dragging the response score down
                </p>
                <ul className="divide-y divide-slate-100">
                  {(openJobs.data ?? []).map((job) => (
                    <li key={job.id} className="flex items-center justify-between gap-3 py-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-slate-800">{job.title}</p>
                        <p className="text-xs text-slate-400">
                          {job.reference_code} · reported {dateTime(job.created_at)}
                        </p>
                      </div>
                      <Badge tone={job.hours_open > 96 ? 'danger' : 'warn'}>
                        {job.hours_open.toFixed(0)}h open
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.data.properties.length > 0 && (
              <p className="text-xs text-slate-500">
                Assigned to {detail.data.properties.map((p) => p.name).join(', ')}.
              </p>
            )}
          </div>
        ) : null}
      </Dialog>
    </div>
  )
}
