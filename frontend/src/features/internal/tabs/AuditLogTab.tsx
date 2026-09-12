import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, RefreshCw, ShieldCheck, ShieldOff } from 'lucide-react'
import { useState } from 'react'

import { internalApi, securityApi } from '@/api'
import type { AuditLogEntry } from '@/api/types'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Input,
  PageLoader,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { errorMessage, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const PAGE_SIZE = 50

export function AuditLogTab() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [format, setFormat] = useState<'csv' | 'pdf'>('csv')
  const [exportError, setExportError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)

  const params = {
    search: search || undefined,
    action: action || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    limit: PAGE_SIZE,
    offset,
  }

  const log = useQuery({
    queryKey: queryKeys.auditLog(params),
    queryFn: () => internalApi.auditLog(params),
  })

  const verify = useQuery({
    queryKey: queryKeys.auditVerify,
    queryFn: securityApi.verifyAuditLog,
  })

  const exportLog = useMutation({
    mutationFn: () =>
      securityApi.exportAuditLog({
        format,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit-log.${format}`
      a.click()
      URL.revokeObjectURL(url)
    },
    onError: (err) => setExportError(errorMessage(err)),
  })

  const v = verify.data
  const total = log.data?.total ?? 0
  const rows = log.data?.rows ?? []

  return (
    <div className="space-y-6">
      {/* Chain integrity */}
      <Card>
        <CardBody>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Audit chain integrity
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                Every audit entry is cryptographically chained. A broken chain means a record was
                tampered with or deleted.
              </p>
            </div>
            {verify.isPending ? (
              <PageLoader />
            ) : v ? (
              <div className="flex items-center gap-2">
                {v.intact ? (
                  <>
                    <ShieldCheck className="h-5 w-5 text-success-600" />
                    <Badge tone="success">Intact</Badge>
                  </>
                ) : (
                  <>
                    <ShieldOff className="h-5 w-5 text-danger-600" />
                    <Badge tone="danger">Broken</Badge>
                  </>
                )}
              </div>
            ) : null}
          </div>

          {v && (
            <div className="mt-4 grid grid-cols-3 gap-4">
              {[
                { label: 'Total entries', value: v.total.toLocaleString() },
                { label: 'Verified', value: v.verified.toLocaleString() },
                { label: 'Unchained', value: v.unchained, danger: v.unchained > 0 },
              ].map((s) => (
                <div
                  key={s.label}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800"
                >
                  <p className="text-xs text-slate-500">{s.label}</p>
                  <p
                    className={`text-lg font-semibold ${
                      'danger' in s && s.danger
                        ? 'text-danger-600'
                        : 'text-slate-900 dark:text-slate-100'
                    }`}
                  >
                    {s.value}
                  </p>
                </div>
              ))}
            </div>
          )}

          {v && !v.intact && v.broken_at_created_at && (
            <Alert tone="danger" className="mt-4">
              Chain broken at entry created {v.broken_at_created_at}. ID: {v.broken_at_id}
            </Alert>
          )}
        </CardBody>
      </Card>

      {/* Live log viewer */}
      <Card>
        <CardBody>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Input
              className="min-w-48 flex-1"
              placeholder="Search action or summary…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setOffset(0) }}
            />
            <Input
              className="w-52"
              placeholder="Filter by action (e.g. payment.created)"
              value={action}
              onChange={(e) => { setAction(e.target.value); setOffset(0) }}
            />
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => { setDateFrom(e.target.value); setOffset(0) }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => { setDateTo(e.target.value); setOffset(0) }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <Button
              size="sm"
              variant="ghost"
              icon={<RefreshCw className="h-3.5 w-3.5" />}
              loading={log.isFetching}
              onClick={() => log.refetch()}
            >
              Refresh
            </Button>
          </div>

          {log.isPending ? (
            <PageLoader />
          ) : rows.length === 0 ? (
            <EmptyState title="No entries found" description="Try adjusting the filters." />
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>When</Th>
                      <Th>Action</Th>
                      <Th>Actor</Th>
                      <Th>Entity</Th>
                      <Th>Summary</Th>
                      <Th>IP</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row: AuditLogEntry) => (
                      <tr key={row.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                        <Td className="whitespace-nowrap text-xs text-slate-400">
                          {relative(row.created_at)}
                        </Td>
                        <Td>
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {row.action}
                          </span>
                        </Td>
                        <Td className="text-sm text-slate-700 dark:text-slate-300">
                          {row.actor_name ?? <span className="text-slate-400">system</span>}
                        </Td>
                        <Td className="text-xs text-slate-500">
                          {row.entity_type}
                          {row.entity_id && (
                            <span className="ml-1 font-mono text-slate-400">
                              {row.entity_id.slice(0, 8)}…
                            </span>
                          )}
                        </Td>
                        <Td className="max-w-xs truncate text-sm text-slate-600 dark:text-slate-400">
                          {row.summary ?? '—'}
                        </Td>
                        <Td className="font-mono text-xs text-slate-400">
                          {row.ip_address ?? '—'}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>

              {/* Pagination */}
              <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                <span>
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardBody>
      </Card>

      {/* Export */}
      <Card>
        <CardBody>
          <p className="mb-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
            Export audit log
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Format</label>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as 'csv' | 'pdf')}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="csv">CSV</option>
                <option value="pdf">PDF</option>
              </select>
            </div>
            <Button
              icon={<Download className="h-4 w-4" />}
              loading={exportLog.isPending}
              onClick={() => { setExportError(null); exportLog.mutate() }}
            >
              Export
            </Button>
          </div>
          {exportError && <Alert tone="danger" className="mt-3">{exportError}</Alert>}
        </CardBody>
      </Card>
    </div>
  )
}
