import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, ShieldCheck, ShieldOff } from 'lucide-react'
import { useState } from 'react'

import { securityApi } from '@/api'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  PageLoader,
} from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

export function AuditLogTab() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [format, setFormat] = useState<'csv' | 'pdf'>('csv')
  const [exportError, setExportError] = useState<string | null>(null)

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
                Every audit entry is cryptographically chained to the previous one. A broken chain
                means a record was tampered with or deleted.
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
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                <p className="text-xs text-slate-500">Total entries</p>
                <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {v.total.toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                <p className="text-xs text-slate-500">Verified</p>
                <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {v.verified.toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                <p className="text-xs text-slate-500">Unchained</p>
                <p
                  className={`text-lg font-semibold ${v.unchained > 0 ? 'text-danger-600' : 'text-slate-900 dark:text-slate-100'}`}
                >
                  {v.unchained}
                </p>
              </div>
            </div>
          )}

          {v && !v.intact && v.broken_at_created_at && (
            <Alert tone="danger" className="mt-4">
              Chain broken at entry created {v.broken_at_created_at}. ID: {v.broken_at_id}
            </Alert>
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
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                Format
              </label>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as 'csv' | 'pdf')}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="csv">CSV</option>
                <option value="pdf">PDF</option>
              </select>
            </div>
            <Button
              icon={<Download className="h-4 w-4" />}
              loading={exportLog.isPending}
              onClick={() => {
                setExportError(null)
                exportLog.mutate()
              }}
            >
              Export
            </Button>
          </div>
          {exportError && (
            <Alert tone="danger" className="mt-3">
              {exportError}
            </Alert>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
