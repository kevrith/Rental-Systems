import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Check, LogOut, Plus, UserRound } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { unitsApi, visitorLogsApi } from '@/api'
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
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  Textarea,
  linkButtonClass,
} from '@/components/ui'
import { submitOrQueue } from '@/hooks/use-offline-queue'
import { currentPosition } from '@/lib/device'
import { errorMessage, relative, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function VisitorLogPage() {
  const queryClient = useQueryClient()
  const [openOnly, setOpenOnly] = useState(false)
  const [unitId, setUnitId] = useState('')
  const [since, setSince] = useState('')
  const canRecord = useAuthStore((state) => state.user?.permissions?.includes('visitor_log:record'))

  const units = useQuery({ queryKey: queryKeys.units({}), queryFn: () => unitsApi.list() })

  const logs = useQuery({
    queryKey: queryKeys.visitorLogs({ openOnly, unitId, since }),
    queryFn: () =>
      visitorLogsApi.list({
        open_only: openOnly,
        unit_id: unitId || undefined,
        since: since || undefined,
        limit: 100,
      }),
  })

  const checkOut = useMutation({
    mutationFn: (id: string) => visitorLogsApi.checkOut(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['visitor-logs'] })
    },
  })

  return (
    <div>
      <PageHeader
        title="Visitor log"
        description="Who came, when, and why — a record for security and dispute purposes."
        actions={
          canRecord && (
            <Link to="/visitor-log/new" className={linkButtonClass()}>
              <Plus className="h-4 w-4" />
              Log a visitor
            </Link>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select className="w-auto min-w-40" value={unitId} onChange={(event) => setUnitId(event.target.value)}>
          <option value="">All units</option>
          {units.data?.map((unit) => (
            <option key={unit.id} value={unit.id}>
              Unit {unit.unit_number}
            </option>
          ))}
        </Select>
        <Input
          type="date"
          className="w-auto"
          value={since}
          onChange={(event) => setSince(event.target.value)}
          aria-label="Show visitors checked in since"
        />
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 accent-brand-600"
            checked={openOnly}
            onChange={(event) => setOpenOnly(event.target.checked)}
          />
          Still on site only
        </label>
      </div>

      <Card>
        {logs.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : logs.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Visitor</Th>
                <Th>Unit</Th>
                <Th>Purpose</Th>
                <Th>Checked in</Th>
                <Th>Checked out</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {logs.data.map((entry) => (
                <tr key={entry.id} className="hover:bg-slate-50">
                  <Td>
                    <span className="font-medium text-slate-900">{entry.visitor_name}</span>
                    {entry.visitor_phone && (
                      <span className="block text-xs text-slate-400">{entry.visitor_phone}</span>
                    )}
                  </Td>
                  <Td>
                    <span className="font-medium text-brand-700">{entry.unit_number}</span>
                    <span className="block text-xs text-slate-400">{entry.property_name}</span>
                  </Td>
                  <Td className="max-w-xs truncate text-slate-600">{entry.purpose ?? '—'}</Td>
                  <Td className="text-slate-600">{relative(entry.checked_in_at)}</Td>
                  <Td>
                    {entry.checked_out_at ? (
                      <span className="text-slate-600">{shortDate(entry.checked_out_at)}</span>
                    ) : (
                      <Badge tone="warn">On site</Badge>
                    )}
                  </Td>
                  <Td>
                    {!entry.checked_out_at && canRecord && (
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<LogOut className="h-3.5 w-3.5" />}
                        loading={checkOut.isPending}
                        onClick={() => checkOut.mutate(entry.id)}
                      >
                        Check out
                      </Button>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<UserRound className="h-6 w-6" />}
            title="No visitors logged"
            description="Log a visitor as soon as they arrive."
          />
        )}
      </Card>
    </div>
  )
}

export function LogVisitorPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [unitId, setUnitId] = useState('')
  const [visitorName, setVisitorName] = useState('')
  const [visitorPhone, setVisitorPhone] = useState('')
  const [purpose, setPurpose] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [queued, setQueued] = useState(false)

  const units = useQuery({ queryKey: queryKeys.units({ occupied: true }), queryFn: () => unitsApi.list() })

  const record = useMutation({
    mutationFn: async () => {
      const position = await currentPosition()
      const body = {
        unit_id: unitId,
        visitor_name: visitorName,
        visitor_phone: visitorPhone || null,
        purpose: purpose || null,
        gps_latitude: position?.coords.latitude ?? null,
        gps_longitude: position?.coords.longitude ?? null,
      }
      return submitOrQueue({
        run: () => visitorLogsApi.log(body),
        method: 'POST',
        url: '/visitor-logs',
        body,
        label: `Visitor ${visitorName} logged`,
      })
    },
    onSuccess: async (result) => {
      if (result.queued) {
        setQueued(true)
        return
      }
      await queryClient.invalidateQueries({ queryKey: ['visitor-logs'] })
      navigate('/visitor-log')
    },
    onError: (recordError) => setError(errorMessage(recordError)),
  })

  if (queued) {
    return (
      <div className="mx-auto max-w-lg">
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
            <Check className="h-10 w-10 text-money-600" />
            <p className="font-medium text-slate-900">Saved on this device</p>
            <p className="max-w-sm text-sm text-slate-500">
              You are offline. This entry will be sent as soon as you reconnect.
            </p>
            <Link to="/visitor-log" className={linkButtonClass('outline')}>
              Back to visitor log
            </Link>
          </CardBody>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg">
      <PageHeader title="Log a visitor" backTo="/visitor-log" />

      <Card>
        <CardBody className="space-y-4">
          <Field label="Unit visited" required>
            <Select value={unitId} onChange={(event) => setUnitId(event.target.value)}>
              <option value="">Choose a unit</option>
              {units.data?.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  Unit {unit.unit_number}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Visitor name" required>
            <Input
              placeholder="Full name"
              value={visitorName}
              onChange={(event) => setVisitorName(event.target.value)}
            />
          </Field>

          <Field label="Phone number">
            <Input
              placeholder="Optional"
              value={visitorPhone}
              onChange={(event) => setVisitorPhone(event.target.value)}
            />
          </Field>

          <Field label="Purpose of visit">
            <Textarea
              placeholder="Visiting unit 4B, delivery, contractor, ..."
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
            />
          </Field>

          {error && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              {error}
            </Alert>
          )}

          <Button
            className="w-full justify-center"
            size="lg"
            disabled={!unitId || !visitorName}
            loading={record.isPending}
            onClick={() => {
              setError(null)
              record.mutate()
            }}
          >
            Log visitor
          </Button>
        </CardBody>
      </Card>
    </div>
  )
}
