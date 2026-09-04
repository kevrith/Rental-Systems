import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileDown, ShieldCheck } from 'lucide-react'
import { useState } from 'react'

import { vacanciesApi } from '@/api'
import type { ExportFormat, ExportKind } from '@/api/types'
import { apiClient } from '@/lib/api-client'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Field,
  Input,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const DATASETS: { value: ExportKind; label: string; hint: string }[] = [
  { value: 'tenants', label: 'Tenants', hint: 'Everyone on your books, with their KYC details' },
  { value: 'tenancies', label: 'Tenancies', hint: 'Who lives where, on what terms' },
  { value: 'payments', label: 'Payments', hint: 'Every payment received, with M-Pesa codes' },
  { value: 'invoices', label: 'Invoices', hint: 'What was billed, paid and still owing' },
  { value: 'properties', label: 'Properties', hint: 'Your buildings and their settings' },
  { value: 'units', label: 'Units', hint: 'Every unit, its rent and its status' },
]

const DATE_FILTERED: ExportKind[] = ['payments', 'invoices']

/** Your data, on your terms — the anti-lock-in page (US-077). */
export function DataExportPage() {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<ExportKind>('tenants')
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [error, setError] = useState<string | null>(null)

  const history = useQuery({ queryKey: queryKeys.dataExports, queryFn: vacanciesApi.exports })

  const run = useMutation({
    mutationFn: async () => {
      const response = await apiClient.post(
        '/vacancies/exports',
        {
          kind,
          export_format: format,
          date_from: from || null,
          date_to: to || null,
        },
        { responseType: 'blob' },
      )
      const disposition = String(response.headers['content-disposition'] ?? '')
      const match = disposition.match(/filename="?([^"]+)"?/)
      const url = URL.createObjectURL(response.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = match?.[1] ?? `rentflow-${kind}.${format === 'csv' ? 'csv' : 'xlsx'}`
      link.click()
      URL.revokeObjectURL(url)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.dataExports }),
    onError: (runError) => setError(errorMessage(runError)),
  })

  const dataset = DATASETS.find((item) => item.value === kind)
  const supportsDates = DATE_FILTERED.includes(kind)

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Export your data"
        description="Everything in RentFlow is yours. Take it out whenever you like, in a format anything can read."
      />

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Build an export</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="What do you want?" hint={dataset?.hint}>
              <Select value={kind} onChange={(event) => setKind(event.target.value as ExportKind)}>
                {DATASETS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Format">
              <Select
                value={format}
                onChange={(event) => setFormat(event.target.value as ExportFormat)}
              >
                <option value="csv">CSV — opens anywhere</option>
                <option value="excel">Excel — formatted, with filters</option>
              </Select>
            </Field>
          </div>

          {supportsDates && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="From" hint="Optional">
                <Input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
              </Field>
              <Field label="To" hint="Optional">
                <Input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
              </Field>
            </div>
          )}

          {error && <Alert tone="danger">{error}</Alert>}

          <Button
            size="lg"
            icon={<Download className="h-4 w-4" />}
            loading={run.isPending}
            onClick={() => {
              setError(null)
              run.mutate()
            }}
          >
            Download
          </Button>

          <Alert tone="info" icon={<ShieldCheck className="h-4 w-4" />}>
            Every export is logged below, with who took it and when — this is your whole tenant
            book leaving the building.
          </Alert>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Export history</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {history.data?.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>When</Th>
                    <Th>What</Th>
                    <Th>Rows</Th>
                    <Th>By</Th>
                  </tr>
                </thead>
                <tbody>
                  {history.data.map((row) => (
                    <tr key={row.id}>
                      <Td className="text-slate-500">{dateTime(row.created_at)}</Td>
                      <Td>
                        {humanize(row.kind)}
                        <span className="ml-1 text-xs uppercase text-slate-400">
                          {row.export_format}
                        </span>
                      </Td>
                      <Td>{row.row_count}</Td>
                      <Td className="text-slate-500">{row.requested_by_name ?? '—'}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<FileDown className="h-6 w-6" />}
              title="Nothing exported yet"
              description="Exports you take are listed here for your own audit trail."
            />
          )}
        </CardBody>
      </Card>
    </div>
  )
}
