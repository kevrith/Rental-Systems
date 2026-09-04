import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleSlash, Play, RefreshCw, TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { tasksApi } from '@/api'
import type { ScheduledTask, TaskHealth } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  PageLoader,
  Table,
  Td,
  Th,
  type BadgeTone,
} from '@/components/ui'
import { dateTime, errorMessage, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const HEALTH_TONE: Record<TaskHealth, BadgeTone> = {
  healthy: 'success',
  failing: 'warn',
  broken: 'danger',
  never_run: 'neutral',
}

const HEALTH_LABEL: Record<TaskHealth, string> = {
  healthy: 'Healthy',
  failing: 'Some failures',
  broken: 'Broken',
  never_run: 'Never run',
}

/** `{"sent": 7, "skipped": 2}` -> `sent 7 · skipped 2`. */
function describeResult(result: Record<string, unknown> | null): string {
  if (!result) return '—'
  const parts = Object.entries(result).map(([key, value]) => `${key.replace(/_/g, ' ')} ${value}`)
  return parts.length ? parts.join(' · ') : '—'
}

/**
 * Scheduled task monitoring (US-056).
 *
 * The background jobs are what makes the product run without anyone logging in;
 * this is how you find out one of them stopped. A task is "broken" only after
 * several consecutive failures — a single blip is noise, a week of silence is
 * why nobody was invoiced.
 */
export function TaskMonitorPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [detailFor, setDetailFor] = useState<ScheduledTask | null>(null)

  const isSystemAdmin = useAuthStore((state) => state.user?.role === 'system_admin')

  const overview = useQuery({
    queryKey: queryKeys.scheduledTasks,
    queryFn: tasksApi.overview,
    // These change on their own schedule, so poll rather than sit on stale data.
    refetchInterval: 60_000,
  })

  const history = useQuery({
    queryKey: queryKeys.taskHistory(detailFor?.task_name ?? ''),
    queryFn: () => tasksApi.history(detailFor!.task_name),
    enabled: detailFor !== null,
  })

  const runNow = useMutation({
    mutationFn: (taskName: string) => tasksApi.run(taskName),
    onSuccess: async (result) => {
      setError(null)
      setNotice(`${result.task_name} queued. Refresh in a moment to see the result.`)
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (overview.isPending) return <PageLoader />
  if (overview.isError) return <Alert tone="danger">{errorMessage(overview.error)}</Alert>

  const data = overview.data
  const problems = data.tasks.filter((task) => task.health === 'broken')

  return (
    <div>
      <PageHeader
        title="Scheduled tasks"
        description="Invoicing, reminders, late fees, renewals and disbursements all run on their own. This is where you check that they did."
        actions={
          <Button
            variant="outline"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={() => void overview.refetch()}
          >
            Refresh
          </Button>
        }
      />

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}
      {notice && (
        <Alert tone="success" className="mb-4">
          {notice}
        </Alert>
      )}

      {problems.length > 0 && (
        <Alert tone="danger" className="mb-4">
          <TriangleAlert className="mr-1.5 inline h-4 w-4" />
          {problems.length} task{problems.length === 1 ? ' has' : 's have'} failed every recent run:{' '}
          {problems.map((task) => task.task_name).join(', ')}.
        </Alert>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <StatCard label="Healthy" value={String(data.healthy)} tone="success" />
        <StatCard
          label="Failing"
          value={String(data.failing)}
          tone={data.failing > 0 ? 'danger' : 'default'}
        />
        <StatCard
          label="Never run"
          value={String(data.never_run)}
          hint="Scheduled but no record of a run yet"
        />
      </div>

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Every task</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <Th>Task</Th>
                  <Th>Health</Th>
                  <Th>Last run</Th>
                  <Th>What it did</Th>
                  <Th>7 days</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((task) => (
                  <tr key={task.task_name}>
                    <Td>
                      <button
                        type="button"
                        onClick={() => setDetailFor(task)}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {task.task_name.replace('rentflow.', '')}
                      </button>
                      <p className="text-xs text-slate-400">
                        {task.scheduled ? task.schedule : 'Not in the schedule'}
                      </p>
                    </Td>
                    <Td>
                      <Badge tone={HEALTH_TONE[task.health]}>{HEALTH_LABEL[task.health]}</Badge>
                    </Td>
                    <Td className="text-sm text-slate-600">
                      {task.last_run_at ? (
                        <>
                          {relative(task.last_run_at)}
                          {task.last_duration_seconds !== null && (
                            <span className="block text-xs text-slate-400">
                              took {task.last_duration_seconds.toFixed(1)}s
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-slate-400">
                          <CircleSlash className="mr-1 inline h-3.5 w-3.5" />
                          Never
                        </span>
                      )}
                    </Td>
                    <Td className="max-w-xs text-sm text-slate-600">
                      {task.last_error ? (
                        <span className="text-danger-700">{task.last_error}</span>
                      ) : (
                        describeResult(task.last_result)
                      )}
                    </Td>
                    <Td className="text-sm tabular-nums text-slate-500">
                      {task.runs_7d} run{task.runs_7d === 1 ? '' : 's'}
                      {task.failures_7d > 0 && (
                        <span className="block text-xs text-danger-600">
                          {task.failures_7d} failed
                        </span>
                      )}
                    </Td>
                    <Td>
                      {isSystemAdmin && task.scheduled && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={runNow.isPending && runNow.variables === task.task_name}
                          icon={<Play className="h-3.5 w-3.5" />}
                          onClick={() => {
                            setError(null)
                            setNotice(null)
                            runNow.mutate(task.task_name)
                          }}
                        >
                          Run now
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent runs</CardTitle>
        </CardHeader>
        <CardBody>
          {data.recent_runs.length === 0 ? (
            <p className="text-sm text-slate-500">
              Nothing has run yet. Tasks appear here as Celery Beat fires them.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.recent_runs.map((run) => (
                <li key={run.id} className="flex items-start justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800">
                      {run.task_name.replace('rentflow.', '')}
                      {run.triggered_manually && (
                        <Badge tone="neutral" className="ml-2">
                          Manual
                        </Badge>
                      )}
                    </p>
                    <p className="text-xs text-slate-500">
                      {run.error ? (
                        <span className="text-danger-700">{run.error}</span>
                      ) : (
                        describeResult(run.result)
                      )}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <Badge
                      tone={
                        run.status === 'succeeded'
                          ? 'success'
                          : run.status === 'failed'
                            ? 'danger'
                            : 'info'
                      }
                    >
                      {run.status === 'succeeded' && (
                        <CheckCircle2 className="mr-1 inline h-3 w-3" />
                      )}
                      {run.status}
                    </Badge>
                    <p className="mt-0.5 text-xs text-slate-400">{dateTime(run.started_at)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Dialog
        open={detailFor !== null}
        onClose={() => setDetailFor(null)}
        title={detailFor?.task_name.replace('rentflow.', '') ?? ''}
        description={detailFor?.scheduled ? `Runs ${detailFor.schedule}` : 'Not in the schedule'}
        size="lg"
        footer={
          <Button variant="ghost" onClick={() => setDetailFor(null)}>
            Close
          </Button>
        }
      >
        {history.isPending ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (history.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">No runs recorded yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {(history.data ?? []).map((run) => (
              <li key={run.id} className="py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-slate-700">{dateTime(run.started_at)}</span>
                  <Badge
                    tone={
                      run.status === 'succeeded'
                        ? 'success'
                        : run.status === 'failed'
                          ? 'danger'
                          : 'info'
                    }
                  >
                    {run.status}
                  </Badge>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  {run.error ? (
                    <span className="text-danger-700">{run.error}</span>
                  ) : (
                    describeResult(run.result)
                  )}
                  {run.duration_seconds !== null && ` · ${run.duration_seconds.toFixed(1)}s`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </div>
  )
}
