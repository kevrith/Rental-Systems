import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { paymentsApi, tenanciesApi } from '@/api'
import type { BankStatementCommitRow, BankStatementRow } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

type ReviewRow = BankStatementRow & { tenancy_id: string; record_payment: boolean }

/**
 * Bank statement upload and reconciliation (Sprint 23, US-101).
 *
 * A row is only ever a proposal: matching by reference code fills in a
 * tenancy, but nothing is recorded as a payment until this screen's operator
 * confirms it, row by row.
 */
export function BankReconciliationPage() {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [rows, setRows] = useState<ReviewRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const tenancies = useQuery({
    queryKey: queryKeys.tenancies({ forReconciliation: true }),
    queryFn: () => tenanciesApi.list({ tenancy_status: 'active' }),
  })
  const history = useQuery({ queryKey: queryKeys.bankStatements, queryFn: paymentsApi.bankStatements })

  const preview = useMutation({
    mutationFn: (file: File) => paymentsApi.previewBankStatement(file),
    onSuccess: (result) => {
      setError(null)
      setNotice(null)
      setRows(
        result.rows.map((row) => ({
          ...row,
          tenancy_id: row.matched_tenancy_id ?? '',
          record_payment: Boolean(row.matched_tenancy_id),
        })),
      )
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const commit = useMutation({
    mutationFn: (reviewed: ReviewRow[]) => {
      const payload: BankStatementCommitRow[] = reviewed.map((row) => ({
        row: row.row,
        entry_date: row.entry_date,
        description: row.description,
        amount: row.amount,
        tenancy_id: row.tenancy_id || null,
        record_payment: row.record_payment && Boolean(row.tenancy_id),
      }))
      return paymentsApi.commitBankStatement(payload)
    },
    onSuccess: async (result) => {
      setError(null)
      setNotice(
        `Saved: ${result.upload.matched_count} matched, ${result.upload.unmatched_count} unmatched.` +
          (result.payment_failures.length
            ? ` ${result.payment_failures.length} payment(s) could not be recorded.`
            : ''),
      )
      setRows(null)
      if (fileInput.current) fileInput.current.value = ''
      await queryClient.invalidateQueries({ queryKey: queryKeys.bankStatements })
      await queryClient.invalidateQueries({ queryKey: ['payments'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const updateRow = (index: number, patch: Partial<ReviewRow>) =>
    setRows((current) =>
      current ? current.map((row, i) => (i === index ? { ...row, ...patch } : row)) : current,
    )

  return (
    <div>
      <PageHeader
        title="Bank statement reconciliation"
        description="Upload a bank statement to match deposits against tenancies and record them as payments."
        backTo="/payments"
        backLabel="Payments"
      />

      {error && (
        <Alert tone="danger" className="mb-4" icon={<AlertCircle className="h-4 w-4" />}>
          {error}
        </Alert>
      )}
      {notice && (
        <Alert tone="success" className="mb-4">
          {notice}
        </Alert>
      )}

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Upload a statement</CardTitle>
          <p className="mt-0.5 text-sm text-slate-500">
            CSV or Excel, with a date, description and amount (or credit) column. Only credit lines are
            read — nothing is recorded until you confirm below.
          </p>
        </CardHeader>
        <CardBody>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) preview.mutate(file)
            }}
            className="block text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
          />
          {preview.isPending && <p className="mt-2 text-sm text-slate-500">Reading the statement…</p>}
        </CardBody>
      </Card>

      {rows && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle>Review {rows.length} row(s)</CardTitle>
          </CardHeader>
          <CardBody>
            <Table>
              <thead>
                <tr>
                  <Th>Date</Th>
                  <Th>Description</Th>
                  <Th>Amount</Th>
                  <Th>Matched tenancy</Th>
                  <Th>Record now</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={row.row}>
                    <Td className="whitespace-nowrap text-sm text-slate-500">{row.entry_date}</Td>
                    <Td className="max-w-xs text-sm text-slate-700">{row.description}</Td>
                    <Td className="tabular-nums">{kes(row.amount)}</Td>
                    <Td>
                      <Select
                        value={row.tenancy_id}
                        onChange={(event) =>
                          updateRow(index, {
                            tenancy_id: event.target.value,
                            record_payment: Boolean(event.target.value),
                          })
                        }
                      >
                        <option value="">— unmatched —</option>
                        {tenancies.data?.map((tenancy) => (
                          <option key={tenancy.id} value={tenancy.id}>
                            {tenancy.reference_code} — {tenancy.tenant_name} ({tenancy.unit_number})
                          </option>
                        ))}
                      </Select>
                    </Td>
                    <Td>
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-brand-600"
                        checked={row.record_payment}
                        disabled={!row.tenancy_id}
                        onChange={(event) => updateRow(index, { record_payment: event.target.checked })}
                      />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>

            <Button
              className="mt-4"
              icon={<Upload className="h-4 w-4" />}
              loading={commit.isPending}
              onClick={() => commit.mutate(rows)}
            >
              Confirm and save
            </Button>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Past uploads</CardTitle>
        </CardHeader>
        <CardBody>
          {history.isPending ? (
            <PageLoader />
          ) : history.data && history.data.length > 0 ? (
            <Table>
              <thead>
                <tr>
                  <Th>Uploaded</Th>
                  <Th>Rows</Th>
                  <Th>Matched</Th>
                  <Th>Unmatched</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {history.data.map((upload) => (
                  <tr key={upload.id}>
                    <Td className="text-sm text-slate-500">{dateTime(upload.created_at)}</Td>
                    <Td className="tabular-nums">{upload.row_count}</Td>
                    <Td className="tabular-nums text-money-700">{upload.matched_count}</Td>
                    <Td className="tabular-nums text-warn-700">{upload.unmatched_count}</Td>
                    <Td>
                      <Link to={`/payments/bank-statements/${upload.id}`} className="text-sm text-brand-600">
                        View
                      </Link>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="text-sm text-slate-500">No statements uploaded yet.</p>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

export function BankStatementDetailPage() {
  const { uploadId } = useParams<{ uploadId: string }>()
  const detail = useQuery({
    queryKey: queryKeys.bankStatement(uploadId ?? ''),
    queryFn: () => paymentsApi.bankStatement(uploadId!),
    enabled: Boolean(uploadId),
  })

  if (detail.isPending) return <PageLoader />
  if (!detail.data) return null

  return (
    <div>
      <PageHeader
        title="Statement detail"
        description={`Uploaded ${dateTime(detail.data.created_at)}`}
        backTo="/payments/bank-statements"
        backLabel="Reconciliation"
      />
      <Card>
        <CardBody>
          <Table>
            <thead>
              <tr>
                <Th>Date</Th>
                <Th>Description</Th>
                <Th>Amount</Th>
                <Th>Matched</Th>
              </tr>
            </thead>
            <tbody>
              {detail.data.entries.map((entry) => (
                <tr key={entry.id}>
                  <Td className="text-sm text-slate-500">{entry.entry_date}</Td>
                  <Td className="max-w-xs text-sm text-slate-700">{entry.description}</Td>
                  <Td className="tabular-nums">{kes(entry.amount)}</Td>
                  <Td>
                    {entry.is_matched ? (
                      <CheckCircle2 className="h-4 w-4 text-money-600" />
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardBody>
      </Card>
    </div>
  )
}
