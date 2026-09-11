import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  CalendarPlus,
  Check,
  Fuel,
  Gauge,
  LogIn,
  LogOut,
} from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { assetsApi, rentalAgreementsApi, tenantsApi } from '@/api'
import type { RentalAgreement, RentalAsset } from '@/api/types'
import { FileUpload, type UploadedFile } from '@/components/FileUpload'
import { PageHeader } from '@/components/PageHeader'
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
  Table,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const AGREEMENT_TONE: Record<string, 'neutral' | 'brand' | 'success' | 'warn' | 'danger'> = {
  booked: 'warn',
  out: 'brand',
  returned: 'success',
  cancelled: 'neutral',
}

export function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const [booking, setBooking] = useState(false)
  const [checkingOut, setCheckingOut] = useState<RentalAgreement | null>(null)
  const [checkingIn, setCheckingIn] = useState<RentalAgreement | null>(null)

  const asset = useQuery({
    queryKey: queryKeys.asset(assetId!),
    queryFn: () => assetsApi.get(assetId!),
    enabled: Boolean(assetId),
  })
  const agreements = useQuery({
    queryKey: queryKeys.rentalAgreements({ assetId }),
    queryFn: () => rentalAgreementsApi.list({ asset_id: assetId }),
    enabled: Boolean(assetId),
  })

  if (asset.isPending) return <PageLoader />
  if (asset.isError) {
    return (
      <Alert tone="danger" title="Could not load this asset">
        {errorMessage(asset.error)}
      </Alert>
    )
  }

  const record = asset.data
  const isVehicle = record.kind === 'vehicle'
  const live = agreements.data?.find((row) => row.status === 'out')
  const upcoming = agreements.data?.filter((row) => row.status === 'booked') ?? []

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={record.name}
        description={`${record.reference_code} · ${
          isVehicle ? record.registration_number : record.serial_number
        }`}
        backTo="/fleet"
        backLabel="The fleet"
        actions={
          <Button icon={<CalendarPlus className="h-4 w-4" />} onClick={() => setBooking(true)}>
            Take a booking
          </Button>
        }
      />

      {record.compliance_warnings.length > 0 && (
        <Alert
          tone="danger"
          className="mb-4"
          icon={<AlertTriangle className="h-4 w-4" />}
          title="This asset cannot go out"
        >
          <ul className="mt-1 space-y-0.5 text-sm">
            {record.compliance_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.4fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
              <Badge tone={record.status === 'available' ? 'success' : 'brand'}>
                {humanize(record.status)}
              </Badge>
            </CardHeader>
            <CardBody>
              <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <Detail label="Daily rate" value={kes(record.daily_rate)} />
                <Detail
                  label="Weekly rate"
                  value={record.weekly_rate ? kes(record.weekly_rate) : '—'}
                />
                <Detail label="Deposit" value={kes(record.deposit_amount)} />
                {isVehicle ? (
                  <>
                    <Detail
                      label="Odometer"
                      value={record.mileage ? `${record.mileage.toLocaleString()} km` : '—'}
                    />
                    <Detail label="Fuel policy" value={humanize(record.fuel_policy)} />
                    <Detail
                      label="Included km/day"
                      value={record.daily_mileage_limit ? String(record.daily_mileage_limit) : '—'}
                    />
                    <Detail
                      label="Insurance to"
                      value={
                        record.insurance_expiry ? shortDate(record.insurance_expiry) : 'Not recorded'
                      }
                    />
                    <Detail
                      label="Inspection to"
                      value={
                        record.inspection_expiry
                          ? shortDate(record.inspection_expiry)
                          : 'Not recorded'
                      }
                    />
                    <Detail
                      label="Road licence to"
                      value={
                        record.road_licence_expiry
                          ? shortDate(record.road_licence_expiry)
                          : 'Not recorded'
                      }
                    />
                  </>
                ) : (
                  <>
                    <Detail label="Category" value={record.category ?? '—'} />
                    <Detail
                      label="Last serviced"
                      value={
                        record.last_serviced_on ? shortDate(record.last_serviced_on) : 'Not recorded'
                      }
                    />
                    <Detail
                      label="Service due"
                      value={record.service_due_on ? shortDate(record.service_due_on) : '—'}
                    />
                  </>
                )}
              </dl>
              {record.notes && (
                <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                  {record.notes}
                </p>
              )}
            </CardBody>
          </Card>

          {live && (
            <Card>
              <CardHeader>
                <CardTitle>Out right now</CardTitle>
                {live.is_overdue && <Badge tone="danger">Overdue</Badge>}
              </CardHeader>
              <CardBody className="space-y-3">
                <p className="text-sm text-slate-800">
                  With <span className="font-medium">{live.hirer_name}</span> until{' '}
                  {shortDate(live.end_date)}
                </p>
                {live.hirer_phone && (
                  <a
                    href={`tel:${live.hirer_phone}`}
                    className="text-sm text-brand-600 hover:text-brand-700"
                  >
                    {live.hirer_phone}
                  </a>
                )}
                {live.mileage_out !== null && (
                  <p className="text-xs text-slate-500">
                    Went out at {live.mileage_out.toLocaleString()} km
                    {live.fuel_out_eighths !== null
                      ? `, ${live.fuel_out_eighths}/8 of a tank`
                      : ''}
                  </p>
                )}
                <Button
                  icon={<LogIn className="h-4 w-4" />}
                  onClick={() => setCheckingIn(live)}
                >
                  Take it back
                </Button>
              </CardBody>
            </Card>
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Hire history</CardTitle>
            {upcoming.length > 0 && (
              <span className="text-sm text-slate-500">{upcoming.length} booked ahead</span>
            )}
          </CardHeader>
          <CardBody className="p-0">
            {agreements.data?.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>Hirer</Th>
                      <Th>Window</Th>
                      <Th>Status</Th>
                      <Th>Total</Th>
                      <Th />
                    </tr>
                  </thead>
                  <tbody>
                    {agreements.data.map((agreement) => (
                      <tr key={agreement.id}>
                        <Td>
                          <span className="font-medium text-slate-800">
                            {agreement.hirer_name}
                          </span>
                          <p className="text-xs text-slate-400">{agreement.reference_code}</p>
                        </Td>
                        <Td className="text-slate-600">
                          {shortDate(agreement.start_date)} → {shortDate(agreement.end_date)}
                          <p className="text-xs text-slate-400">
                            {agreement.hire_days} day{agreement.hire_days === 1 ? '' : 's'}
                          </p>
                        </Td>
                        <Td>
                          <Badge tone={AGREEMENT_TONE[agreement.status] ?? 'neutral'}>
                            {humanize(agreement.status)}
                          </Badge>
                        </Td>
                        <Td>
                          {kes(agreement.total_charge)}
                          {agreement.status === 'returned' &&
                            Number(agreement.total_charge) >
                              Number(agreement.hire_charge) && (
                              <p className="text-xs text-danger-700">
                                +{kes(
                                  Number(agreement.total_charge) - Number(agreement.hire_charge),
                                )}{' '}
                                extras
                              </p>
                            )}
                        </Td>
                        <Td>
                          {agreement.status === 'booked' && (
                            <button
                              type="button"
                              className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700"
                              onClick={() => setCheckingOut(agreement)}
                            >
                              <LogOut className="h-3.5 w-3.5" />
                              Hand over
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
                icon={<CalendarPlus className="h-6 w-6" />}
                title="Never been out"
                description="Take a booking and the hire history builds up here."
              />
            )}
          </CardBody>
        </Card>
      </div>

      <BookDialog asset={record} open={booking} onClose={() => setBooking(false)} />
      <CheckOutDialog
        asset={record}
        agreement={checkingOut}
        onClose={() => setCheckingOut(null)}
      />
      <CheckInDialog asset={record} agreement={checkingIn} onClose={() => setCheckingIn(null)} />
    </div>
  )
}

function BookDialog({
  asset,
  open,
  onClose,
}: {
  asset: RentalAsset
  open: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [walkin, setWalkin] = useState(false)
  const [form, setForm] = useState({
    tenant_id: '',
    hirer_name: '',
    hirer_phone: '',
    hirer_id_number: '',
    start_date: today(),
    end_date: '',
    rate_basis: 'daily',
  })
  const [error, setError] = useState<string | null>(null)

  const hirers = useQuery({
    queryKey: queryKeys.tenants({ forHire: true }),
    queryFn: () => tenantsApi.list(),
    enabled: open && !walkin,
  })

  const book = useMutation({
    mutationFn: () =>
      rentalAgreementsApi.book({
        asset_id: asset.id,
        tenant_id: walkin ? null : form.tenant_id || null,
        hirer_name: walkin ? form.hirer_name : null,
        hirer_phone: walkin ? form.hirer_phone : null,
        hirer_id_number: walkin ? form.hirer_id_number || null : null,
        start_date: form.start_date,
        end_date: form.end_date,
        rate_basis: form.rate_basis,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['rental-agreements'] })
      await queryClient.invalidateQueries({ queryKey: ['assets'] })
      onClose()
    },
    onError: (bookError) => setError(errorMessage(bookError)),
  })

  const valid = form.start_date && form.end_date && (
    walkin ? (form.hirer_name.length > 1 && form.hirer_phone.length > 6) : Boolean(form.tenant_id)
  )

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Book ${asset.name}`}
      description="Overlapping bookings are refused, so the calendar can be trusted."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={book.isPending}
            onClick={() => {
              setError(null)
              book.mutate()
            }}
          >
            Book it
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              className="accent-brand-600"
              checked={!walkin}
              onChange={() => setWalkin(false)}
            />
            Existing tenant
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              className="accent-brand-600"
              checked={walkin}
              onChange={() => setWalkin(true)}
            />
            Walk-in / external hirer
          </label>
        </div>

        {walkin ? (
          <>
            <Field label="Full name" required>
              <Input
                placeholder="John Kamau"
                value={form.hirer_name}
                onChange={(e) => setForm({ ...form, hirer_name: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Phone" required>
                <Input
                  type="tel"
                  placeholder="0712 345 678"
                  value={form.hirer_phone}
                  onChange={(e) => setForm({ ...form, hirer_phone: e.target.value })}
                />
              </Field>
              <Field label="ID / Passport number">
                <Input
                  placeholder="12345678"
                  value={form.hirer_id_number}
                  onChange={(e) => setForm({ ...form, hirer_id_number: e.target.value })}
                />
              </Field>
            </div>
          </>
        ) : (
          <Field label="Hirer" required>
            <Select
              value={form.tenant_id}
              onChange={(event) => setForm({ ...form, tenant_id: event.target.value })}
            >
              <option value="">Choose a hirer</option>
              {hirers.data?.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.full_name} — {tenant.phone_number}
                </option>
              ))}
            </Select>
          </Field>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="From" required>
            <Input
              type="date"
              value={form.start_date}
              onChange={(event) => setForm({ ...form, start_date: event.target.value })}
            />
          </Field>
          <Field label="To" required>
            <Input
              type="date"
              min={form.start_date}
              value={form.end_date}
              onChange={(event) => setForm({ ...form, end_date: event.target.value })}
            />
          </Field>
          <Field label="Charged">
            <Select
              value={form.rate_basis}
              onChange={(event) => setForm({ ...form, rate_basis: event.target.value })}
            >
              <option value="daily">Per day</option>
              <option value="weekly">Per week</option>
              <option value="monthly">Per month</option>
            </Select>
          </Field>
        </div>

        <p className="text-sm text-slate-500">
          Deposit of {kes(asset.deposit_amount)} is taken at hand-over and refunded on return,
          less any extras.
        </p>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function CheckOutDialog({
  asset,
  agreement,
  onClose,
}: {
  asset: RentalAsset
  agreement: RentalAgreement | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [mileage, setMileage] = useState(asset.mileage ? String(asset.mileage) : '')
  const [fuel, setFuel] = useState('8')
  const [notes, setNotes] = useState('')
  const [photos, setPhotos] = useState<UploadedFile[]>([])
  const [override, setOverride] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const isVehicle = asset.kind === 'vehicle'
  const blocked = asset.compliance_warnings.some(
    (warning) => warning.includes('expired') || warning.includes('overdue'),
  )

  const send = useMutation({
    mutationFn: () =>
      rentalAgreementsApi.checkOut(agreement!.id, {
        mileage: isVehicle && mileage ? Number(mileage) : null,
        fuel_eighths: isVehicle ? Number(fuel) : null,
        condition_notes: notes || null,
        photo_file_ids: photos.map((photo) => photo.id),
        override_compliance: override,
        override_reason: override ? reason : null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['rental-agreements'] })
      await queryClient.invalidateQueries({ queryKey: ['assets'] })
      onClose()
    },
    onError: (sendError) => setError(errorMessage(sendError)),
  })

  return (
    <Dialog
      open={agreement !== null}
      onClose={onClose}
      title="Hand it over"
      description="Record its condition now. This is what a damage dispute is settled against."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={blocked && (!override || reason.length < 5)}
            loading={send.isPending}
            onClick={() => {
              setError(null)
              send.mutate()
            }}
          >
            Check out
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {blocked && (
          <Alert
            tone="danger"
            icon={<AlertTriangle className="h-4 w-4" />}
            title="This asset is not legal to hire out"
          >
            {asset.compliance_warnings.join('; ')}
          </Alert>
        )}

        {isVehicle && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Odometer (km)" required>
              <Input
                type="number"
                min="0"
                value={mileage}
                onChange={(event) => setMileage(event.target.value)}
              />
            </Field>
            <Field label="Fuel (eighths of a tank)">
              <Select value={fuel} onChange={(event) => setFuel(event.target.value)}>
                {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((value) => (
                  <option key={value} value={value}>
                    {value}/8
                    {value === 8 ? ' (full)' : value === 4 ? ' (half)' : ''}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        )}

        <Field label="Condition on hand-over" hint="Note every existing mark before it leaves">
          <Textarea
            placeholder="Small scratch on the front bumper, otherwise clean. Spare wheel present."
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>

        <FileUpload
          value={photos}
          onChange={setPhotos}
          category="inspection_photo"
          max={10}
          label="Photos at hand-over"
          hint="Required — walk around the full vehicle/equipment. These photos are the evidence if a damage dispute arises on return."
        />

        {blocked && (
          <div className="space-y-3 rounded-lg border border-danger-200 bg-danger-50 p-3">
            <label className="flex items-start gap-2 text-sm text-danger-800">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-danger-300"
                checked={override}
                onChange={(event) => setOverride(event.target.checked)}
              />
              I am hiring this out anyway, and I accept the risk
            </label>
            {override && (
              <Field label="Why?" required>
                <Input
                  placeholder="Cover renewed this morning, certificate arriving by email"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </Field>
            )}
          </div>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function CheckInDialog({
  asset,
  agreement,
  onClose,
}: {
  asset: RentalAsset
  agreement: RentalAgreement | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [mileage, setMileage] = useState('')
  const [fuel, setFuel] = useState('8')
  const [notes, setNotes] = useState('')
  const [damage, setDamage] = useState('')
  const [photos, setPhotos] = useState<UploadedFile[]>([])
  const [result, setResult] = useState<RentalAgreement | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isVehicle = asset.kind === 'vehicle'

  const send = useMutation({
    mutationFn: () =>
      rentalAgreementsApi.checkIn(agreement!.id, {
        mileage: isVehicle && mileage ? Number(mileage) : null,
        fuel_eighths: isVehicle ? Number(fuel) : null,
        condition_notes: notes || null,
        damage_charge: damage || null,
        photo_file_ids: photos.map((photo) => photo.id),
        returned_on: today(),
      }),
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ['rental-agreements'] })
      await queryClient.invalidateQueries({ queryKey: ['assets'] })
      setResult(updated)
    },
    onError: (sendError) => setError(errorMessage(sendError)),
  })

  if (result) {
    return (
      <Dialog
        open
        onClose={() => {
          setResult(null)
          onClose()
        }}
        title="Returned"
        description="Here is what the hirer owes, and what goes back to them."
        footer={
          <Button
            onClick={() => {
              setResult(null)
              onClose()
            }}
          >
            Done
          </Button>
        }
      >
        <div className="space-y-3">
          <div className="flex flex-col items-center gap-2 py-2 text-center">
            <Check className="h-8 w-8 text-money-600" />
          </div>
          <dl className="space-y-2 text-sm">
            <Line label="Hire" value={kes(result.hire_charge)} />
            {Number(result.excess_mileage_charge) > 0 && (
              <Line
                label={`Excess mileage${
                  result.mileage_covered ? ` (${result.mileage_covered} km covered)` : ''
                }`}
                value={kes(result.excess_mileage_charge)}
              />
            )}
            {Number(result.fuel_charge) > 0 && (
              <Line label="Fuel" value={kes(result.fuel_charge)} />
            )}
            {Number(result.late_charge) > 0 && (
              <Line label="Returned late" value={kes(result.late_charge)} />
            )}
            {Number(result.damage_charge) > 0 && (
              <Line label="Damage" value={kes(result.damage_charge)} />
            )}
            <div className="flex justify-between border-t border-slate-200 pt-2 font-medium text-slate-900">
              <dt>Total</dt>
              <dd>{kes(result.total_charge)}</dd>
            </div>
            <div className="flex justify-between text-money-700">
              <dt>Deposit refund</dt>
              <dd>{kes(result.deposit_refunded ?? 0)}</dd>
            </div>
          </dl>
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog
      open={agreement !== null}
      onClose={onClose}
      title="Take it back"
      description="Compared against the hand-over snapshot to work out what is owed."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={send.isPending}
            onClick={() => {
              setError(null)
              send.mutate()
            }}
          >
            Check in
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {agreement && isVehicle && agreement.mileage_out !== null && (
          <div className="flex items-center gap-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            <Gauge className="h-4 w-4 text-slate-400" />
            Went out at {agreement.mileage_out.toLocaleString()} km
            {agreement.fuel_out_eighths !== null && (
              <>
                <ArrowRight className="h-3 w-3" />
                <Fuel className="h-4 w-4 text-slate-400" />
                {agreement.fuel_out_eighths}/8
              </>
            )}
          </div>
        )}

        {isVehicle && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Odometer now (km)" required>
              <Input
                type="number"
                min={agreement?.mileage_out ?? 0}
                value={mileage}
                onChange={(event) => setMileage(event.target.value)}
              />
            </Field>
            <Field label="Fuel now">
              <Select value={fuel} onChange={(event) => setFuel(event.target.value)}>
                {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((value) => (
                  <option key={value} value={value}>
                    {value}/8
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        )}

        <Field label="Condition on return">
          <Textarea
            placeholder="New scratch on the rear bumper, otherwise as it went out."
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>

        <Field label="Damage charge (KES)" hint="Leave blank if there is nothing to charge for">
          <Input
            type="number"
            min="0"
            value={damage}
            onChange={(event) => setDamage(event.target.value)}
          />
        </Field>

        <FileUpload
          value={photos}
          onChange={setPhotos}
          category="inspection_photo"
          max={10}
          label="Photos on return"
          hint="Required — photograph every panel and any new damage. Compared directly against the hand-over photos."
        />

        {agreement && (
          <p className="text-xs text-slate-500">
            Due back {shortDate(agreement.end_date)}
            {agreement.is_overdue ? ' — this return is late, and a late charge applies.' : '.'}
          </p>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{value}</dd>
    </div>
  )
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-slate-600">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
