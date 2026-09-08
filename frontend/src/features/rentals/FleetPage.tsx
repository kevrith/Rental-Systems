import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CalendarDays,
  Car,
  Package,
  Plus,
  Search,
  Wallet,
  Wrench,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { assetsApi } from '@/api'
import type { AssetKind } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Tab,
  Tabs,
  Textarea,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const STATUS_TONE: Record<string, 'neutral' | 'brand' | 'success' | 'warn' | 'danger'> = {
  available: 'success',
  on_hire: 'brand',
  maintenance: 'warn',
  retired: 'neutral',
}

/** The counter's morning screen: what is out, what is free, what is not legal. */
export function FleetPage() {
  const [kind, setKind] = useState('')
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState<AssetKind | null>(null)

  const overview = useQuery({ queryKey: queryKeys.fleetOverview, queryFn: assetsApi.overview })
  const assets = useQuery({
    queryKey: queryKeys.assets({ kind, search }),
    queryFn: () => assetsApi.list({ kind: kind || undefined, search: search || undefined }),
  })

  if (overview.isPending) return <PageLoader />
  const data = overview.data!

  return (
    <div>
      <PageHeader
        title="Fleet"
        description="Vehicles and equipment out on hire, and everything waiting to go."
        actions={
          <>
            <Button
              variant="outline"
              icon={<Package className="h-4 w-4" />}
              onClick={() => setAdding('equipment')}
            >
              Add equipment
            </Button>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding('vehicle')}>
              Add a vehicle
            </Button>
          </>
        }
      />

      {data.compliance_warnings.length > 0 && (
        <Alert
          tone="danger"
          className="mb-4"
          icon={<AlertTriangle className="h-4 w-4" />}
          title={`${data.compliance_warnings.length} asset${
            data.compliance_warnings.length === 1 ? '' : 's'
          } cannot legally go out`}
        >
          <ul className="mt-1 space-y-0.5 text-sm">
            {data.compliance_warnings.slice(0, 5).map((row) => (
              <li key={row.asset_id}>
                <span className="font-medium">{row.name}</span> — {row.warnings.join('; ')}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Out on hire"
          value={String(data.on_hire)}
          hint={`${data.available} available`}
          icon={<Car className="h-4 w-4" />}
        />
        <StatCard
          label="Overdue returns"
          value={String(data.overdue_returns)}
          tone={data.overdue_returns > 0 ? 'danger' : 'default'}
          icon={<CalendarDays className="h-4 w-4" />}
        />
        <StatCard
          label="In for service"
          value={String(data.in_maintenance)}
          icon={<Wrench className="h-4 w-4" />}
        />
        <StatCard
          label="Hire income this month"
          value={kes(data.revenue_this_month)}
          icon={<Wallet className="h-4 w-4" />}
        />
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={kind} onChange={setKind}>
          <Tab value="">Everything ({data.total_assets})</Tab>
          <Tab value="vehicle">Vehicles ({data.vehicles})</Tab>
          <Tab value="equipment">Equipment ({data.equipment})</Tab>
        </Tabs>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Name, registration or serial"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </div>

      {assets.data?.length ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {assets.data.map((asset) => (
            <Card key={asset.id}>
              <CardBody className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link
                      to={`/fleet/${asset.id}`}
                      className="font-medium text-slate-900 hover:text-brand-700"
                    >
                      {asset.name}
                    </Link>
                    <p className="text-xs text-slate-500">
                      {asset.kind === 'vehicle'
                        ? `${asset.registration_number ?? ''}${
                            asset.year ? ` · ${asset.year}` : ''
                          }`
                        : `${asset.serial_number ?? ''}${
                            asset.category ? ` · ${asset.category}` : ''
                          }`}
                    </p>
                  </div>
                  <Badge tone={STATUS_TONE[asset.status] ?? 'neutral'}>
                    {humanize(asset.status)}
                  </Badge>
                </div>

                <p className="text-sm text-slate-700">
                  {kes(asset.daily_rate)}
                  <span className="text-slate-400"> / day</span>
                  {asset.weekly_rate && (
                    <span className="ml-2 text-xs text-slate-500">
                      {kes(asset.weekly_rate)} / week
                    </span>
                  )}
                </p>

                {asset.current_hirer && (
                  <p className="text-xs text-slate-500">
                    With {asset.current_hirer} ({asset.current_hire})
                  </p>
                )}

                {asset.compliance_warnings.length > 0 && (
                  <p className="rounded bg-danger-50 px-2 py-1 text-xs text-danger-700">
                    {asset.compliance_warnings[0]}
                  </p>
                )}

                {asset.kind === 'vehicle' && asset.mileage !== null && (
                  <p className="text-xs text-slate-400">
                    {asset.mileage.toLocaleString()} km
                    {asset.insurance_expiry
                      ? ` · insured to ${shortDate(asset.insurance_expiry)}`
                      : ''}
                  </p>
                )}
                {asset.kind === 'equipment' && asset.service_due_on && (
                  <p className="text-xs text-slate-400">
                    Service due {shortDate(asset.service_due_on)}
                  </p>
                )}
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Car className="h-6 w-6" />}
            title="Nothing in the fleet yet"
            description="Add a vehicle or a piece of equipment and you can start taking bookings."
            action={
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding('vehicle')}>
                Add a vehicle
              </Button>
            }
          />
        </Card>
      )}

      <AddAssetDialog kind={adding} onClose={() => setAdding(null)} />
    </div>
  )
}

function AddAssetDialog({ kind, onClose }: { kind: AssetKind | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '',
    registration_number: '',
    make: '',
    model: '',
    year: '',
    mileage: '',
    serial_number: '',
    category: '',
    daily_rate: '',
    weekly_rate: '',
    monthly_rate: '',
    deposit_amount: '',
    daily_mileage_limit: '',
    excess_mileage_rate: '',
    fuel_policy: 'full_to_full',
    insurance_expiry: '',
    inspection_expiry: '',
    road_licence_expiry: '',
    service_interval_days: '',
    last_serviced_on: '',
    notes: '',
  })

  const isVehicle = kind === 'vehicle'

  const create = useMutation({
    mutationFn: () =>
      assetsApi.create({
        kind,
        name: form.name,
        daily_rate: form.daily_rate || '0',
        weekly_rate: form.weekly_rate || null,
        monthly_rate: form.monthly_rate || null,
        deposit_amount: form.deposit_amount || '0',
        notes: form.notes || null,
        ...(isVehicle
          ? {
              registration_number: form.registration_number,
              make: form.make || null,
              model: form.model || null,
              year: form.year ? Number(form.year) : null,
              mileage: form.mileage ? Number(form.mileage) : null,
              fuel_policy: form.fuel_policy,
              daily_mileage_limit: form.daily_mileage_limit
                ? Number(form.daily_mileage_limit)
                : null,
              excess_mileage_rate: form.excess_mileage_rate || null,
              insurance_expiry: form.insurance_expiry || null,
              inspection_expiry: form.inspection_expiry || null,
              road_licence_expiry: form.road_licence_expiry || null,
            }
          : {
              serial_number: form.serial_number,
              category: form.category || null,
              service_interval_days: form.service_interval_days
                ? Number(form.service_interval_days)
                : null,
              last_serviced_on: form.last_serviced_on || null,
            }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['assets'] })
      onClose()
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  const valid =
    form.name.length > 1 &&
    Boolean(form.daily_rate) &&
    (isVehicle ? form.registration_number.length > 2 : form.serial_number.length > 1)

  return (
    <Dialog
      open={kind !== null}
      onClose={onClose}
      size="lg"
      title={isVehicle ? 'Add a vehicle' : 'Add equipment'}
      description={
        isVehicle
          ? 'Insurance, inspection and road licence dates are checked before every hand-over.'
          : 'A service interval means the system tells you when it is due, rather than the hirer.'
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
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
              placeholder={isVehicle ? 'Toyota Fielder' : 'Honda generator 5kVA'}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          {isVehicle ? (
            <Field label="Registration" required>
              <Input
                placeholder="KDA 123X"
                value={form.registration_number}
                onChange={(event) =>
                  setForm({ ...form, registration_number: event.target.value })
                }
              />
            </Field>
          ) : (
            <Field label="Serial number" required>
              <Input
                value={form.serial_number}
                onChange={(event) => setForm({ ...form, serial_number: event.target.value })}
              />
            </Field>
          )}
        </div>

        {isVehicle ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <Field label="Make">
              <Input
                value={form.make}
                onChange={(event) => setForm({ ...form, make: event.target.value })}
              />
            </Field>
            <Field label="Model">
              <Input
                value={form.model}
                onChange={(event) => setForm({ ...form, model: event.target.value })}
              />
            </Field>
            <Field label="Year">
              <Input
                type="number"
                value={form.year}
                onChange={(event) => setForm({ ...form, year: event.target.value })}
              />
            </Field>
            <Field label="Odometer (km)">
              <Input
                type="number"
                value={form.mileage}
                onChange={(event) => setForm({ ...form, mileage: event.target.value })}
              />
            </Field>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Category">
              <Input
                placeholder="Power, lifting, compaction"
                value={form.category}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
              />
            </Field>
            <Field label="Service every (days)">
              <Input
                type="number"
                value={form.service_interval_days}
                onChange={(event) =>
                  setForm({ ...form, service_interval_days: event.target.value })
                }
              />
            </Field>
            <Field label="Last serviced">
              <Input
                type="date"
                value={form.last_serviced_on}
                onChange={(event) => setForm({ ...form, last_serviced_on: event.target.value })}
              />
            </Field>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <Field label="Daily rate (KES)" required>
            <Input
              type="number"
              min="0"
              value={form.daily_rate}
              onChange={(event) => setForm({ ...form, daily_rate: event.target.value })}
            />
          </Field>
          <Field label="Weekly rate">
            <Input
              type="number"
              min="0"
              value={form.weekly_rate}
              onChange={(event) => setForm({ ...form, weekly_rate: event.target.value })}
            />
          </Field>
          <Field label="Monthly rate">
            <Input
              type="number"
              min="0"
              value={form.monthly_rate}
              onChange={(event) => setForm({ ...form, monthly_rate: event.target.value })}
            />
          </Field>
          <Field label="Deposit">
            <Input
              type="number"
              min="0"
              value={form.deposit_amount}
              onChange={(event) => setForm({ ...form, deposit_amount: event.target.value })}
            />
          </Field>
        </div>

        {isVehicle && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field label="Fuel policy">
                <Select
                  value={form.fuel_policy}
                  onChange={(event) => setForm({ ...form, fuel_policy: event.target.value })}
                >
                  <option value="full_to_full">Return it full</option>
                  <option value="same_to_same">Return it as taken</option>
                  <option value="prepaid">Fuel prepaid</option>
                </Select>
              </Field>
              <Field label="Daily km included">
                <Input
                  type="number"
                  min="0"
                  placeholder="150"
                  value={form.daily_mileage_limit}
                  onChange={(event) =>
                    setForm({ ...form, daily_mileage_limit: event.target.value })
                  }
                />
              </Field>
              <Field label="Excess km rate (KES)">
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.excess_mileage_rate}
                  onChange={(event) =>
                    setForm({ ...form, excess_mileage_rate: event.target.value })
                  }
                />
              </Field>
            </div>

            <div className="grid grid-cols-1 gap-4 rounded-lg bg-slate-50 p-3 sm:grid-cols-3">
              <Field label="Insurance to">
                <Input
                  type="date"
                  value={form.insurance_expiry}
                  onChange={(event) => setForm({ ...form, insurance_expiry: event.target.value })}
                />
              </Field>
              <Field label="Inspection to">
                <Input
                  type="date"
                  value={form.inspection_expiry}
                  onChange={(event) =>
                    setForm({ ...form, inspection_expiry: event.target.value })
                  }
                />
              </Field>
              <Field label="Road licence to">
                <Input
                  type="date"
                  value={form.road_licence_expiry}
                  onChange={(event) =>
                    setForm({ ...form, road_licence_expiry: event.target.value })
                  }
                />
              </Field>
            </div>
          </>
        )}

        <Field label="Notes">
          <Textarea
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </Field>

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}
