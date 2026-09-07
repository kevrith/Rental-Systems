import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ClipboardCheck, Plus, Settings2, Trash2, XCircle } from 'lucide-react'
import { useState } from 'react'

import { approvalsApi } from '@/api'
import type { ApprovalRequestStatus } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Tab,
  Tabs,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const REQUEST_TABS: { value: ApprovalRequestStatus; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

/**
 * Configurable approval chains (Sprint 26A, item 13) — a generic maker-checker
 * mechanism a feature opts into by defining a rule for its own `entity_type`,
 * rather than writing its own one-off approval fields and logic. Cash payment
 * dual approval and maintenance cost sign-off predate this and are not routed
 * through it; a new threshold-gated action is the natural first user.
 */
export function ApprovalsPage() {
  const [view, setView] = useState<'requests' | 'rules'>('requests')

  return (
    <div>
      <PageHeader
        title="Approvals"
        description="Requests waiting on a second person's sign-off, and the rules that create them."
      />

      <Tabs value={view} onChange={(value) => setView(value as 'requests' | 'rules')} className="mb-4">
        <Tab value="requests">Requests</Tab>
        <Tab value="rules">Rules</Tab>
      </Tabs>

      {view === 'requests' ? <RequestsPanel /> : <RulesPanel />}
    </div>
  )
}

function RequestsPanel() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<ApprovalRequestStatus>('pending')
  const [error, setError] = useState<string | null>(null)

  const requests = useQuery({
    queryKey: queryKeys.approvalRequests(status),
    queryFn: () => approvalsApi.list({ status }),
  })

  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      action === 'approve' ? approvalsApi.approve(id) : approvalsApi.reject(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approvals', 'requests'] }),
    onError: (err) => setError(errorMessage(err)),
  })

  return (
    <div>
      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <Tabs value={status} onChange={(value) => setStatus(value as ApprovalRequestStatus)} className="mb-4">
        {REQUEST_TABS.map((tab) => (
          <Tab key={tab.value} value={tab.value}>
            {tab.label}
          </Tab>
        ))}
      </Tabs>

      {requests.isPending ? (
        <PageLoader />
      ) : requests.data && requests.data.length > 0 ? (
        <div className="space-y-3">
          {requests.data.map((request) => (
            <Card key={request.id}>
              <CardBody className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <Badge tone="brand">{humanize(request.entity_type)}</Badge>
                    {request.required_approvals > 1 && (
                      <Badge tone="neutral">Needs {request.required_approvals} approvals</Badge>
                    )}
                  </div>
                  <p className="text-sm text-slate-800 dark:text-slate-200">
                    Requested by {request.requested_by_name ?? 'someone no longer on the team'}
                    {request.trigger_value && <> · {kes(request.trigger_value)}</>}
                  </p>
                  {request.note && (
                    <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{request.note}</p>
                  )}
                  <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                    {dateTime(request.created_at)}
                  </p>
                </div>
                {status === 'pending' && (
                  <div className="flex shrink-0 gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<XCircle className="h-3.5 w-3.5" />}
                      loading={act.isPending}
                      onClick={() => act.mutate({ id: request.id, action: 'reject' })}
                    >
                      Reject
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                      loading={act.isPending}
                      onClick={() => act.mutate({ id: request.id, action: 'approve' })}
                    >
                      Approve
                    </Button>
                  </div>
                )}
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ClipboardCheck className="h-6 w-6" />}
          title="Nothing here"
          description="Requests appear here when an active rule's threshold is crossed."
        />
      )}
    </div>
  )
}

function RulesPanel() {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [entityType, setEntityType] = useState('')
  const [name, setName] = useState('')
  const [threshold, setThreshold] = useState('')
  const [requiredApprovals, setRequiredApprovals] = useState('1')
  const [error, setError] = useState<string | null>(null)

  const rules = useQuery({ queryKey: queryKeys.approvalRules, queryFn: approvalsApi.listRules })

  const create = useMutation({
    mutationFn: () =>
      approvalsApi.createRule({
        entity_type: entityType.trim(),
        name: name.trim(),
        threshold: threshold.trim() || null,
        required_approvals: Number(requiredApprovals) || 1,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.approvalRules })
      setCreating(false)
      setEntityType('')
      setName('')
      setThreshold('')
      setRequiredApprovals('1')
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      approvalsApi.updateRule(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.approvalRules }),
  })

  const remove = useMutation({
    mutationFn: (id: string) => approvalsApi.removeRule(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.approvalRules }),
  })

  return (
    <div>
      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {rules.isPending ? (
        <PageLoader />
      ) : (
        <div className="space-y-3">
          {rules.data?.map((rule) => (
            <Card key={rule.id}>
              <CardBody className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <Badge tone="brand">{humanize(rule.entity_type)}</Badge>
                    <Badge tone={rule.is_active ? 'success' : 'neutral'}>
                      {rule.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{rule.name}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {rule.threshold ? `Above ${kes(rule.threshold)}` : 'Always requires approval'} ·{' '}
                    {rule.required_approvals} approval{rule.required_approvals > 1 ? 's' : ''} required
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toggle.mutate({ id: rule.id, is_active: !rule.is_active })}
                  >
                    {rule.is_active ? 'Deactivate' : 'Activate'}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                    onClick={() => remove.mutate(rule.id)}
                  />
                </div>
              </CardBody>
            </Card>
          ))}

          {!rules.data?.length && !creating && (
            <EmptyState
              icon={<Settings2 className="h-6 w-6" />}
              title="No approval rules yet"
              description="A rule names what needs sign-off, and above what amount."
            />
          )}

          {creating ? (
            <Card>
              <CardBody className="grid gap-3 sm:grid-cols-2">
                <Field label="Entity type" hint="A short code your team recognises, e.g. large_expense">
                  <Input value={entityType} onChange={(event) => setEntityType(event.target.value)} />
                </Field>
                <Field label="Rule name">
                  <Input value={name} onChange={(event) => setName(event.target.value)} />
                </Field>
                <Field label="Threshold (KES)" hint="Leave blank to always require approval">
                  <Input
                    type="number"
                    value={threshold}
                    onChange={(event) => setThreshold(event.target.value)}
                  />
                </Field>
                <Field label="Approvals required">
                  <Select
                    value={requiredApprovals}
                    onChange={(event) => setRequiredApprovals(event.target.value)}
                  >
                    {[1, 2, 3].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </Field>
                <div className="flex gap-2 sm:col-span-2">
                  <Button
                    disabled={!entityType.trim() || !name.trim() || create.isPending}
                    loading={create.isPending}
                    onClick={() => create.mutate()}
                  >
                    Save rule
                  </Button>
                  <Button variant="ghost" onClick={() => setCreating(false)}>
                    Cancel
                  </Button>
                </div>
              </CardBody>
            </Card>
          ) : (
            <Button variant="outline" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
              New rule
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
