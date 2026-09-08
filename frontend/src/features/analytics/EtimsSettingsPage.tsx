import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, RefreshCw, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { etimsApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const STATUS_TONE = {
  submitted: 'success',
  pending: 'warn',
  failed: 'warn',
  abandoned: 'danger',
} as const

/**
 * KRA eTIMS settings and submission report (US-053).
 *
 * Two jobs on one screen: hold the landlord's eTIMS registration, and answer
 * "is every receipt actually reaching KRA?". The second matters more day to day —
 * an undeclared receipt is the landlord's compliance exposure, not ours, so the
 * failures are listed by name with a retry rather than buried in a count.
 */
export function EtimsSettingsPage() {
  const queryClient = useQueryClient()

  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [kraPin, setKraPin] = useState('')
  const [deviceSerial, setDeviceSerial] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [branchId, setBranchId] = useState('00')
  const [environment, setEnvironment] = useState('sandbox')

  const credentials = useQuery({
    queryKey: queryKeys.etimsCredentials,
    queryFn: etimsApi.credentials,
  })
  const report = useQuery({ queryKey: queryKeys.etimsReport, queryFn: etimsApi.report })

  const save = useMutation({
    mutationFn: () =>
      etimsApi.saveCredentials({
        kra_pin: kraPin.trim().toUpperCase(),
        device_serial: deviceSerial.trim(),
        api_key: apiKey.trim(),
        branch_id: branchId.trim() || '00',
        environment,
      }),
    onSuccess: async () => {
      setError(null)
      setNotice('eTIMS credentials saved. New receipts will be filed with KRA automatically.')
      setDeviceSerial('')
      setApiKey('')
      await queryClient.invalidateQueries({ queryKey: ['etims'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const disconnect = useMutation({
    mutationFn: etimsApi.deleteCredentials,
    onSuccess: async () => {
      setError(null)
      setNotice('eTIMS disconnected. Receipts already filed keep their KRA stamp.')
      await queryClient.invalidateQueries({ queryKey: ['etims'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const retry = useMutation({
    mutationFn: (id: string) => etimsApi.retry(id),
    onSuccess: async (result) => {
      setError(null)
      setNotice(
        result.status === 'submitted'
          ? 'Accepted by KRA on the retry.'
          : `Still not accepted: ${result.last_error ?? 'unknown error'}`,
      )
      await queryClient.invalidateQueries({ queryKey: ['etims'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (credentials.isPending) return <PageLoader />

  const configured = credentials.data?.configured ?? false

  return (
    <div>
      <PageHeader
        title="KRA eTIMS"
        description="File every rent receipt with the Kenya Revenue Authority automatically."
        backTo="/settings"
        backLabel="Settings"
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

      {report.data && report.data.total > 0 && (
        <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Receipts filed" value={String(report.data.submitted)} />
          <StatCard
            label="Success rate"
            value={`${report.data.success_rate}%`}
            tone={report.data.success_rate >= 95 ? 'success' : 'warn'}
          />
          <StatCard
            label="Retrying"
            value={String(report.data.pending + report.data.failed)}
            hint="Will be attempted again automatically"
            tone={report.data.failed > 0 ? 'warn' : 'default'}
          />
          <StatCard
            label="Given up on"
            value={String(report.data.abandoned)}
            hint="Needs declaring by hand"
            tone={report.data.abandoned > 0 ? 'danger' : 'default'}
          />
        </div>
      )}

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>
            <ShieldCheck className="mr-1.5 inline h-4 w-4 text-slate-400" />
            Registration
          </CardTitle>
          <p className="mt-0.5 text-sm text-slate-500">
            Your device serial and API key are encrypted before they are stored and are never
            shown again — re-enter them to change them.
          </p>
        </CardHeader>
        <CardBody className="space-y-4">
          {configured ? (
            <Alert tone="success">
              <CheckCircle2 className="mr-1.5 inline h-4 w-4" />
              Connected as {credentials.data?.kra_pin} (branch {credentials.data?.branch_id},{' '}
              {credentials.data?.environment}). Device serial ends{' '}
              {credentials.data?.device_serial_hint ?? '—'}.
              {credentials.data?.last_verified_at && (
                <> Last accepted {dateTime(credentials.data.last_verified_at)}.</>
              )}
            </Alert>
          ) : (
            <Alert tone="info">
              Not connected. Receipts are issued normally, without eTIMS fields — which is correct
              for a landlord who is not VAT registered.
            </Alert>
          )}

          {credentials.data?.last_error && (
            <Alert tone="warn">
              <TriangleAlert className="mr-1.5 inline h-4 w-4" />
              KRA last reported: {credentials.data.last_error}
            </Alert>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="KRA PIN" required>
              <Input
                value={kraPin}
                onChange={(event) => setKraPin(event.target.value)}
                placeholder={credentials.data?.kra_pin ?? 'A000000000Z'}
              />
            </Field>
            <Field label="Branch ID" hint="00 for a single-branch business">
              <Input value={branchId} onChange={(event) => setBranchId(event.target.value)} />
            </Field>
            <Field label="Control unit serial" required hint="From your eTIMS device registration">
              <Input
                value={deviceSerial}
                onChange={(event) => setDeviceSerial(event.target.value)}
                placeholder={configured ? 'Enter again to replace' : 'KRACU…'}
              />
            </Field>
            <Field label="API key (cmcKey)" required>
              <Input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={configured ? 'Enter again to replace' : ''}
              />
            </Field>
            <Field label="Environment" hint="Test against sandbox before going live">
              <Select
                value={environment}
                onChange={(event) => setEnvironment(event.target.value)}
              >
                <option value="sandbox">Sandbox</option>
                <option value="production">Production</option>
              </Select>
            </Field>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              loading={save.isPending}
              disabled={!kraPin.trim() || !deviceSerial.trim() || !apiKey.trim()}
              onClick={() => save.mutate()}
            >
              {configured ? 'Replace credentials' : 'Connect eTIMS'}
            </Button>
            {configured && (
              <Button
                variant="ghost"
                loading={disconnect.isPending}
                onClick={() => disconnect.mutate()}
              >
                Disconnect
              </Button>
            )}
          </div>
        </CardBody>
      </Card>

      {report.data && report.data.recent_failures.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Receipts KRA has not accepted</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              These are retried automatically with a growing delay. One marked "abandoned" has run
              out of retries and needs declaring by hand, or a manual retry here.
            </p>
          </CardHeader>
          <CardBody>
            <Table>
              <thead>
                <tr>
                  <Th>Receipt</Th>
                  <Th>Status</Th>
                  <Th>Attempts</Th>
                  <Th>Next try</Th>
                  <Th>Reason</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {report.data.recent_failures.map((row) => (
                  <tr key={row.submission_id}>
                    <Td className="font-medium">{row.receipt_reference ?? '—'}</Td>
                    <Td>
                      <Badge tone={STATUS_TONE[row.status]}>{humanize(row.status)}</Badge>
                    </Td>
                    <Td className="tabular-nums">{row.attempts}</Td>
                    <Td className="text-sm text-slate-500">
                      {row.next_attempt_at ? dateTime(row.next_attempt_at) : 'No more retries'}
                    </Td>
                    <Td className="max-w-xs text-sm text-slate-600">{row.last_error ?? '—'}</Td>
                    <Td>
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={retry.isPending && retry.variables === row.submission_id}
                        icon={<RefreshCw className="h-3.5 w-3.5" />}
                        onClick={() => {
                          setError(null)
                          setNotice(null)
                          retry.mutate(row.submission_id)
                        }}
                      >
                        Retry
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
