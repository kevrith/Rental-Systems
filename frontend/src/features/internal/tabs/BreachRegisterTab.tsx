import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertOctagon,
  Bell,
  ChevronRight,
  Clock,
  Plus,
  ShieldCheck,
} from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import type { BreachRecord } from '@/api/types'
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
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const SEVERITY_TONE = {
  low: 'neutral',
  medium: 'info',
  high: 'warn',
  critical: 'danger',
} as const

const STATUS_TONE = {
  open: 'danger',
  contained: 'warn',
  notified: 'info',
  closed: 'success',
  no_notification_required: 'neutral',
} as const

const CATEGORIES = [
  'unauthorised_access',
  'data_loss',
  'ransomware',
  'accidental_disclosure',
  'insider_threat',
  'other',
]

const SEVERITIES = ['low', 'medium', 'high', 'critical']

const ADVANCE_STATUSES = [
  { value: 'contained', label: 'Mark contained' },
  { value: 'notified', label: 'Mark regulator notified' },
  { value: 'no_notification_required', label: 'No notification required' },
  { value: 'closed', label: 'Close breach' },
]

export function BreachRegisterTab() {
  const [openOnly, setOpenOnly] = useState(true)
  const [reporting, setReporting] = useState(false)
  const [selected, setSelected] = useState<BreachRecord | null>(null)

  const dashboard = useQuery({
    queryKey: queryKeys.internalBreachDashboard,
    queryFn: internalApi.breachDashboard,
  })

  const breaches = useQuery({
    queryKey: queryKeys.internalBreaches(openOnly),
    queryFn: () => internalApi.breaches(openOnly),
  })

  const d = dashboard.data

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          label="Open breaches"
          value={d ? String(d.open) : '—'}
          tone={d && d.open > 0 ? 'danger' : 'default'}
          icon={d && d.open > 0 ? <AlertOctagon className="h-4 w-4" /> : undefined}
        />
        <StatCard
          label="Awaiting notification"
          value={d ? String(d.awaiting_notification) : '—'}
          tone={d && d.awaiting_notification > 0 ? 'warn' : 'default'}
          icon={d && d.awaiting_notification > 0 ? <Clock className="h-4 w-4" /> : undefined}
        />
        <StatCard
          label="Overdue (72h passed)"
          value={d ? String(d.overdue) : '—'}
          tone={d && d.overdue > 0 ? 'danger' : 'default'}
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Button
            size="sm"
            variant={openOnly ? 'secondary' : 'ghost'}
            onClick={() => setOpenOnly(true)}
          >
            Open only
          </Button>
          <Button
            size="sm"
            variant={!openOnly ? 'secondary' : 'ghost'}
            onClick={() => setOpenOnly(false)}
          >
            All breaches
          </Button>
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setReporting(true)}>
          Report breach
        </Button>
      </div>

      {breaches.isPending ? (
        <PageLoader />
      ) : !breaches.data?.length ? (
        <EmptyState
          icon={<ShieldCheck className="h-6 w-6" />}
          title="No breaches recorded"
          description="Report a breach to start the Kenya DPA 72-hour notification clock."
        />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Summary</Th>
                  <Th>Severity</Th>
                  <Th>Status</Th>
                  <Th>72h clock</Th>
                  <Th>Detected</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {breaches.data.map((b) => (
                  <tr key={b.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <Td className="font-mono text-xs text-slate-500">{b.reference_code}</Td>
                    <Td className="max-w-xs truncate font-medium text-slate-900 dark:text-slate-100">
                      {b.summary}
                    </Td>
                    <Td>
                      <Badge tone={SEVERITY_TONE[b.severity]}>{b.severity}</Badge>
                    </Td>
                    <Td>
                      <Badge tone={STATUS_TONE[b.status]}>
                        {b.status.replace(/_/g, ' ')}
                      </Badge>
                    </Td>
                    <Td>
                      {b.status === 'open' || b.status === 'contained' ? (
                        <span
                          className={`text-sm font-semibold tabular-nums ${
                            b.hours_remaining < 0
                              ? 'text-danger-600'
                              : b.hours_remaining < 12
                                ? 'text-warn-600'
                                : 'text-slate-600'
                          }`}
                        >
                          {b.hours_remaining < 0
                            ? `${Math.abs(b.hours_remaining)}h overdue`
                            : `${b.hours_remaining}h left`}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </Td>
                    <Td>{shortDate(b.detected_at)}</Td>
                    <Td>
                      <button
                        type="button"
                        onClick={() => setSelected(b)}
                        className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                        aria-label="Open breach"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      {reporting && <ReportBreachDialog onClose={() => setReporting(false)} />}
      {selected && (
        <BreachDetailDialog breach={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}

function ReportBreachDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [category, setCategory] = useState('unauthorised_access')
  const [severity, setSeverity] = useState('medium')
  const [summary, setSummary] = useState('')
  const [detail, setDetail] = useState('')
  const [subjectCount, setSubjectCount] = useState('')

  const report = useMutation({
    mutationFn: () =>
      internalApi.reportBreach({
        category,
        severity,
        summary,
        detail: detail || null,
        affected_subject_count: subjectCount ? Number(subjectCount) : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['internal', 'breaches'] })
      queryClient.invalidateQueries({ queryKey: queryKeys.internalBreachDashboard })
      onClose()
    },
  })

  return (
    <Dialog open onClose={onClose} title="Report a data breach" size="lg">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          report.mutate()
        }}
      >
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-400">
          Reporting starts the Kenya DPA s.43 72-hour notification clock immediately.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, ' ')}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Severity">
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Summary">
          <Input
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            required
            minLength={10}
            maxLength={512}
          />
        </Field>
        <Field label="Detail (optional)">
          <Textarea
            value={detail}
            onChange={(e) => setDetail(e.target.value)}
            rows={4}
            maxLength={10000}
          />
        </Field>
        <Field label="Estimated affected subjects (optional)">
          <Input
            type="number"
            min={0}
            value={subjectCount}
            onChange={(e) => setSubjectCount(e.target.value)}
          />
        </Field>
        {report.isError && <Alert tone="danger">{errorMessage(report.error)}</Alert>}
        <Button type="submit" className="w-full" loading={report.isPending}>
          Report breach
        </Button>
      </form>
    </Dialog>
  )
}

function BreachDetailDialog({
  breach,
  onClose,
}: {
  breach: BreachRecord
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [advanceStatus, setAdvanceStatus] = useState('')
  const [note, setNote] = useState('')
  const [regulatorRef, setRegulatorRef] = useState('')
  const [notifyMsg, setNotifyMsg] = useState('')
  const [notifyMode, setNotifyMode] = useState(false)

  const advance = useMutation({
    mutationFn: () =>
      internalApi.advanceBreach(breach.id, {
        new_status: advanceStatus,
        note: note || null,
        regulator_reference: regulatorRef || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['internal', 'breaches'] })
      queryClient.invalidateQueries({ queryKey: queryKeys.internalBreachDashboard })
      onClose()
    },
  })

  const notify = useMutation({
    mutationFn: () => internalApi.notifyBreachCustomers(breach.id, notifyMsg),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['internal', 'breaches'] })
      setNotifyMode(false)
    },
  })

  const isClosed = breach.status === 'closed' || breach.status === 'no_notification_required'

  return (
    <Dialog open onClose={onClose} title={`Breach ${breach.reference_code}`} size="lg">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-slate-500">Status</p>
            <Badge tone={STATUS_TONE[breach.status]}>{breach.status.replace(/_/g, ' ')}</Badge>
          </div>
          <div>
            <p className="text-xs text-slate-500">Severity</p>
            <Badge tone={SEVERITY_TONE[breach.severity]}>{breach.severity}</Badge>
          </div>
          <div>
            <p className="text-xs text-slate-500">Detected</p>
            <p className="font-medium text-slate-900 dark:text-slate-100">
              {dateTime(breach.detected_at)}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Notification due</p>
            <p
              className={`font-medium ${breach.hours_remaining < 0 ? 'text-danger-600' : 'text-slate-900 dark:text-slate-100'}`}
            >
              {dateTime(breach.notification_due_at)}
              {!isClosed && (
                <span className="ml-1 text-xs">
                  ({breach.hours_remaining < 0
                    ? `${Math.abs(breach.hours_remaining)}h overdue`
                    : `${breach.hours_remaining}h left`})
                </span>
              )}
            </p>
          </div>
          {breach.affected_subject_count !== null && (
            <div>
              <p className="text-xs text-slate-500">Affected subjects</p>
              <p className="font-medium text-slate-900 dark:text-slate-100">
                {breach.affected_subject_count}
              </p>
            </div>
          )}
          {breach.regulator_reference && (
            <div>
              <p className="text-xs text-slate-500">Regulator reference</p>
              <p className="font-medium text-slate-900 dark:text-slate-100">
                {breach.regulator_reference}
              </p>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
          <p className="text-xs font-medium text-slate-500">Summary</p>
          <p className="mt-1 text-sm text-slate-800 dark:text-slate-200">{breach.summary}</p>
          {breach.detail && (
            <p className="mt-2 whitespace-pre-wrap text-xs text-slate-600 dark:text-slate-400">
              {breach.detail}
            </p>
          )}
        </div>

        {!isClosed && !notifyMode && (
          <div className="space-y-3">
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault()
                advance.mutate()
              }}
            >
              <Field label="Advance status">
                <Select
                  value={advanceStatus}
                  onChange={(e) => setAdvanceStatus(e.target.value)}
                  required
                >
                  <option value="">Select next status…</option>
                  {ADVANCE_STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </Field>
              {advanceStatus === 'notified' && (
                <Field label="Regulator reference number">
                  <Input
                    value={regulatorRef}
                    onChange={(e) => setRegulatorRef(e.target.value)}
                    required
                    placeholder="OPC/2024/…"
                  />
                </Field>
              )}
              <Field label="Note (optional)">
                <Textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                />
              </Field>
              {advance.isError && <Alert tone="danger">{errorMessage(advance.error)}</Alert>}
              <div className="flex gap-2">
                <Button type="submit" loading={advance.isPending} className="flex-1">
                  Advance breach
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  icon={<Bell className="h-4 w-4" />}
                  onClick={() => setNotifyMode(true)}
                >
                  Notify customers
                </Button>
              </div>
            </form>
          </div>
        )}

        {notifyMode && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              notify.mutate()
            }}
          >
            <Field
              label="Message to affected landlords"
              hint="Sent by email and SMS to owners/agency admins of affected organizations."
            >
              <Textarea
                value={notifyMsg}
                onChange={(e) => setNotifyMsg(e.target.value)}
                required
                minLength={20}
                rows={5}
              />
            </Field>
            {notify.isError && <Alert tone="danger">{errorMessage(notify.error)}</Alert>}
            {notify.isSuccess && (
              <Alert tone="success">Notifications sent.</Alert>
            )}
            <div className="flex gap-2">
              <Button type="submit" loading={notify.isPending} className="flex-1">
                Send notifications
              </Button>
              <Button variant="ghost" onClick={() => setNotifyMode(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>
    </Dialog>
  )
}
