import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Camera, Check, Droplets, Gauge, Plus, ScanLine, Zap } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { metersApi, unitsApi } from '@/api'
import type { MeterPhotoRead } from '@/api/types'
import { SinglePhotoUpload, type UploadedFile } from '@/components/FileUpload'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Field,
  Input,
  Select,
  Skeleton,
  Spinner,
  Table,
  Td,
  Th,
  Textarea,
  linkButtonClass,
} from '@/components/ui'
import { submitOrQueue } from '@/hooks/use-offline-queue'
import { currentPosition } from '@/lib/device'
import { errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function MeterReadingsPage() {
  const [meterType, setMeterType] = useState('')
  const canRecord = useAuthStore((state) =>
    state.user?.permissions?.includes('meter_reading:record'),
  )

  const readings = useQuery({
    queryKey: queryKeys.meterReadings({ meterType }),
    queryFn: () => metersApi.list({ meter_type: meterType || undefined, limit: 100 }),
  })

  const due = useQuery({ queryKey: queryKeys.readingsDue, queryFn: () => metersApi.due(10) })

  return (
    <div>
      <PageHeader
        title="Meter readings"
        description="Water and electricity readings feed straight into the next invoice."
        actions={
          canRecord && (
            <Link to="/meter-readings/new" className={linkButtonClass()}>
              <Plus className="h-4 w-4" />
              Record reading
            </Link>
          )
        }
      />

      {due.data && due.data.length > 0 && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle>Due this month</CardTitle>
            <Badge tone="warn">{due.data.length} pending</Badge>
          </CardHeader>
          <CardBody>
            <div className="flex flex-wrap gap-2">
              {due.data.map((item) => (
                <Link
                  key={`${item.unit_id}-${item.meter_type}`}
                  to={`/meter-readings/new?unit_id=${item.unit_id}&meter_type=${item.meter_type}`}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm hover:border-brand-300"
                >
                  {item.meter_type === 'water' ? (
                    <Droplets className="h-4 w-4 text-sky-500" />
                  ) : (
                    <Zap className="h-4 w-4 text-warn-500" />
                  )}
                  <span className="font-medium text-slate-800">Unit {item.unit_number}</span>
                  <span className="text-slate-400">{item.property_name}</span>
                </Link>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      <div className="mb-4">
        <Select
          className="w-auto min-w-36"
          value={meterType}
          onChange={(event) => setMeterType(event.target.value)}
        >
          <option value="">All meters</option>
          <option value="water">Water</option>
          <option value="electricity">Electricity</option>
        </Select>
      </div>

      <Card>
        {readings.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10" />
            ))}
          </div>
        ) : readings.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Unit</Th>
                <Th>Meter</Th>
                <Th>Reading</Th>
                <Th>Consumption</Th>
                <Th>Amount</Th>
                <Th>Date</Th>
                <Th>Billed</Th>
              </tr>
            </thead>
            <tbody>
              {readings.data.map((reading) => (
                <tr key={reading.id} className="hover:bg-slate-50">
                  <Td>
                    <Link
                      to={`/units/${reading.unit_id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {reading.unit_number}
                    </Link>
                    <span className="block text-xs text-slate-400">{reading.property_name}</span>
                  </Td>
                  <Td>
                    <span className="inline-flex items-center gap-1.5 text-slate-600">
                      {reading.meter_type === 'water' ? (
                        <Droplets className="h-3.5 w-3.5 text-sky-500" />
                      ) : (
                        <Zap className="h-3.5 w-3.5 text-warn-500" />
                      )}
                      {humanize(reading.meter_type)}
                    </span>
                  </Td>
                  <Td className="text-slate-600">
                    {reading.previous_reading} → {reading.current_reading}
                  </Td>
                  <Td className="font-medium">{reading.consumption} units</Td>
                  <Td className="font-medium">{kes(reading.amount)}</Td>
                  <Td className="text-slate-600">{shortDate(reading.reading_date)}</Td>
                  <Td>
                    {reading.billed_invoice_id ? (
                      <Badge tone="success">Billed</Badge>
                    ) : (
                      <Badge tone="warn">Next invoice</Badge>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            icon={<Gauge className="h-6 w-6" />}
            title="No readings yet"
            description="Record a reading to bill utilities automatically."
          />
        )}
      </Card>
    </div>
  )
}

/** Capture form with a mandatory meter photo and GPS tagging (US-026). */
export function RecordMeterReadingPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [unitId, setUnitId] = useState(params.get('unit_id') ?? '')
  const [meterType, setMeterType] = useState(params.get('meter_type') ?? 'water')
  const [currentReading, setCurrentReading] = useState('')
  // The previous reading field is pre-filled from context but the caretaker
  // can override it when bringing in a meter for the first time or correcting
  // a historical error. An empty string means "use what the API provides".
  const [previousReadingOverride, setPreviousReadingOverride] = useState<string>('')
  const [readingDate, setReadingDate] = useState(today())
  const [photo, setPhoto] = useState<UploadedFile | null>(null)
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [queued, setQueued] = useState(false)
  // What the OCR pass proposed, kept alongside whatever the caretaker ends up
  // submitting so the record shows whether they accepted it or corrected it.
  const [ocr, setOcr] = useState<MeterPhotoRead | null>(null)
  // When true the caretaker has explicitly chosen to keep their typed value
  // over the high-confidence OCR reading.
  const [ocrOverrideAcknowledged, setOcrOverrideAcknowledged] = useState(false)

  const units = useQuery({
    queryKey: queryKeys.units({ occupied: true }),
    queryFn: () => unitsApi.list(),
  })

  const context = useQuery({
    queryKey: queryKeys.meterContext(unitId, meterType),
    queryFn: () => metersApi.context(unitId, meterType),
    enabled: Boolean(unitId && meterType),
    // When the context loads, seed the previous reading field only if the
    // caretaker hasn't already typed something.
    select: (data) => data,
  })

  // Whenever the unit/meter type changes, reset the previous reading override
  // so it re-seeds from the new context.
  const handleUnitChange = (id: string) => {
    setUnitId(id)
    setPreviousReadingOverride('')
    setOcr(null)
    setCurrentReading('')
    setOcrOverrideAcknowledged(false)
  }
  const handleMeterTypeChange = (type: string) => {
    setMeterType(type)
    setPreviousReadingOverride('')
    setOcr(null)
    setCurrentReading('')
    setOcrOverrideAcknowledged(false)
  }

  // Effective previous reading: caretaker's override takes precedence, then
  // the context value, then zero.
  const contextPrevious = Number(context.data?.previous_reading ?? 0)
  const previous =
    previousReadingOverride !== '' ? Number(previousReadingOverride) : contextPrevious

  // True when a high-confidence OCR reading contradicts what the caretaker typed
  // and they haven't yet acknowledged the conflict.
  const ocrConflict =
    ocr !== null &&
    ocr.high_confidence &&
    ocr.reading !== null &&
    currentReading !== '' &&
    ocr.reading !== currentReading &&
    !ocrOverrideAcknowledged

  // The reading that will actually be submitted: OCR wins on high-confidence
  // conflict (unless the caretaker explicitly overrode). This mirrors what
  // the backend service will enforce — making it visible before submission
  // prevents surprises.
  const effectiveCurrent =
    ocr !== null && ocr.high_confidence && ocr.reading !== null && !ocrOverrideAcknowledged
      ? ocr.reading
      : currentReading

  // Live preview of what the tenant will be charged, so a typo is obvious before
  // it lands on an invoice.
  const current = Number(effectiveCurrent || 0)
  const consumption = Number.isFinite(current) ? Math.max(0, current - previous) : 0
  const rate = Number(context.data?.rate ?? 0)
  const estimated = consumption * rate
  const belowPrevious = effectiveCurrent !== '' && current < previous

  /**
   * Read the dial off the photo (Module 5).
   *
   * High-confidence results supersede what the caretaker typed (the photo is
   * the authoritative evidence). Low-confidence results are shown but the
   * caretaker must actively choose to use them.
   */
  const readPhoto = useMutation({
    mutationFn: (fileId: string) =>
      metersApi.readPhoto({ photo_file_id: fileId, meter_type: meterType }),
    onSuccess: (result) => {
      setOcr(result)
      setOcrOverrideAcknowledged(false)
      // High-confidence: pre-fill the field so the caretaker can see and
      // confirm. The backend will use this value regardless, but showing it
      // in the field makes the override transparent.
      if (result.reading && result.high_confidence) {
        setCurrentReading(result.reading)
      }
    },
    // Never fatal: the caretaker types the reading as they always have.
    onError: () => setOcr(null),
  })

  const record = useMutation({
    mutationFn: async () => {
      const position = await currentPosition()
      // photo_superseded tells the backend (and the audit log) that the photo
      // value was used over the caretaker's typed value.
      const photoSuperseded =
        ocr !== null &&
        ocr.high_confidence &&
        ocr.reading !== null &&
        ocr.reading !== currentReading &&
        !ocrOverrideAcknowledged
      const body = {
        unit_id: unitId,
        meter_type: meterType,
        current_reading: effectiveCurrent,
        previous_reading:
          previousReadingOverride !== '' ? previousReadingOverride : undefined,
        reading_date: readingDate,
        photo_file_id: photo!.id,
        notes: notes || null,
        gps_latitude: position?.coords.latitude ?? null,
        gps_longitude: position?.coords.longitude ?? null,
        ocr_reading: ocr?.reading ?? null,
        ocr_confidence: ocr?.confidence ?? null,
        photo_superseded: photoSuperseded,
      }
      return submitOrQueue({
        run: () => metersApi.record(body),
        method: 'POST',
        url: '/meter-readings',
        body,
        label: `${humanize(meterType)} reading for unit ${context.data?.unit_number ?? ''}`,
      })
    },
    onSuccess: async (result) => {
      if (result.queued) {
        setQueued(true)
        return
      }
      await queryClient.invalidateQueries({ queryKey: ['meter-readings'] })
      await queryClient.invalidateQueries({ queryKey: ['caretaker'] })
      navigate('/meter-readings')
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
              You are offline. This reading will be sent as soon as you reconnect.
            </p>
            <Link to="/meter-readings" className={linkButtonClass('outline')}>
              Back to readings
            </Link>
          </CardBody>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg">
      <PageHeader title="Record a meter reading" backTo="/meter-readings" />

      <Card>
        <CardBody className="space-y-4">
          <Field label="Unit" required>
            <Select value={unitId} onChange={(event) => handleUnitChange(event.target.value)}>
              <option value="">Choose a unit</option>
              {units.data?.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  Unit {unit.unit_number}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Meter" required>
            <div className="grid grid-cols-2 gap-2">
              <MeterOption
                icon={<Droplets className="h-4 w-4" />}
                label="Water"
                selected={meterType === 'water'}
                onSelect={() => handleMeterTypeChange('water')}
              />
              <MeterOption
                icon={<Zap className="h-4 w-4" />}
                label="Electricity"
                selected={meterType === 'electricity'}
                onSelect={() => handleMeterTypeChange('electricity')}
              />
            </div>
          </Field>

          {context.data && !context.data.has_rate_configured && (
            <Alert tone="warn" icon={<AlertCircle className="h-4 w-4" />}>
              No {meterType} rate is configured for {context.data.property_name}. The reading will be
              saved, but billed at KES 0 until a rate is set on the property.
            </Alert>
          )}

          {/* Previous reading — editable so caretakers can set the correct
              starting point for units being brought in for the first time or
              after a manual correction. Pre-filled from the last recorded
              reading but the caretaker can change it. */}
          {unitId && meterType && (
            <Field
              label="Previous reading"
              hint={
                context.data?.previous_reading_date
                  ? `Last recorded on ${shortDate(context.data.previous_reading_date)}`
                  : 'No prior reading on record — enter the meter value at the start of this period.'
              }
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                inputMode="decimal"
                placeholder={
                  context.isPending
                    ? 'Loading…'
                    : String(context.data?.previous_reading ?? '0')
                }
                value={previousReadingOverride}
                onChange={(event) => setPreviousReadingOverride(event.target.value)}
              />
            </Field>
          )}

          <Field
            label="Current reading"
            required
            error={belowPrevious ? 'This is lower than the previous reading — check the meter.' : undefined}
          >
            <Input
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
              placeholder="Reading on the meter"
              value={currentReading}
              invalid={belowPrevious}
              onChange={(event) => {
                setCurrentReading(event.target.value)
                // If the caretaker is editing, and OCR was high-confidence,
                // treat any deviation as an intentional override attempt —
                // the conflict banner will ask them to confirm.
                if (ocr?.high_confidence) {
                  setOcrOverrideAcknowledged(false)
                }
              }}
            />
          </Field>

          {consumption > 0 && (
            <div className="rounded-lg border border-brand-100 bg-brand-50 p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-brand-700">Consumption</span>
                <span className="font-medium text-brand-800">{consumption} units</span>
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-brand-700">Charge at {kes(rate)}/unit</span>
                <span className="text-base font-semibold text-brand-800">{kes(estimated)}</span>
              </div>
              <p className="mt-1.5 text-xs text-brand-700/70">
                Added to the tenant&apos;s next invoice automatically.
              </p>
            </div>
          )}

          <Field label="Reading date" required>
            <Input
              type="date"
              max={today()}
              value={readingDate}
              onChange={(event) => setReadingDate(event.target.value)}
            />
          </Field>

          <SinglePhotoUpload
            value={photo}
            onChange={(next) => {
              setPhoto(next)
              setOcr(null)
              // Asked for explicitly on upload rather than fired on every
              // photo the app ever stores: this is a billed model call.
              if (next) readPhoto.mutate(next.id)
            }}
            category="meter_reading"
            label="Photo of the meter"
            required
            hint="Required — this is the evidence behind the charge."
          />

          {readPhoto.isPending && (
            <p className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner className="h-4 w-4" />
              Reading the meter from your photo…
            </p>
          )}

          {ocr && (
            <Alert
              tone={ocr.reading && ocr.high_confidence ? 'info' : 'warn'}
              icon={<ScanLine className="h-4 w-4" />}
            >
              {ocr.reading ? (
                <>
                  <span className="font-medium">The photo reads {ocr.reading}.</span>{' '}
                  {ocr.high_confidence
                    ? 'Filled in for you — check it against the meter before saving.'
                    : 'Not clear enough to fill in automatically. Type what you can see.'}
                  {!ocr.high_confidence && ocr.reading !== currentReading && (
                    <button
                      type="button"
                      onClick={() => setCurrentReading(ocr.reading ?? '')}
                      className="ml-1 font-medium underline"
                    >
                      Use {ocr.reading} anyway
                    </button>
                  )}
                </>
              ) : (
                (ocr.message ?? 'The meter could not be read from that photo. Type it in.')
              )}
            </Alert>
          )}

          {/* OCR conflict banner — shown when the caretaker has typed a value
              that differs from a high-confidence photo reading. The photo value
              will be submitted unless they explicitly override it here. */}
          {ocrConflict && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              <span className="font-medium">
                The photo reads {ocr!.reading} but you entered {currentReading}.
              </span>{' '}
              The photo reading will be used because it is highly confident. If you are
              sure your value is correct, you can override it — but please recheck the
              meter first.
              <div className="mt-2 flex gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setCurrentReading(ocr!.reading ?? '')
                    setOcrOverrideAcknowledged(false)
                  }}
                  className="font-medium underline"
                >
                  Use photo value ({ocr!.reading})
                </button>
                <button
                  type="button"
                  onClick={() => setOcrOverrideAcknowledged(true)}
                  className="font-medium text-danger-700 underline"
                >
                  Keep my value ({currentReading}) instead
                </button>
              </div>
            </Alert>
          )}

          {ocrOverrideAcknowledged && ocr?.high_confidence && (
            <Alert tone="warn" icon={<AlertCircle className="h-4 w-4" />}>
              Your typed value ({currentReading}) will be used instead of the photo reading (
              {ocr.reading}). Make sure you have verified this against the physical meter.
            </Alert>
          )}

          <Field label="Notes">
            <Textarea
              placeholder="Meter was hard to read; tenant present."
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </Field>

          {error && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              {error}
            </Alert>
          )}

          {!photo && (
            <Alert tone="info" icon={<Camera className="h-4 w-4" />}>
              A photo of the meter is required before you can submit.
            </Alert>
          )}

          <Button
            className="w-full justify-center"
            size="lg"
            disabled={!unitId || !effectiveCurrent || !photo || belowPrevious || ocrConflict}
            loading={record.isPending}
            onClick={() => {
              setError(null)
              record.mutate()
            }}
          >
            Submit reading
          </Button>
        </CardBody>
      </Card>
    </div>
  )
}

function MeterOption({
  icon,
  label,
  selected,
  onSelect,
}: {
  icon: React.ReactNode
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      data-touch-target
      className={
        selected
          ? 'flex items-center justify-center gap-2 rounded-lg border border-brand-600 bg-brand-50 px-3 py-2.5 text-sm font-medium text-brand-700'
          : 'flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-600 hover:bg-slate-50'
      }
    >
      {icon}
      {label}
    </button>
  )
}
