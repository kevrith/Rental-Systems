import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, TrendingDown, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { internalApi } from '@/api'
import type { HealthTrend } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import { Badge, Card, CardBody, EmptyState, PageLoader, Table, Td, Th } from '@/components/ui'
import { shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const TREND_BADGE: Record<HealthTrend, { tone: 'success' | 'warn' | 'neutral'; label: string }> = {
  improving: { tone: 'success', label: 'Improving' },
  declining: { tone: 'warn', label: 'Declining' },
  stable: { tone: 'neutral', label: 'Stable' },
}

/** RentFlow's internal customer-health dashboard (US-091) — cross-organization,
 * visible only to `is_platform_staff` accounts (see `ProtectedRoute`'s
 * `requirePlatformStaff`). Every other screen in this app is scoped to one
 * tenant; this one deliberately is not. */
export function CustomerHealthPage() {
  const [selected, setSelected] = useState<string | null>(null)

  const organizations = useQuery({
    queryKey: queryKeys.internalOrganizations,
    queryFn: internalApi.organizations,
  })

  const history = useQuery({
    queryKey: queryKeys.internalOrganizationHealth(selected ?? ''),
    queryFn: () => internalApi.organizationHealthHistory(selected as string),
    enabled: Boolean(selected),
  })

  if (organizations.isPending) return <PageLoader />

  const rows = organizations.data ?? []
  const atRisk = rows.filter((row) => row.is_at_risk).length
  const scored = rows.filter((row) => row.latest_score !== null)
  const average = scored.length
    ? Math.round(scored.reduce((sum, row) => sum + (row.latest_score ?? 0), 0) / scored.length)
    : null

  return (
    <div>
      <PageHeader
        title="Customer health"
        description="Weekly health score across every organization on the platform."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Organizations" value={String(rows.length)} />
        <StatCard label="Average score" value={average === null ? '—' : String(average)} />
        <StatCard
          label="At risk"
          value={String(atRisk)}
          tone={atRisk > 0 ? 'danger' : 'default'}
          icon={atRisk > 0 ? <AlertTriangle className="h-4 w-4" /> : undefined}
        />
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No health scores yet" description="Scores compute weekly, every Monday." />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  <Th>Organization</Th>
                  <Th>Score</Th>
                  <Th>Trend</Th>
                  <Th>Week of</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.organization_id}
                    onClick={() => setSelected(row.organization_id)}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <Td className="font-medium text-slate-900">
                      {row.organization_name}
                      {row.is_at_risk && (
                        <Badge tone="danger" className="ml-2">
                          At risk
                        </Badge>
                      )}
                    </Td>
                    <Td>{row.latest_score ?? '—'}</Td>
                    <Td>
                      {row.trend ? (
                        <Badge tone={TREND_BADGE[row.trend].tone}>
                          {row.trend === 'improving' ? (
                            <TrendingUp className="mr-1 inline h-3 w-3" />
                          ) : row.trend === 'declining' ? (
                            <TrendingDown className="mr-1 inline h-3 w-3" />
                          ) : null}
                          {TREND_BADGE[row.trend].label}
                        </Badge>
                      ) : (
                        '—'
                      )}
                    </Td>
                    <Td>{row.week_of ? shortDate(row.week_of) : '—'}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      {selected && (
        <Card className="mt-6">
          <CardBody>
            <p className="mb-3 text-sm font-medium text-slate-900">
              {rows.find((row) => row.organization_id === selected)?.organization_name} — score history
            </p>
            {history.isPending ? (
              <PageLoader />
            ) : history.data && history.data.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={[...history.data].reverse()}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-slate-100)" />
                    <XAxis dataKey="week_of" tickFormatter={(value) => shortDate(value)} fontSize={12} />
                    <YAxis domain={[0, 100]} fontSize={12} />
                    <Tooltip labelFormatter={(value) => shortDate(value as string)} />
                    <Line
                      type="monotone"
                      dataKey="score"
                      stroke="var(--color-brand-600)"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-slate-500">No history yet.</p>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  )
}
