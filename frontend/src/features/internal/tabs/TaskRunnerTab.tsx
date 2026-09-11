import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Play, RefreshCw, XCircle } from 'lucide-react'
import { useState } from 'react'

import { tasksApi } from '@/api'
import type { ScheduledTask, TaskRun } from '@/api/types'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  PageLoader,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const HEALTH_TONE = {
  healthy: 'success',
  failing: 'danger',
  broken: 'danger',
  never_run: 'neutral',
} as const

export function TaskRunnerTab() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<ScheduledTask | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const overview = useQuery({
    queryKey: queryKeys.internalTaskOverview,
    queryFn: tasksApi.overview,
    refetchInterval: 30_000,
  })

  const history = useQuery({
    queryKey: queryKeys.taskHistory(selected?.task_name ?? ''),
    queryFn: () => tasksApi.history(selected!.task_name),
    enabled: Boolean(selected),
  })

  const run = useMutation({
    mutationFn: (taskName: string) => tasksApi.run(taskName),
    onSuccess: () => {
      setRunError(null)
      queryClient.invalidateQueries({ queryKey: queryKeys.internalTaskOverview })
      if (selected) {
        queryClient.invalidateQueries({ queryKey: queryKeys.taskHistory(selected.task_name) })
      }
    },
    onError: (err) => setRunError(errorMessage(err)),
  })

  if (overview.isPending) return <PageLoader />

  const tasks = overview.data?.tasks ?? []

  return (
    <div className="space-y-6">
      {/* Summary tiles */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Healthy', value: overview.data?.healthy ?? 0, tone: 'success' },
          { label: 'Failing', value: overview.data?.failing ?? 0, tone: overview.data?.failing ? 'danger' : 'neutral' },
          { label: 'Never run', value: overview.data?.never_run ?? 0, tone: 'neutral' },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{s.label}</p>
            <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{s.value}</p>
          </div>
        ))}
      </div>

      {runError && <Alert tone="danger">{runError}</Alert>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Task list */}
        <Card>
          <CardBody className="p-0 overflow-x-auto">
            <Table>
              <thead>
                <tr>
                  <Th>Task</Th>
                  <Th>Health</Th>
                  <Th>Last run</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-sm text-slate-400">
                      No tasks registered.
                    </td>
                  </tr>
                ) : (
                  tasks.map((task) => (
                    <tr
                      key={task.task_name}
                      className={`cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 ${
                        selected?.task_name === task.task_name
                          ? 'bg-brand-50 dark:bg-brand-950/30'
                          : ''
                      }`}
                      onClick={() => setSelected(task)}
                    >
                      <Td>
                        <p className="font-mono text-xs font-medium text-slate-800 dark:text-slate-200">
                          {task.task_name}
                        </p>
                        {task.schedule && (
                          <p className="text-[11px] text-slate-400">{task.schedule}</p>
                        )}
                      </Td>
                      <Td>
                        <Badge tone={HEALTH_TONE[task.health]}>{task.health.replace('_', ' ')}</Badge>
                      </Td>
                      <Td className="text-xs text-slate-500">
                        {task.last_run_at ? relative(task.last_run_at) : '—'}
                      </Td>
                      <Td>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Play className="h-3.5 w-3.5" />}
                          loading={run.isPending && run.variables === task.task_name}
                          onClick={(e) => {
                            e.stopPropagation()
                            run.mutate(task.task_name)
                          }}
                        >
                          Run
                        </Button>
                      </Td>
                    </tr>
                  ))
                )}
              </tbody>
            </Table>
          </CardBody>
        </Card>

        {/* History panel */}
        <Card>
          <CardBody>
            {!selected ? (
              <EmptyState
                title="Select a task"
                description="Click a task on the left to see its run history."
              />
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {selected.task_name}
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<RefreshCw className="h-3.5 w-3.5" />}
                    onClick={() =>
                      queryClient.invalidateQueries({
                        queryKey: queryKeys.taskHistory(selected.task_name),
                      })
                    }
                  >
                    Refresh
                  </Button>
                </div>

                {selected.last_error && (
                  <Alert tone="danger" className="text-xs">
                    {selected.last_error}
                  </Alert>
                )}

                {history.isPending ? (
                  <PageLoader />
                ) : !history.data?.length ? (
                  <p className="text-sm text-slate-400">No runs recorded yet.</p>
                ) : (
                  <div className="space-y-2">
                    {history.data.map((run: TaskRun) => (
                      <RunRow key={run.id} run={run} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}

function RunRow({ run }: { run: TaskRun }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className="rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800"
    >
      <button
        type="button"
        className="flex w-full items-center gap-3 px-3 py-2 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        {run.status === 'succeeded' ? (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-success-600" />
        ) : run.status === 'failed' ? (
          <XCircle className="h-4 w-4 shrink-0 text-danger-600" />
        ) : (
          <RefreshCw className="h-4 w-4 shrink-0 animate-spin text-brand-500" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-slate-800 dark:text-slate-200">
            {dateTime(run.started_at)}
            {run.triggered_manually && (
              <span className="ml-2 rounded bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700 dark:bg-brand-900 dark:text-brand-300">
                manual
              </span>
            )}
          </p>
          {run.duration_seconds !== null && (
            <p className="text-[11px] text-slate-400">{run.duration_seconds.toFixed(1)}s</p>
          )}
        </div>
      </button>
      {open && (run.result || run.error) && (
        <div className="border-t border-slate-200 px-3 py-2 dark:border-slate-700">
          {run.error && (
            <p className="whitespace-pre-wrap font-mono text-xs text-danger-600">{run.error}</p>
          )}
          {run.result && (
            <pre className="whitespace-pre-wrap font-mono text-xs text-slate-600 dark:text-slate-400">
              {JSON.stringify(run.result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
