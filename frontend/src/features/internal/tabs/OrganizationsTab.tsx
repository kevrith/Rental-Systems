import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CreditCard,
  ExternalLink,
  Search,
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
import type { OrgDetail, OrganizationSuspensionState } from '@/api/types'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { errorMessage, humanize, relative, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const PLAN_TONE: Record<string, 'neutral' | 'info' | 'brand' | 'success' | 'warn' | 'danger'> = {
  trial: 'warn',
  free: 'neutral',
  starter: 'info',
  professional: 'brand',
  business: 'success',
}

const PLAN_OPTIONS = ['free', 'starter', 'professional', 'business']

export function OrganizationsTab() {
  const [search, setSearch] = useState('')
  const [planFilter, setPlanFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [suspendTarget, setSuspendTarget] = useState<OrgDetail | null>(null)
  const [planTarget, setPlanTarget] = useState<OrgDetail | null>(null)

  const params = {
    search: search || undefined,
    plan: planFilter || undefined,
    is_active: statusFilter === '' ? undefined : statusFilter === 'active',
  }

  const orgs = useQuery({
    queryKey: queryKeys.internalOrganizationsDetail(params),
    queryFn: () => internalApi.organizationsDetail(params),
  })

  const history = useQuery({
    queryKey: queryKeys.internalOrganizationHealth(expanded ?? ''),
    queryFn: () => internalApi.organizationHealthHistory(expanded!),
    enabled: Boolean(expanded),
  })

  const rows = orgs.data ?? []

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          value={planFilter}
          onChange={(e) => setPlanFilter(e.target.value)}
          className="w-40"
        >
          <option value="">All plans</option>
          {['trial', ...PLAN_OPTIONS].map((p) => (
            <option key={p} value={p}>
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </option>
          ))}
        </Select>
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-40"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </Select>
      </div>

      {orgs.isPending ? (
        <PageLoader />
      ) : rows.length === 0 ? (
        <EmptyState title="No organizations match" description="Try adjusting the filters." />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  <Th>Organization</Th>
                  <Th>Owner</Th>
                  <Th>Plan</Th>
                  <Th>Mode</Th>
                  <Th>Units</Th>
                  <Th>Tenants</Th>
                  <Th>Users</Th>
                  <Th>Joined</Th>
                  <Th>Status</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <>
                    <tr
                      key={row.id}
                      className="hover:bg-slate-50 dark:hover:bg-slate-800/50"
                    >
                      <Td>
                        <button
                          type="button"
                          className="flex items-center gap-1.5 text-left font-medium text-slate-900 hover:text-brand-700 dark:text-slate-100"
                          onClick={() => setExpanded(expanded === row.id ? null : row.id)}
                        >
                          {row.name}
                          {expanded === row.id ? (
                            <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                          )}
                        </button>
                      </Td>
                      <Td>
                        <p className="text-sm text-slate-800 dark:text-slate-200">
                          {row.owner_name ?? '—'}
                        </p>
                        {row.owner_email && (
                          <p className="text-xs text-slate-400">{row.owner_email}</p>
                        )}
                      </Td>
                      <Td>
                        <Badge tone={PLAN_TONE[row.subscription_plan] ?? 'neutral'}>
                          {row.subscription_plan}
                        </Badge>
                        {row.is_trial_expired && (
                          <Badge tone="danger" className="ml-1">expired</Badge>
                        )}
                      </Td>
                      <Td>
                        <span className="text-sm text-slate-600 dark:text-slate-400">
                          {humanize(row.operating_mode)}
                        </span>
                      </Td>
                      <Td className="tabular-nums text-slate-700 dark:text-slate-300">
                        {row.unit_count.toLocaleString()}
                      </Td>
                      <Td className="tabular-nums text-slate-700 dark:text-slate-300">
                        {row.tenant_count.toLocaleString()}
                      </Td>
                      <Td className="tabular-nums text-slate-700 dark:text-slate-300">
                        {row.user_count}
                      </Td>
                      <Td className="text-xs text-slate-500">{shortDate(row.created_at)}</Td>
                      <Td>
                        {row.is_active ? (
                          <Badge tone="success">Active</Badge>
                        ) : (
                          <Badge tone="danger">Suspended</Badge>
                        )}
                      </Td>
                      <Td>
                        <div className="flex items-center gap-1">
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
                            {row.is_active ? 'Suspend' : 'Reactivate'}
                          </Button>
                        </div>
                      </Td>
                    </tr>

                    {expanded === row.id && (
                      <tr key={`${row.id}-expand`}>
                        <td colSpan={10} className="bg-slate-50 px-6 py-4 dark:bg-slate-800/40">
                          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div className="space-y-1 text-sm">
                              <p className="font-semibold text-slate-700 dark:text-slate-300">
                                Account details
                              </p>
                              <Detail label="ID" value={row.id} mono />
                              <Detail label="Phone" value={row.owner_phone ?? '—'} />
                              <Detail
                                label="Trial ends"
                                value={row.trial_ends_at ? shortDate(row.trial_ends_at) : '—'}
                              />
                              {row.suspended_at && (
                                <Detail label="Suspended" value={shortDate(row.suspended_at)} />
                              )}
                            </div>
                            <div>
                              <p className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
                                Health score history
                              </p>
                              {history.isPending ? (
                                <PageLoader />
                              ) : history.data && history.data.length > 0 ? (
                                <div className="h-40">
                                  <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={[...history.data].reverse()}>
                                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-slate-200)" />
                                      <XAxis dataKey="week_of" tickFormatter={(v) => shortDate(v)} fontSize={11} />
                                      <YAxis domain={[0, 100]} fontSize={11} />
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
                                <p className="text-sm text-slate-400">No health data yet.</p>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </Table>
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

function Detail({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-24 shrink-0 text-xs text-slate-400">{label}</span>
      <span
        className={`truncate text-slate-800 dark:text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}
      >
        {value}
      </span>
    </div>
  )
}

function SuspendDialog({ org, onClose }: { org: OrgDetail; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const [notify, setNotify] = useState(true)
  const [mode, setMode] = useState<'suspend' | 'reactivate' | null>(null)

  const suspension = useQuery({
    queryKey: queryKeys.internalSuspension(org.id),
    queryFn: () => internalApi.suspensionState(org.id),
  })

  const suspend = useMutation({
    mutationFn: () =>
      internalApi.suspendOrganization(org.id, { reason, notify_account: notify }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalSuspension(org.id) })
      queryClient.invalidateQueries({ queryKey: ['internal', 'organizations', 'detail'] })
      setMode(null)
      setReason('')
    },
  })

  const reactivate = useMutation({
    mutationFn: () => internalApi.reactivateOrganization(org.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalSuspension(org.id) })
      queryClient.invalidateQueries({ queryKey: ['internal', 'organizations', 'detail'] })
      setMode(null)
    },
  })

  const state: OrganizationSuspensionState | undefined = suspension.data

  return (
    <Dialog open onClose={onClose} title={`Account status — ${org.name}`} size="md">
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
                <Button type="submit" variant="danger" loading={suspend.isPending} className="flex-1">
                  Confirm suspension
                </Button>
                <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
              </div>
            </form>
          )}

          {mode === 'reactivate' && (
            <div className="space-y-3">
              <p className="text-sm text-slate-600 dark:text-slate-400">
                This will restore access. Users will need to sign in again.
              </p>
              {reactivate.isError && <Alert tone="danger">{errorMessage(reactivate.error)}</Alert>}
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
                <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
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

function PlanDialog({ org, onClose }: { org: OrgDetail; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [plan, setPlan] = useState(org.subscription_plan)

  const update = useMutation({
    mutationFn: () => internalApi.updateOrganizationPlan(org.id, plan),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['internal', 'organizations', 'detail'] })
      onClose()
    },
  })

  return (
    <Dialog open onClose={onClose} title={`Change plan — ${org.name}`} size="sm">
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
