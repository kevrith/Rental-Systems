import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarClock,
  Car,
  Check,
  Dumbbell,
  Plug,
  Plus,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { amenitiesApi, parkingApi, propertiesApi, tenanciesApi, utilitiesApi } from '@/api'
import type { AmenityKind, BayType, UtilityAccountType } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Tab,
  Table,
  Tabs,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const BAY_TYPES: BayType[] = ['open', 'covered', 'reserved', 'visitor', 'disabled']
const AMENITY_KINDS: AmenityKind[] = [
  'gym',
  'meeting_room',
  'rooftop',
  'pool',
  'clubhouse',
  'playground',
  'laundry',
  'other',
]
const UTILITY_TYPES: UtilityAccountType[] = ['kplc', 'water', 'internet', 'garbage', 'other']

/** Parking, amenities and the building's own utility accounts, per property. */
export function FacilitiesPage() {
  const { propertyId } = useParams<{ propertyId: string }>()
  const [tab, setTab] = useState('parking')

  const property = useQuery({
    queryKey: queryKeys.property(propertyId!),
    queryFn: () => propertiesApi.get(propertyId!),
    enabled: Boolean(propertyId),
  })

  if (property.isPending) return <PageLoader />

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Facilities"
        description={property.data?.name}
        backTo={`/properties/${propertyId}`}
        backLabel="Back to the property"
      />

      <Tabs value={tab} onChange={setTab}>
        <Tab value="parking">Parking</Tab>
        <Tab value="amenities">Amenities</Tab>
        <Tab value="utilities">Utility accounts</Tab>
      </Tabs>

      <div className="mt-4">
        {tab === 'parking' && <ParkingTab propertyId={propertyId!} />}
        {tab === 'amenities' && <AmenitiesTab propertyId={propertyId!} />}
        {tab === 'utilities' && <UtilitiesTab propertyId={propertyId!} />}
      </div>
    </div>
  )
}

