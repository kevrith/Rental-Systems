import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CreditCard,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
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
import type { OrganizationHealthSummary, OrganizationSuspensionState } from '@/api/types'
import { StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  Field,
  PageLoader,
  Select,
  Table,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { errorMessage, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const PLAN_OPTIONS = ['free', 'starter', 'professional', 'business']

const TREND_BADGE = {
  improving: { tone: 'success' as const, icon: <TrendingUp className="mr-1 inline h-3 w-3" /> },
  declining: { tone: 'warn' as const, icon: <TrendingDown className="mr-1 inline h-3 w-3" /> },
  stable: { tone: 'neutral' as const, icon: null },
}

export function OrganizationsTab() {
  const [selected, setSelected] = useState<string | null>(null)
  const [suspendTarget, setSuspendTarget] = useState<OrganizationHealthSummary | null>(null)
  const [planTarget, setPlanTarget] = useState<OrganizationHealthSummary | null>(null)

  const orgs = useQuery({
    queryKey: queryKeys.internalOrganizations,
    queryFn: internalApi.organizations,
  })

  const history = useQuery({
    queryKey: queryKeys.internalOrganizationHealth(selected ?? ''),
    queryFn: () => internalApi.organizationHealthHistory(selected!),
    enabled: Boolean(selected),
  })

  if (orgs.isPending) return <PageLoader />

  const rows = orgs.data ?? []
  const atRisk = rows.filter((r) => r.is_at_risk).length
  const scored = rows.filter((r) => r.latest_score !== null)
  const avg = scored.length
    ? Math.round(scored.reduce((s, r) => s + (r.latest_score ?? 0), 0) / scored.length)
    : null

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Total organizations" value={String(rows.length)} />
        <StatCard label="Average health score" value={avg === null ? '—' : String(avg)} />
        <StatCard
          label="At risk"
          value={String(atRisk)}
          tone={atRisk > 0 ? 'danger' : 'default'}
          icon={atRisk > 0 ? <AlertTriangle className="h-4 w-4" /> : undefined}
        />
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No organizations yet" description="Health scores compute weekly." />
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
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.organization_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <Td className="font-medium text-slate-900 dark:text-slate-100">
                      <button
                        type="button"
                        className="flex items-center gap-2 text-left hover:underline"
                        onClick={() =>
                          setSelected(selected === row.organization_id ? null : row.organization_id)
                        }
                      >
                        {row.organization_name}
                        {selected === row.organization_id ? (
                          <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                        )}
                      </button>
                      {row.is_at_risk && (
                        <Badge tone="danger" className="ml-2">
                          At risk
                        </Badge>
                      )}
                    </Td>
                    <Td className="tabular-nums">{row.latest_score ?? '—'}</Td>
                    <Td>
                      {row.trend ? (
                        <Badge tone={TREND_BADGE[row.trend].tone}>
                          {TREND_BADGE[row.trend].icon}
                          {row.trend}
                        </Badge>
                      ) : (
                        '—'
                      )}
                    </Td>
                    <Td>{row.week_of ? shortDate(row.week_of) : '—'}</Td>
                    <Td>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<CreditCard className="h-3.5 w-3.5" />}
                          onClick={() => setPlanTarget(row)}
                        >
                          Plan
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Ban className="h-3.5 w-3.5" />}
                          onClick={() => setSuspendTarget(row)}
                        >
                          Suspend
                        </Button>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      {selected && (
        <Card>
          <CardBody>
            <p className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
              {rows.find((r) => r.organization_id === selected)?.organization_name} — score history
            </p>
            {history.isPending ? (
              <PageLoader />
            ) : history.data && history.data.length > 0 ? (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={[...history.data].reverse()}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-slate-100)" />
                    <XAxis dataKey="week_of" tickFormatter={(v) => shortDate(v)} fontSize={12} />
                    <YAxis domain={[0, 100]} fontSize={12} />
                    <Tooltip labelFormatter={(v) => shortDate(v as string)} />
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

      {suspendTarget && (
        <SuspendDialog org={suspendTarget} onClose={() => setSuspendTarget(null)} />
      )}
      {planTarget && (
        <PlanDialog org={planTarget} onClose={() => setPlanTarget(null)} />
      )}
    </div>
  )
}

function SuspendDialog({
  org,
  onClose,
}: {
  org: OrganizationHealthSummary
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const [notify, setNotify] = useState(true)
  const [mode, setMode] = useState<'suspend' | 'reactivate' | null>(null)

  const suspension = useQuery({
    queryKey: queryKeys.internalSuspension(org.organization_id),
    queryFn: () => internalApi.suspensionState(org.organization_id),
  })

  const suspend = useMutation({
    mutationFn: () =>
      internalApi.suspendOrganization(org.organization_id, { reason, notify_account: notify }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalSuspension(org.organization_id) })
      setMode(null)
      setReason('')
    },
  })

  const reactivate = useMutation({
    mutationFn: () => internalApi.reactivateOrganization(org.organization_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalSuspension(org.organization_id) })
      setMode(null)
    },
  })

  const state: OrganizationSuspensionState | undefined = suspension.data

  return (
    <Dialog open onClose={onClose} title={`Account status — ${org.organization_name}`} size="md">
      {suspension.isPending ? (
        <PageLoader />
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
            <div
              className={`h-3 w-3 rounded-full ${state?.is_active ? 'bg-success-500' : 'bg-danger-500'}`}
            />
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                {state?.is_active ? 'Active' : 'Suspended'}
              </p>
              {!state?.is_active && state?.suspension_reason && (
                <p className="text-xs text-slate-500">{state.suspension_reason}</p>
              )}
              {!state?.is_active && state?.suspended_at && (
                <p className="text-xs text-slate-400">Since {shortDate(state.suspended_at)}</p>
              )}
            </div>
          </div>

          {mode === 'suspend' && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault()
                suspend.mutate()
              }}
            >
              <Field label="Reason (shown to the account holder)">
                <Textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  minLength={5}
                  rows={3}
                  placeholder="Non-payment of subscription, abuse of platform, …"
                />
              </Field>
              <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <input
                  type="checkbox"
                  checked={notify}
                  onChange={(e) => setNotify(e.target.checked)}
                />
                Notify account owners by SMS and email
              </label>
              {suspend.isError && <Alert tone="danger">{errorMessage(suspend.error)}</Alert>}
              <div className="flex gap-2">
                <Button
                  type="submit"
                  variant="danger"
                  loading={suspend.isPending}
                  className="flex-1"
                >
                  Confirm suspension
                </Button>
                <Button variant="ghost" onClick={() => setMode(null)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {mode === 'reactivate' && (
            <div className="space-y-3">
              <p className="text-sm text-slate-600 dark:text-slate-400">
                This will restore access. Users will need to sign in again — their sessions were
                revoked when the account was suspended.
              </p>
              {reactivate.isError && (
                <Alert tone="danger">{errorMessage(reactivate.error)}</Alert>
              )}
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  icon={<CheckCircle2 className="h-4 w-4" />}
                  loading={reactivate.isPending}
                  onClick={() => reactivate.mutate()}
                  className="flex-1"
                >
                  Confirm reactivation
                </Button>
                <Button variant="ghost" onClick={() => setMode(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {mode === null && (
            <div className="flex gap-2">
              {state?.is_active ? (
                <Button
                  variant="danger"
                  icon={<Ban className="h-4 w-4" />}
                  onClick={() => setMode('suspend')}
                  className="flex-1"
                >
                  Suspend account
                </Button>
              ) : (
                <Button
                  variant="secondary"
                  icon={<CheckCircle2 className="h-4 w-4" />}
                  onClick={() => setMode('reactivate')}
                  className="flex-1"
                >
                  Reactivate account
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </Dialog>
  )
}

function PlanDialog({
  org,
  onClose,
}: {
  org: OrganizationHealthSummary
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [plan, setPlan] = useState('free')

  const update = useMutation({
    mutationFn: () => internalApi.updateOrganizationPlan(org.organization_id, plan),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalOrganizations })
      onClose()
    },
  })

  return (
    <Dialog open onClose={onClose} title={`Change plan — ${org.organization_name}`} size="sm">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          update.mutate()
        }}
      >
        <Field label="Subscription plan">
          <Select value={plan} onChange={(e) => setPlan(e.target.value)}>
            {PLAN_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </option>
            ))}
          </Select>
        </Field>
        {update.isError && <Alert tone="danger">{errorMessage(update.error)}</Alert>}
        <Button type="submit" className="w-full" loading={update.isPending}>
          Save plan
        </Button>
      </form>
    </Dialog>
  )
}
