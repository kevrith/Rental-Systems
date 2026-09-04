import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Hammer,
  Phone,
  Plus,
  Search,
  Star,
  UserRoundX,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { vendorsApi } from '@/api'
import type { Vendor, VendorSpecialty } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
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
  Select,
  Skeleton,
  Textarea,
} from '@/components/ui'
import { errorMessage, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export const SPECIALTIES: VendorSpecialty[] = [
  'plumbing',
  'electrical',
  'carpentry',
  'painting',
  'masonry',
  'roofing',
  'appliance',
  'cleaning',
  'pest_control',
  'security',
  'landscaping',
  'general',
]

/** A vendor's average score, or a quiet note that they have none yet. */
export function Rating({ value, count }: { value: number | null; count?: number }) {
  if (value === null) {
    return <span className="text-xs text-slate-400">Not yet rated</span>
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-700">
      <Star className="h-3.5 w-3.5 fill-warn-400 text-warn-400" />
      {value.toFixed(1)}
      {count ? <span className="font-normal text-slate-400">({count})</span> : null}
    </span>
  )
}

export function VendorsPage() {
  const [search, setSearch] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [editing, setEditing] = useState<Vendor | null>(null)
  const [creating, setCreating] = useState(false)

  const canManage = useAuthStore((state) => state.user?.permissions?.includes('vendor:manage'))

  const vendors = useQuery({
    queryKey: queryKeys.vendors({ search, specialty, includeInactive }),
    queryFn: () =>
      vendorsApi.list({
        search: search || undefined,
        specialty: specialty || undefined,
        include_inactive: includeInactive || undefined,
      }),
  })

  return (
    <div>
      <PageHeader
        title="Vendors"
        description="The contractors you trust, ranked by how their jobs actually went."
        actions={
          canManage && (
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
              Add a vendor
            </Button>
          )
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by name, company or phone"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Select
          className="w-auto min-w-44"
          value={specialty}
          onChange={(event) => setSpecialty(event.target.value)}
        >
          <option value="">Any specialty</option>
          {SPECIALTIES.map((value) => (
            <option key={value} value={value}>
              {humanize(value)}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300"
            checked={includeInactive}
            onChange={(event) => setIncludeInactive(event.target.checked)}
          />
          Show inactive
        </label>
      </div>

      {vendors.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
      ) : vendors.data?.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {vendors.data.map((vendor) => (
            <Card key={vendor.id} className={vendor.is_active ? undefined : 'opacity-60'}>
              <CardBody className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link
                      to={`/vendors/${vendor.id}`}
                      className="font-medium text-slate-900 hover:text-brand-700"
                    >
                      {vendor.name}
                    </Link>
                    {vendor.company_name && (
                      <p className="truncate text-xs text-slate-500">{vendor.company_name}</p>
                    )}
                  </div>
                  {!vendor.is_active && <Badge tone="neutral">Inactive</Badge>}
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {vendor.specialties.map((value) => (
                    <Badge key={value} tone="brand">
                      {humanize(value)}
                    </Badge>
                  ))}
                </div>

                <div className="flex items-center justify-between text-xs text-slate-500">
                  <a
                    href={`tel:${vendor.phone_number}`}
                    className="inline-flex items-center gap-1.5 hover:text-brand-700"
                  >
                    <Phone className="h-3.5 w-3.5" />
                    {vendor.phone_number}
                  </a>
                  <Rating value={vendor.average_rating} count={vendor.rating_count} />
                </div>

                <div className="flex items-center justify-between border-t border-slate-100 pt-2 text-xs text-slate-500">
                  <span>
                    {vendor.jobs_completed} job{vendor.jobs_completed === 1 ? '' : 's'}
                  </span>
                  {vendor.jobs_completed > 0 && <span>avg {kes(vendor.average_job_cost)}</span>}
                  {canManage && (
                    <button
                      type="button"
                      className="font-medium text-brand-600 hover:text-brand-700"
                      onClick={() => setEditing(vendor)}
                    >
                      Edit
                    </button>
                  )}
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Hammer className="h-6 w-6" />}
            title="No vendors yet"
            description="Add the plumbers, electricians and fundis you already call, so assigning a job takes one tap."
            action={
              canManage && (
                <Button icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
                  Add a vendor
                </Button>
              )
            }
          />
        </Card>
      )}

      <VendorDialog
        open={creating || editing !== null}
        vendor={editing}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
      />
    </div>
  )
}

export function VendorDialog({
  open,
  vendor,
  onClose,
  onCreated,
}: {
  open: boolean
  vendor?: Vendor | null
  onClose: () => void
  onCreated?: (vendor: Vendor) => void
}) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const [form, setForm] = useState({
    name: '',
    company_name: '',
    phone_number: '',
    email: '',
    rate_notes: '',
    notes: '',
    specialties: [] as VendorSpecialty[],
    is_active: true,
  })
  // Reset the form whenever the dialog is pointed at a different vendor.
  const [loadedId, setLoadedId] = useState<string | null>(null)
  const currentId = vendor?.id ?? null
  if (open && loadedId !== currentId) {
    setLoadedId(currentId)
    setForm({
      name: vendor?.name ?? '',
      company_name: vendor?.company_name ?? '',
      phone_number: vendor?.phone_number ?? '',
      email: vendor?.email ?? '',
      rate_notes: vendor?.rate_notes ?? '',
      notes: vendor?.notes ?? '',
      specialties: vendor?.specialties ?? [],
      is_active: vendor?.is_active ?? true,
    })
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: form.name.trim(),
        company_name: form.company_name.trim() || null,
        phone_number: form.phone_number.trim(),
        email: form.email.trim() || null,
        rate_notes: form.rate_notes.trim() || null,
        notes: form.notes.trim() || null,
        specialties: form.specialties,
        ...(vendor ? { is_active: form.is_active } : {}),
      }
      return vendor ? vendorsApi.update(vendor.id, body) : vendorsApi.create(body)
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ['vendors'] })
      onCreated?.(saved)
      onClose()
    },
    onError: (saveError) => setError(errorMessage(saveError)),
  })

  const toggle = (value: VendorSpecialty) =>
    setForm((state) => ({
      ...state,
      specialties: state.specialties.includes(value)
        ? state.specialties.filter((item) => item !== value)
        : [...state.specialties, value],
    }))

  const valid = form.name.trim().length > 1 && form.phone_number.trim().length >= 10 && form.specialties.length > 0

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={vendor ? `Edit ${vendor.name}` : 'Add a vendor'}
      description="Specialties drive which jobs this vendor is suggested for."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!valid}
            loading={save.isPending}
            onClick={() => {
              setError(null)
              save.mutate()
            }}
          >
            {vendor ? 'Save changes' : 'Add vendor'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" required>
            <Input
              placeholder="John Mwangi"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Company" hint="Optional">
            <Input
              placeholder="Mwangi Plumbing Works"
              value={form.company_name}
              onChange={(event) => setForm({ ...form, company_name: event.target.value })}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Phone" required hint="Used for the WhatsApp job alert">
            <Input
              placeholder="+2547XXXXXXXX"
              value={form.phone_number}
              onChange={(event) => setForm({ ...form, phone_number: event.target.value })}
            />
          </Field>
          <Field label="Email" hint="Optional">
            <Input
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </Field>
        </div>

        <Field label="Specialties" required>
          <div className="flex flex-wrap gap-2">
            {SPECIALTIES.map((value) => {
              const selected = form.specialties.includes(value)
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => toggle(value)}
                  className={
                    selected
                      ? 'rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white'
                      : 'rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50'
                  }
                >
                  {humanize(value)}
                </button>
              )
            })}
          </div>
        </Field>

        <Field label="Rates" hint="Free text — callout fee, day rate, whatever they quote">
          <Input
            placeholder="KES 1,500 callout, then per job"
            value={form.rate_notes}
            onChange={(event) => setForm({ ...form, rate_notes: event.target.value })}
          />
        </Field>

        <Field label="Notes">
          <Textarea
            placeholder="Reliable on emergencies. Prefers jobs in Westlands and Parklands."
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </Field>

        {vendor && (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={form.is_active}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
            />
            Active — available for new job assignments
          </label>
        )}

        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}
      </div>
    </Dialog>
  )
}

export function DeactivateVendorButton({
  vendor,
  openJobs = 0,
}: {
  vendor: Vendor
  openJobs?: number
}) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const deactivate = useMutation({
    mutationFn: () => vendorsApi.deactivate(vendor.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['vendors'] }),
    onError: (deactivateError) => setError(errorMessage(deactivateError)),
  })

  if (!vendor.is_active) return null

  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        icon={<UserRoundX className="h-4 w-4" />}
        // The server refuses this too; disabling it just saves the round trip.
        disabled={openJobs > 0}
        loading={deactivate.isPending}
        onClick={() => {
          setError(null)
          deactivate.mutate()
        }}
      >
        Deactivate
      </Button>
      {openJobs > 0 && (
        <p className="text-xs text-slate-500">
          Reassign their {openJobs} job{openJobs === 1 ? '' : 's'} in progress first.
        </p>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
    </div>
  )
}