function ParkingTab({ propertyId }: { propertyId: string }) {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [allocating, setAllocating] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const overview = useQuery({
    queryKey: queryKeys.parking(propertyId),
    queryFn: () => parkingApi.overview(propertyId),
  })

  const release = useMutation({
    mutationFn: (allocationId: string) => parkingApi.release(allocationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['parking'] }),
    onError: (releaseError) => setError(errorMessage(releaseError)),
  })

  if (overview.isPending) return <PageLoader />
  const data = overview.data!

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label="Bays" value={String(data.total_bays)} icon={<Car className="h-4 w-4" />} />
        <StatCard
          label="Available"
          value={String(data.available)}
          tone={data.available > 0 ? 'success' : 'default'}
        />
        <StatCard label="Monthly income" value={kes(data.monthly_parking_income)} />
      </div>

      {error && <Alert tone="danger">{error}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Bays</CardTitle>
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add a bay
          </Button>
        </CardHeader>
        <CardBody className="p-0">
          {data.bays.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Bay</Th>
                    <Th>Type</Th>
                    <Th>Fee</Th>
                    <Th>Held by</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {data.bays.map((bay) => (
                    <tr key={bay.bay_id}>
                      <Td>
                        <span className="font-medium text-slate-900">{bay.bay_number}</span>
                        {bay.level && (
                          <span className="ml-1 text-xs text-slate-400">{bay.level}</span>
                        )}
                      </Td>
                      <Td>{humanize(bay.bay_type)}</Td>
                      <Td>{kes(bay.monthly_fee)}</Td>
                      <Td>
                        {bay.holder ? (
                          <>
                            <span className="text-slate-800">{bay.holder}</span>
                            {bay.vehicle_registration && (
                              <span className="ml-1 text-xs text-slate-400">
                                {bay.vehicle_registration}
                              </span>
                            )}
                            {bay.allocated_until && (
                              <p className="text-xs text-slate-400">
                                until {shortDate(bay.allocated_until)}
                              </p>
                            )}
                          </>
                        ) : (
                          <Badge tone="success">Available</Badge>
                        )}
                      </Td>
                      <Td>
                        {bay.allocation_id ? (
                          <button
                            type="button"
                            className="text-sm text-slate-500 hover:text-danger-700"
                            onClick={() => {
                              setError(null)
                              release.mutate(bay.allocation_id!)
                            }}
                          >
                            Release
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="text-sm text-brand-600 hover:text-brand-700"
                            onClick={() => setAllocating(bay.bay_id)}
                          >
                            Allocate
                          </button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<Car className="h-6 w-6" />}
              title="No bays recorded"
              description="Add the building's bays and allocate them to tenants — the fee rides along on their rent invoice."
            />
          )}
        </CardBody>
      </Card>

      <AddBayDialog propertyId={propertyId} open={adding} onClose={() => setAdding(false)} />
      <AllocateDialog
        bayId={allocating}
        propertyId={propertyId}
        onClose={() => setAllocating(null)}
      />
    </div>
  )
}

function AddBayDialog({
  propertyId,
  open,
  onClose,
}: {
  propertyId: string
  open: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ bay_number: '', bay_type: 'open', level: '', monthly_fee: '' })
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      parkingApi.createBay({
        property_id: propertyId,
        bay_number: form.bay_number,
        bay_type: form.bay_type,
        level: form.level || null,
        monthly_fee: form.monthly_fee || '0',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['parking'] })
      setForm({ bay_number: '', bay_type: 'open', level: '', monthly_fee: '' })
      onClose()
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a parking bay"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!form.bay_number}
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Add
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Bay number" required>
            <Input
              placeholder="P12"
              value={form.bay_number}
              onChange={(event) => setForm({ ...form, bay_number: event.target.value })}
            />
          </Field>
          <Field label="Type">
            <Select
              value={form.bay_type}
              onChange={(event) => setForm({ ...form, bay_type: event.target.value })}
            >
              {BAY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {humanize(type)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Level or location">
            <Input
              placeholder="Basement 1"
              value={form.level}
              onChange={(event) => setForm({ ...form, level: event.target.value })}
            />
          </Field>
          <Field label="Monthly fee (KES)" hint="Billed with the tenant's rent">
            <Input
              type="number"
              min="0"
              value={form.monthly_fee}
              onChange={(event) => setForm({ ...form, monthly_fee: event.target.value })}
            />
          </Field>
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function AllocateDialog({
  bayId,
  propertyId,
  onClose,
}: {
  bayId: string | null
  propertyId: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'tenant' | 'visitor'>('tenant')
  const [form, setForm] = useState({
    tenancy_id: '',
    guest_name: '',
    guest_phone: '',
    vehicle_registration: '',
    start_date: today(),
    end_date: '',
  })
  const [error, setError] = useState<string | null>(null)

  const tenancies = useQuery({
    queryKey: queryKeys.tenancies({ propertyId }),
    queryFn: () => tenanciesApi.list({ tenancy_status: 'active' }),
    enabled: bayId !== null,
  })

  const allocate = useMutation({
    mutationFn: () =>
      parkingApi.allocate(bayId!, {
        tenancy_id: mode === 'tenant' ? form.tenancy_id : null,
        guest_name: mode === 'visitor' ? form.guest_name : null,
        guest_phone: mode === 'visitor' ? form.guest_phone || null : null,
        vehicle_registration: form.vehicle_registration || null,
        start_date: form.start_date,
        end_date: form.end_date || null,
        bill_monthly: mode === 'tenant',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['parking'] })
      onClose()
    },
    onError: (allocateError) => setError(errorMessage(allocateError)),
  })

  const valid =
    mode === 'tenant' ? Boolean(form.tenancy_id) : Boolean(form.guest_name && form.end_date)

  return (
    <Dialog
      open={bayId !== null}
      onClose={onClose}
      title="Allocate the bay"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={allocate.isPending}
            onClick={() => {
              setError(null)
              allocate.mutate()
            }}
          >
            Allocate
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Who gets it?">
          <Select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="tenant">A tenant — billed monthly</option>
            <option value="visitor">A visitor — temporary, not billed</option>
          </Select>
        </Field>

        {mode === 'tenant' ? (
          <Field label="Tenancy" required>
            <Select
              value={form.tenancy_id}
              onChange={(event) => setForm({ ...form, tenancy_id: event.target.value })}
            >
              <option value="">Choose a tenancy</option>
              {tenancies.data?.map((tenancy) => (
                <option key={tenancy.id} value={tenancy.id}>
                  {tenancy.tenant_name} — unit {tenancy.unit_number}
                </option>
              ))}
            </Select>
          </Field>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Visitor name" required>
              <Input
                value={form.guest_name}
                onChange={(event) => setForm({ ...form, guest_name: event.target.value })}
              />
            </Field>
            <Field label="Their phone">
              <Input
                value={form.guest_phone}
                onChange={(event) => setForm({ ...form, guest_phone: event.target.value })}
              />
            </Field>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Vehicle registration">
            <Input
              placeholder="KDA 123X"
              value={form.vehicle_registration}
              onChange={(event) => setForm({ ...form, vehicle_registration: event.target.value })}
            />
          </Field>
          <Field label="From" required>
            <Input
              type="date"
              value={form.start_date}
              onChange={(event) => setForm({ ...form, start_date: event.target.value })}
            />
          </Field>
          <Field label="Until" required={mode === 'visitor'}>
            <Input
              type="date"
              value={form.end_date}
              onChange={(event) => setForm({ ...form, end_date: event.target.value })}
            />
          </Field>
        </div>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function AmenitiesTab({ propertyId }: { propertyId: string }) {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const amenities = useQuery({
    queryKey: queryKeys.amenities(propertyId),
    queryFn: () => amenitiesApi.list(propertyId),
  })
  const usage = useQuery({
    queryKey: queryKeys.amenityUsage(propertyId),
    queryFn: () => amenitiesApi.usage(propertyId),
  })
  const calendar = useQuery({
    queryKey: queryKeys.amenityCalendar(selected ?? ''),
    queryFn: () => amenitiesApi.calendar(selected!),
    enabled: Boolean(selected),
  })

  const cancel = useMutation({
    mutationFn: (bookingId: string) => amenitiesApi.cancel(bookingId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['amenities'] }),
    onError: (cancelError) => setError(errorMessage(cancelError)),
  })

  return (
    <div className="space-y-5">
      {error && <Alert tone="danger">{error}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Shared amenities</CardTitle>
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
            Add an amenity
          </Button>
        </CardHeader>
        <CardBody className="p-0">
          {amenities.data?.length ? (
            <ul className="divide-y divide-slate-100">
              {amenities.data.map((amenity) => {
                const stats = usage.data?.find((row) => row.amenity_id === amenity.id)
                return (
                  <li key={amenity.id} className="px-5 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900">{amenity.name}</p>
                        <p className="text-xs text-slate-500">
                          {humanize(amenity.kind)} · open {amenity.opens_at_hour}:00–
                          {amenity.closes_at_hour}:00 · max {amenity.max_hours_per_booking}h,{' '}
                          {amenity.max_bookings_per_week}/week
                        </p>
                        {stats && (
                          <p className="mt-1 text-xs text-slate-400">
                            {stats.bookings} booking(s), {stats.hours_booked}h this month
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        className="text-sm text-brand-600 hover:text-brand-700"
                        onClick={() => setSelected(selected === amenity.id ? null : amenity.id)}
                      >
                        {selected === amenity.id ? 'Hide bookings' : 'See bookings'}
                      </button>
                    </div>

                    {selected === amenity.id && (
                      <div className="mt-3 rounded-lg border border-slate-200">
                        {calendar.data?.length ? (
                          <ul className="divide-y divide-slate-100">
                            {calendar.data.map((booking) => (
                              <li
                                key={booking.id}
                                className="flex items-center justify-between gap-3 px-3 py-2"
                              >
                                <div className="min-w-0">
                                  <p className="text-sm text-slate-800">
                                    {dateTime(booking.starts_at)} –{' '}
                                    {new Date(booking.ends_at).toLocaleTimeString('en-KE', {
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    })}
                                  </p>
                                  <p className="text-xs text-slate-500">
                                    {booking.status === 'blocked'
                                      ? `Out of service — ${booking.purpose ?? 'maintenance'}`
                                      : `${booking.tenant_name ?? 'A tenant'}${
                                          booking.purpose ? ` · ${booking.purpose}` : ''
                                        }`}
                                  </p>
                                </div>
                                <div className="flex items-center gap-2">
                                  <Badge tone={booking.status === 'blocked' ? 'warn' : 'brand'}>
                                    {humanize(booking.status)}
                                  </Badge>
                                  <button
                                    type="button"
                                    aria-label="Cancel booking"
                                    className="rounded p-1 text-slate-400 hover:text-danger-700"
                                    onClick={() => {
                                      setError(null)
                                      cancel.mutate(booking.id)
                                    }}
                                  >
                                    <X className="h-4 w-4" />
                                  </button>
                                </div>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="px-3 py-4 text-center text-sm text-slate-500">
                            Nothing booked in the next 30 days.
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          ) : (
            <EmptyState
              icon={<Dumbbell className="h-6 w-6" />}
              title="No shared amenities"
              description="Add the gym, meeting room or rooftop and tenants can book slots from their portal."
            />
          )}
        </CardBody>
      </Card>

      <AddAmenityDialog
        propertyId={propertyId}
        open={adding}
        onClose={() => setAdding(false)}
      />
    </div>
  )
}

function AddAmenityDialog({
  propertyId,
  open,
  onClose,
}: {
  propertyId: string
  open: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    name: '',
    kind: 'gym',
    description: '',
    max_hours_per_booking: '2',
    min_notice_hours: '2',
    max_bookings_per_week: '3',
    opens_at_hour: '6',
    closes_at_hour: '22',
  })
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      amenitiesApi.create({
        property_id: propertyId,
        name: form.name,
        kind: form.kind,
        description: form.description || null,
        max_hours_per_booking: Number(form.max_hours_per_booking),
        min_notice_hours: Number(form.min_notice_hours),
        max_bookings_per_week: Number(form.max_bookings_per_week),
        opens_at_hour: Number(form.opens_at_hour),
        closes_at_hour: Number(form.closes_at_hour),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['amenities'] })
      onClose()
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a shared amenity"
      description="The rules below are what stop two tenants booking the same slot."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={form.name.length < 2}
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Add
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name" required>
            <Input
              placeholder="Rooftop terrace"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Kind">
            <Select
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value })}
            >
              {AMENITY_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {humanize(kind)}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Description">
          <Textarea
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Max hours per booking">
            <Input
              type="number"
              min="1"
              max="24"
              value={form.max_hours_per_booking}
              onChange={(event) =>
                setForm({ ...form, max_hours_per_booking: event.target.value })
              }
            />
          </Field>
          <Field label="Notice required (hours)">
            <Input
              type="number"
              min="0"
              value={form.min_notice_hours}
              onChange={(event) => setForm({ ...form, min_notice_hours: event.target.value })}
            />
          </Field>
          <Field label="Bookings per week">
            <Input
              type="number"
              min="1"
              value={form.max_bookings_per_week}
              onChange={(event) =>
                setForm({ ...form, max_bookings_per_week: event.target.value })
              }
            />
          </Field>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Opens at">
            <Input
              type="number"
              min="0"
              max="23"
              value={form.opens_at_hour}
              onChange={(event) => setForm({ ...form, opens_at_hour: event.target.value })}
            />
          </Field>
          <Field label="Closes at">
            <Input
              type="number"
              min="1"
              max="24"
              value={form.closes_at_hour}
              onChange={(event) => setForm({ ...form, closes_at_hour: event.target.value })}
            />
          </Field>
        </div>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function UtilitiesTab({ propertyId }: { propertyId: string }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    account_type: 'kplc',
    account_number: '',
    provider: '',
    next_due_on: '',
  })
  const [error, setError] = useState<string | null>(null)

  const accounts = useQuery({
    queryKey: queryKeys.utilities(propertyId),
    queryFn: () => utilitiesApi.list(propertyId),
  })

  const save = useMutation({
    mutationFn: () =>
      utilitiesApi.save({
        property_id: propertyId,
        account_type: form.account_type,
        account_number: form.account_number,
        provider: form.provider || null,
        next_due_on: form.next_due_on || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['utilities'] })
      setForm({ ...form, account_number: '', provider: '', next_due_on: '' })
    },
    onError: (saveError) => setError(errorMessage(saveError)),
  })

  const markPaid = useMutation({
    mutationFn: (accountId: string) =>
      utilitiesApi.updateStatus(accountId, {
        payment_status: 'paid',
        last_paid_on: today(),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['utilities'] }),
    onError: (markError) => setError(errorMessage(markError)),
  })

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>The building&apos;s own accounts</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-sm text-slate-600">
            These are the block&apos;s accounts with KPLC, the water board and so on — not the
            tenants&apos; meters. A disconnection affects everyone in the building, so an overdue
            one raises an alert.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <Field label="Type">
              <Select
                value={form.account_type}
                onChange={(event) => setForm({ ...form, account_type: event.target.value })}
              >
                {UTILITY_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.toUpperCase()}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Account number" required>
              <Input
                value={form.account_number}
                onChange={(event) => setForm({ ...form, account_number: event.target.value })}
              />
            </Field>
            <Field label="Provider">
              <Input
                placeholder="Kenya Power"
                value={form.provider}
                onChange={(event) => setForm({ ...form, provider: event.target.value })}
              />
            </Field>
            <Field label="Next due">
              <Input
                type="date"
                value={form.next_due_on}
                onChange={(event) => setForm({ ...form, next_due_on: event.target.value })}
              />
            </Field>
          </div>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button
            disabled={form.account_number.length < 2}
            loading={save.isPending}
            onClick={() => {
              setError(null)
              save.mutate()
            }}
          >
            Save the account
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {accounts.data?.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Account</Th>
                    <Th>Status</Th>
                    <Th>Last paid</Th>
                    <Th>Next due</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {accounts.data.map((account) => (
                    <tr key={account.id}>
                      <Td>
                        <span className="font-medium text-slate-900">
                          {account.account_type.toUpperCase()}
                        </span>
                        <span className="ml-2 text-slate-600">{account.account_number}</span>
                        {account.provider && (
                          <p className="text-xs text-slate-400">{account.provider}</p>
                        )}
                      </Td>
                      <Td>
                        <Badge
                          tone={
                            account.is_overdue
                              ? 'danger'
                              : account.payment_status === 'paid'
                                ? 'success'
                                : 'warn'
                          }
                        >
                          {account.is_overdue ? 'Overdue' : humanize(account.payment_status)}
                        </Badge>
                      </Td>
                      <Td className="text-slate-500">
                        {account.last_paid_on ? shortDate(account.last_paid_on) : '—'}
                        {account.last_amount && (
                          <span className="ml-1 text-xs">{kes(account.last_amount)}</span>
                        )}
                      </Td>
                      <Td className="text-slate-500">
                        {account.next_due_on ? shortDate(account.next_due_on) : '—'}
                      </Td>
                      <Td>
                        {account.payment_status !== 'paid' && (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700"
                            onClick={() => {
                              setError(null)
                              markPaid.mutate(account.id)
                            }}
                          >
                            <Check className="h-3.5 w-3.5" />
                            Mark paid
                          </button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<Plug className="h-6 w-6" />}
              title="No accounts recorded"
              description="Add the KPLC and water accounts so nobody has to hunt for the number when a bill lands."
            />
          )}
        </CardBody>
      </Card>

      <Alert tone="info" icon={<CalendarClock className="h-4 w-4" />}>
        Anything past its due date and not marked paid raises a weekly alert to the office.
      </Alert>
    </div>
  )
}
