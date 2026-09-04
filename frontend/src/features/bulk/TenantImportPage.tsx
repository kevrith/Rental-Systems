import { useMutation } from '@tanstack/react-query'
import { AlertCircle, Check, Download, FileSpreadsheet, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { bulkApi } from '@/api'
import type { ImportPreview, ImportResult } from '@/api/types'
import { apiClient } from '@/lib/api-client'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { errorMessage, kes, shortDate } from '@/lib/format'

/** Upload, check, confirm — the operator sees every row before anything is written. */
export function TenantImportPage() {
  const fileInput = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const upload = useMutation({
    mutationFn: (file: File) => bulkApi.previewImport(file),
    onSuccess: (data) => {
      setPreview(data)
      setResult(null)
    },
    onError: (uploadError) => setError(errorMessage(uploadError)),
  })

  const commit = useMutation({
    mutationFn: () => bulkApi.commitImport(preview!.ready),
    onSuccess: (data) => {
      setResult(data)
      setPreview(null)
    },
    onError: (commitError) => setError(errorMessage(commitError)),
  })

  const downloadTemplate = async () => {
    setError(null)
    try {
      const response = await apiClient.get(bulkApi.templateUrl(), { responseType: 'blob' })
      const url = URL.createObjectURL(response.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'rentflow-tenant-import.xlsx'
      link.click()
      URL.revokeObjectURL(url)
    } catch (downloadError) {
      setError(errorMessage(downloadError))
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Import tenants"
        description="Bring your existing tenants across from a spreadsheet. Nothing is saved until you confirm."
        backTo="/bulk"
        backLabel="Bulk actions"
      />

      {result ? (
        <Card>
          <CardBody className="space-y-4 py-10 text-center">
            <Check className="mx-auto h-10 w-10 text-money-600" />
            <div>
              <p className="text-lg font-medium text-slate-900">
                {result.created} tenant{result.created === 1 ? '' : 's'} imported
              </p>
              {result.failed > 0 && (
                <p className="mt-1 text-sm text-danger-700">
                  {result.failed} row{result.failed === 1 ? '' : 's'} could not be saved.
                </p>
              )}
            </div>

            {result.failures.length > 0 && (
              <div className="mx-auto max-w-lg rounded-lg border border-danger-200 bg-danger-50 p-3 text-left">
                <ul className="space-y-1 text-sm text-danger-700">
                  {result.failures.map((failure) => (
                    <li key={failure.row}>
                      Row {failure.row}: {failure.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-center gap-2">
              <Link to="/tenants" className={linkButtonClass()}>
                See your tenants
              </Link>
              <Button
                variant="outline"
                onClick={() => {
                  setResult(null)
                  setFileName(null)
                }}
              >
                Import another file
              </Button>
            </div>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>1. Start from the template</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <p className="text-sm text-slate-600">
                The template has the columns the importer understands, with an example row and
                notes. Properties must already exist in RentFlow — units are created for you.
              </p>
              <Button
                variant="outline"
                icon={<Download className="h-4 w-4" />}
                onClick={downloadTemplate}
              >
                Download the template
              </Button>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. Upload your filled-in file</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <input
                ref={fileInput}
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  setError(null)
                  setFileName(file.name)
                  upload.mutate(file)
                }}
              />
              <Button
                icon={<Upload className="h-4 w-4" />}
                loading={upload.isPending}
                onClick={() => fileInput.current?.click()}
              >
                Choose a file
              </Button>
              {fileName && <p className="text-sm text-slate-500">{fileName}</p>}
              {error && (
                <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
                  {error}
                </Alert>
              )}
            </CardBody>
          </Card>

          {preview && (
            <Card>
              <CardHeader>
                <CardTitle>3. Check what will be created</CardTitle>
                <span className="text-sm text-slate-500">
                  {preview.ready_count} ready · {preview.error_count} with problems
                </span>
              </CardHeader>
              <CardBody className="space-y-4">
                {preview.errors.length > 0 && (
                  <div className="rounded-lg border border-danger-200 bg-danger-50 p-3">
                    <p className="text-sm font-medium text-danger-800">
                      These rows will be skipped
                    </p>
                    <ul className="mt-1 space-y-1 text-sm text-danger-700">
                      {preview.errors.map((row) => (
                        <li key={row.row}>
                          Row {row.row}: {row.reason}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-xs text-danger-700">
                      Fix them in the spreadsheet and upload again, or import the good rows now and
                      the rest later.
                    </p>
                  </div>
                )}

                {preview.ready.length > 0 ? (
                  <>
                    <div className="max-h-96 overflow-auto rounded-lg border border-slate-200">
                      <Table>
                        <thead>
                          <tr>
                            <Th>Tenant</Th>
                            <Th>Unit</Th>
                            <Th>Rent</Th>
                            <Th>From</Th>
                            <Th>Owes</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.ready.map((row) => (
                            <tr key={row.row}>
                              <Td>
                                <span className="font-medium text-slate-900">{row.full_name}</span>
                                <span className="block text-xs text-slate-500">
                                  {row.phone_number}
                                </span>
                              </Td>
                              <Td className="text-slate-600">
                                {row.property_name} {row.unit_number}
                                {!row.unit_exists && (
                                  <span className="ml-1 text-xs text-brand-600">(new unit)</span>
                                )}
                              </Td>
                              <Td>{kes(row.monthly_rent)}</Td>
                              <Td className="text-slate-500">{shortDate(row.start_date)}</Td>
                              <Td>
                                {Number(row.opening_balance) > 0 ? (
                                  <span className="text-danger-700">
                                    {kes(row.opening_balance)}
                                  </span>
                                ) : (
                                  '—'
                                )}
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>

                    <Alert tone="info" icon={<FileSpreadsheet className="h-4 w-4" />}>
                      Anything in the &quot;Owes&quot; column is raised as an opening invoice, so it
                      shows up in arrears and statements from day one.
                    </Alert>

                    <Button
                      size="lg"
                      loading={commit.isPending}
                      onClick={() => {
                        setError(null)
                        commit.mutate()
                      }}
                    >
                      Import {preview.ready_count} tenant{preview.ready_count === 1 ? '' : 's'}
                    </Button>
                  </>
                ) : (
                  <Alert tone="warn">
                    None of the rows can be imported yet. Fix the problems above and upload again.
                  </Alert>
                )}
              </CardBody>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
