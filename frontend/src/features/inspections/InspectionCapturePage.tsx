import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, MapPin, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { inspectionsApi, unitsApi } from '@/api'
import type { InspectionRoom, RoomCondition } from '@/api/types'
import { FileUpload, type UploadedFile } from '@/components/FileUpload'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Field,
  PageLoader,
  Textarea,
} from '@/components/ui'
import { CONDITIONS, CONDITION_TONE } from '@/features/inspections/condition'
import { cn } from '@/lib/cn'
import { errorMessage, humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

interface Draft extends InspectionRoom {
  uploads: UploadedFile[]
}

/**
 * Room-by-room inspection capture, built for a caretaker on a phone (US-049).
 *
 * One room fills the screen at a time — a grid of four condition buttons, the
 * camera, and a notes box — because the alternative is a long scrolling form
 * filled in one-handed while standing in someone's kitchen. Progress is kept on
 * the server after each room, so a dropped connection loses at most one room.
 *
 * Submission is irreversible and every room needs a condition and a photo, which
 * is what makes the report worth anything in a deposit dispute.
 */
export function InspectionCapturePage() {
  const { inspectionId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const unitId = params.get('unit_id') ?? ''
  const tenancyId = params.get('tenancy_id')
  const kind = params.get('type') ?? 'routine'

  const [reportId, setReportId] = useState(inspectionId ?? '')
  const [rooms, setRooms] = useState<Draft[] | null>(null)
  const [index, setIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null)

  // Captured once when the screen opens: the inspection is evidence that
  // somebody physically stood in the unit, and the coordinates are the proof.
  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (position) =>
        setCoords({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => setCoords(null),
      { enableHighAccuracy: true, timeout: 8000 },
    )
  }, [])

  const unit = useQuery({
    queryKey: queryKeys.unit(unitId),
    queryFn: () => unitsApi.get(unitId),
    enabled: Boolean(unitId) && !reportId,
  })

  const existing = useQuery({
    queryKey: queryKeys.inspection(reportId),
    queryFn: () => inspectionsApi.get(reportId),
    enabled: Boolean(reportId),
  })

  useEffect(() => {
    if (!existing.data || rooms !== null) return
    setRooms(
      existing.data.rooms.map((room) => ({
        ...room,
        uploads: (room.photos ?? []).map((photo) => ({
          id: photo.id,
          url: photo.url,
          filename: photo.filename,
        })),
      })),
    )
  }, [existing.data, rooms])

  const start = useMutation({
    mutationFn: () =>
      inspectionsApi.create({
        unit_id: unitId,
        tenancy_id: tenancyId,
        inspection_type: kind,
        gps_latitude: coords?.lat ?? null,
        gps_longitude: coords?.lng ?? null,
      }),
    onSuccess: (report) => {
      setError(null)
      setReportId(report.id)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const saveRooms = useMutation({
    mutationFn: (next: Draft[]) =>
      inspectionsApi.updateRooms(reportId, {
        rooms_data: next.map(({ uploads, photos: _photos, ...room }) => ({
          ...room,
          photo_file_ids: uploads.map((file) => file.id),
        })),
      }),
    onError: (err) => setError(errorMessage(err)),
  })

  const submit = useMutation({
    mutationFn: async () => {
      if (rooms) await saveRooms.mutateAsync(rooms)
      return inspectionsApi.submit(reportId)
    },
    onSuccess: async (report) => {
      await queryClient.invalidateQueries({ queryKey: ['inspections'] })
      navigate(`/inspections/${report.id}`)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (!reportId) {
    if (!unitId) {
      return <Alert tone="danger">Open an inspection from a unit so it knows what to inspect.</Alert>
    }
    if (unit.isPending) return <PageLoader />
    return (
      <div>
        <PageHeader
          title={`${humanize(kind)} inspection`}
          description={`Unit ${unit.data?.unit_number ?? ''}`}
          backTo={`/units/${unitId}`}
          backLabel="Unit"
        />
        {error && <Alert tone="danger" className="mb-4">{error}</Alert>}
        <Card>
          <CardBody className="space-y-3">
            <p className="text-sm text-slate-600">
              You will be asked to rate each room and take at least one photo of it. Once submitted
              the report cannot be changed — it is the evidence in any deposit dispute.
            </p>
            <p className="text-xs text-slate-500">
              <MapPin className="mr-1 inline h-3.5 w-3.5" />
              {coords
                ? `Location captured (${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)})`
                : 'Waiting for location — allow it so the report proves you were on site.'}
            </p>
            <Button loading={start.isPending} onClick={() => start.mutate()}>
              Start the inspection
            </Button>
          </CardBody>
        </Card>
      </div>
    )
  }

  if (existing.isPending || rooms === null) return <PageLoader />

  if (existing.data?.status === 'submitted') {
    return (
      <div>
        <PageHeader title="Inspection submitted" backTo="/inspections" backLabel="Inspections" />
        <Alert tone="success">
          {existing.data.reference_code} is submitted and can no longer be edited.
        </Alert>
      </div>
    )
  }

  const room = rooms[index]
  const complete = rooms.filter((r) => r.condition && r.uploads.length > 0).length
  const ready = complete === rooms.length

  const patch = (changes: Partial<Draft>) => {
    const next = rooms.map((r, i) => (i === index ? { ...r, ...changes } : r))
    setRooms(next)
    return next
  }

  const persistAndMove = async (next: Draft[], step: number) => {
    setError(null)
    await saveRooms.mutateAsync(next)
    setIndex((current) => Math.min(rooms.length - 1, Math.max(0, current + step)))
  }

  return (
    <div className="pb-24">
      <PageHeader
        title={`${humanize(existing.data?.inspection_type ?? kind)} inspection`}
        description={`${existing.data?.reference_code} · room ${index + 1} of ${rooms.length}`}
        backTo="/inspections"
        backLabel="Inspections"
      />

      {error && <Alert tone="danger" className="mb-4">{error}</Alert>}

      <div className="mb-4 flex gap-1">
        {rooms.map((r, i) => (
          <button
            key={r.name}
            type="button"
            aria-label={`Go to ${r.name}`}
            onClick={() => setIndex(i)}
            className={cn(
              'h-1.5 flex-1 rounded-full transition-colors',
              r.condition && r.uploads.length > 0
                ? 'bg-money-500'
                : i === index
                  ? 'bg-brand-500'
                  : 'bg-slate-200',
            )}
          />
        ))}
      </div>

      <Card>
        <CardBody className="space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">{room.name}</h2>
            {room.condition && (
              <Badge tone={CONDITION_TONE[room.condition]}>{humanize(room.condition)}</Badge>
            )}
          </div>

          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">
              Condition <span className="text-danger-600">*</span>
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {CONDITIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  data-touch-target
                  onClick={() => patch({ condition: option.value as RoomCondition })}
                  className={cn(
                    'rounded-card border px-3 py-4 text-sm font-medium transition-colors',
                    room.condition === option.value
                      ? 'border-brand-500 bg-brand-50 text-brand-800'
                      : 'border-slate-200 text-slate-600 hover:border-slate-300',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <FileUpload
            label="Photos *"
            hint="At least one per room. Take them now — the report cannot be submitted without them."
            category="inspection_photo"
            capture
            max={6}
            value={room.uploads}
            onChange={(uploads) => patch({ uploads })}
          />

          <Field label="Notes">
            <Textarea
              rows={3}
              value={room.notes ?? ''}
              onChange={(event) => patch({ notes: event.target.value })}
              placeholder="Anything worth recording — a crack, a stain, a missing fitting."
            />
          </Field>
        </CardBody>
      </Card>

      <div className="fixed inset-x-0 bottom-0 border-t border-slate-200 bg-white/95 p-3 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-2">
          <Button
            variant="secondary"
            disabled={index === 0}
            icon={<ChevronLeft className="h-4 w-4" />}
            onClick={() => void persistAndMove(rooms, -1)}
          >
            Back
          </Button>
          <span className="flex-1 text-center text-xs text-slate-500">
            {complete} of {rooms.length} rooms done
          </span>
          {index < rooms.length - 1 ? (
            <Button
              loading={saveRooms.isPending}
              icon={<ChevronRight className="h-4 w-4" />}
              onClick={() => void persistAndMove(rooms, 1)}
            >
              Next room
            </Button>
          ) : (
            <Button
              loading={submit.isPending}
              disabled={!ready}
              icon={ready ? <Send className="h-4 w-4" /> : <Check className="h-4 w-4" />}
              onClick={() => submit.mutate()}
            >
              {ready ? 'Submit' : `${rooms.length - complete} left`}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
