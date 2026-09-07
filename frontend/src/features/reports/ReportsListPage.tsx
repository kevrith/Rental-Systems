import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FilePlus2, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { reportsApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  PageLoader,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { apiClient } from '@/lib/api-client'
import { dateTime, errorMessage, humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const SCHEDULE_TONE: Record<string, 'neutral' | 'brand'> = {
  none: 'neutral',
  weekly: 'brand',
  monthly: 'brand',
}

export function ReportsListPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const definitions = useQuery({ queryKey: queryKeys.reportDefinitions, queryFn: reportsApi.list })
  const monthly = useQuery({ queryKey: queryKeys.monthlyReports, queryFn: reportsApi.monthly })

  const run = useMutation({
    mutationFn: async (id: string) => {
      const response = await apiClient.post(`/reports/definitions/${id}/run`, undefined, {
        responseType: 'blob',
      })
      const disposition = String(response.headers['content-disposition'] ?? '')
      const match = disposition.match(/filename="?([^"]+)"?/)
      const url = URL.createObjectURL(response.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = match?.[1] ?? 'report'
      link.click()
      URL.revokeObjectURL(url)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.reportDefinitions }),
    onError: (runError) => setError(errorMessage(runError)),
  })

  const remove = useMutation({
    mutationFn: (id: string) => reportsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.reportDefinitions }),
    onError: (removeError) => setError(errorMessage(removeError)),
  })

  if (definitions.isPending) return <PageLoader />
  if (definitions.isError) return <Alert tone="danger">{errorMessage(definitions.error)}</Alert>

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Build custom reports from your own data, schedule them, and see every automatic monthly summary."
        actions={
          <Link to="/reports/new" className={linkButtonClass()}>
            <FilePlus2 className="h-4 w-4" />
            New report
          </Link>
        }
      />

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Saved reports</CardTitle>
        </CardHeader>
        <CardBody>
          {definitions.data.length === 0 ? (
            <EmptyState
              icon={<FilePlus2 className="h-6 w-6" />}
              title="No saved reports yet"
              description="Build one from any of your datasets — payments, tenancies, invoices and more."
              action={
                <Link to="/reports/new" className={linkButtonClass('primary', 'sm')}>
                  New report
                </Link>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Name</Th>
                    <Th>Dataset</Th>
                    <Th>Schedule</Th>
                    <Th>Last run</Th>
                    <Th></Th>
                  </tr>
                </thead>
                <tbody>
                  {definitions.data.map((report) => (
                    <tr key={report.id}>
                      <Td>
                        <Link
                          to={`/reports/${report.id}/edit`}
                          className="font-medium text-brand-700 hover:underline"
                        >
                          {report.name}
                        </Link>
                      </Td>
                      <Td className="text-slate-600">{humanize(report.dataset)}</Td>
                      <Td>
                        <Badge tone={SCHEDULE_TONE[report.schedule]}>{humanize(report.schedule)}</Badge>
                      </Td>
                      <Td className="text-slate-500">
                        {report.last_run_at ? dateTime(report.last_run_at) : 'Never'}
                      </Td>
                      <Td>
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            title="Run and download"
                            onClick={() => run.mutate(report.id)}
                            disabled={run.isPending}
                            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                          >
                            <Download className="h-4 w-4" />
                          </button>
                          <Link
                            to={`/reports/${report.id}/edit`}
                            title="Edit"
                            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                          >
                            <Pencil className="h-4 w-4" />
                          </Link>
                          <button
                            type="button"
                            title="Delete"
                            onClick={() => remove.mutate(report.id)}
                            disabled={remove.isPending}
                            className="rounded-md p-1.5 text-slate-500 hover:bg-danger-50 hover:text-danger-700"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Monthly summary history</CardTitle>
          <p className="mt-0.5 text-sm text-slate-500">
            Delivered automatically on the 1st of every month. Delivery destination is set in
            Settings.
          </p>
        </CardHeader>
        <CardBody>
          {!monthly.data || monthly.data.length === 0 ? (
            <EmptyState
              title="No monthly summaries yet"
              description="Your first automatic summary appears here after your first full calendar month."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Period</Th>
                    <Th>Delivered via</Th>
                    <Th>Delivered</Th>
                    <Th></Th>
                  </tr>
                </thead>
                <tbody>
                  {monthly.data.map((report) => (
                    <tr key={report.id}>
                      <Td>
                        {dateTime(report.period_start).split(',')[0]} —{' '}
                        {dateTime(report.period_end).split(',')[0]}
                      </Td>
                      <Td className="text-slate-600">
                        {report.delivered_channels.length > 0
                          ? report.delivered_channels.map(humanize).join(', ')
                          : '—'}
                      </Td>
                      <Td className="text-slate-500">
                        {report.delivered_at ? dateTime(report.delivered_at) : 'Pending'}
                      </Td>
                      <Td>
                        {report.download_url && (
                          <a
                            href={report.download_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"
                          >
                            <Download className="h-3.5 w-3.5" />
                            Download
                          </a>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
