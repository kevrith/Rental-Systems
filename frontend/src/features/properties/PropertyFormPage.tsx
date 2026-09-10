import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'

import { propertiesApi, customerSuccessApi } from '@/api'
import { FileUpload, type UploadedFile } from '@/components/FileUpload'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Field,
  Input,
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** Kenya's 47 counties, so addresses stay consistent for reporting. */
const COUNTIES = [
  'Baringo', 'Bomet', 'Bungoma', 'Busia', 'Elgeyo-Marakwet', 'Embu', 'Garissa', 'Homa Bay',
  'Isiolo', 'Kajiado', 'Kakamega', 'Kericho', 'Kiambu', 'Kilifi', 'Kirinyaga', 'Kisii', 'Kisumu',
  'Kitui', 'Kwale', 'Laikipia', 'Lamu', 'Machakos', 'Makueni', 'Mandera', 'Marsabit', 'Meru',
  'Migori', 'Mombasa', 'Murang’a', 'Nairobi', 'Nakuru', 'Nandi', 'Narok', 'Nyamira',
  'Nyandarua', 'Nyeri', 'Samburu', 'Siaya', 'Taita-Taveta', 'Tana River', 'Tharaka-Nithi',
  'Trans Nzoia', 'Turkana', 'Uasin Gishu', 'Vihiga', 'Wajir', 'West Pokot',
]

const PROPERTY_TYPES = [
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'mixed_use', label: 'Mixed use' },
  { value: 'vehicle_fleet', label: 'Vehicle fleet' },
  { value: 'equipment', label: 'Equipment' },
  { value: 'event_space', label: 'Event space' },
  { value: 'land', label: 'Land' },
]

const AMENITIES = [
  'Parking', 'Borehole', 'Backup generator', 'Lift', 'Security', 'CCTV', 'Gym', 'Swimming pool',
  'Playground', 'Garbage collection', 'Water tank', 'Perimeter wall', 'Internet',
]

const schema = z.object({
  name: z.string().min(2, 'Give the property a name'),
  property_type: z.string(),
  address: z.string().min(3, 'Enter the street address'),
  county: z.string().optional(),
  sub_county: z.string().optional(),
  description: z.string().optional(),
  water_rate_per_unit: z.string().optional(),
  electricity_rate_per_unit: z.string().optional(),
  grace_period_days: z.coerce.number().int().min(0).max(90),
  // An empty `late_fee_type` means this property charges no late fee at all,
  // which is the default — a landlord opts in per property.
  late_fee_type: z.enum(['', 'fixed', 'percent', 'daily']),
  late_fee_amount: z.string().optional(),
  late_fee_cap: z.string().optional(),
  maintenance_budget_monthly: z.string().optional(),
})
// `z.coerce` makes the parsed output differ from the raw form input, so both
// sides are named explicitly and threaded through useForm's generics.
type FormInput = z.input<typeof schema>
type FormValues = z.output<typeof schema>

export function PropertyFormPage() {
  const { propertyId } = useParams<{ propertyId: string }>()
  const isEdit = Boolean(propertyId)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [serverError, setServerError] = useState<string | null>(null)
  const [amenities, setAmenities] = useState<string[]>([])
  const [photos, setPhotos] = useState<UploadedFile[]>([])

  const existing = useQuery({
    queryKey: queryKeys.property(propertyId!),
    queryFn: () => propertiesApi.get(propertyId!),
    enabled: isEdit,
  })

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      property_type: 'residential',
      grace_period_days: 5,
      late_fee_type: '',
    },
  })

  useEffect(() => {
    if (!existing.data) return
    reset({
      name: existing.data.name,
      property_type: existing.data.property_type,
      address: existing.data.address,
      county: existing.data.county ?? '',
      sub_county: existing.data.sub_county ?? '',
      description: existing.data.description ?? '',
      water_rate_per_unit: existing.data.water_rate_per_unit ?? '',
      electricity_rate_per_unit: existing.data.electricity_rate_per_unit ?? '',
      grace_period_days: existing.data.grace_period_days,
      late_fee_type: existing.data.late_fee_type ?? '',
      late_fee_amount: existing.data.late_fee_amount ?? '',
      late_fee_cap: existing.data.late_fee_cap ?? '',
      maintenance_budget_monthly: existing.data.maintenance_budget_monthly ?? '',
    })
    setAmenities(existing.data.amenities ?? [])
    setPhotos(existing.data.photos.map((p) => ({ id: p.id, url: p.url, filename: p.filename })))
  }, [existing.data, reset])

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const body = {
        ...values,
        county: values.county || null,
        sub_county: values.sub_county || null,
        description: values.description || null,
        // Blank rate means "this property doesn't meter that utility", which the
        // backend reads as null, not zero.
        water_rate_per_unit: values.water_rate_per_unit || null,
        electricity_rate_per_unit: values.electricity_rate_per_unit || null,
        // All three go together: no type means no fee, so the amount and cap are
        // cleared with it rather than left as stale numbers.
        late_fee_type: values.late_fee_type || null,
        late_fee_amount: values.late_fee_type ? values.late_fee_amount || null : null,
        late_fee_cap: values.late_fee_type ? values.late_fee_cap || null : null,
        // Blank means no allowance set, and the cost report simply omits variance.
        maintenance_budget_monthly: values.maintenance_budget_monthly || null,
        amenities,
        photo_file_ids: photos.map((photo) => photo.id),
      }
      return isEdit ? propertiesApi.update(propertyId!, body) : propertiesApi.create(body)
    },
    onSuccess: async (property) => {
      await queryClient.invalidateQueries({ queryKey: ['properties'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      if (!isEdit) {
        void customerSuccessApi.markOnboardingStep('added_property').then(() =>
          queryClient.invalidateQueries({ queryKey: ['onboarding'] })
        )
      }
      navigate(`/properties/${property.id}`)
    },
    onError: (error) => setServerError(errorMessage(error)),
  })

  const lateFeeType = watch('late_fee_type')

  if (isEdit && existing.isPending) return <PageLoader />

  const toggleAmenity = (amenity: string) =>
    setAmenities((current) =>
      current.includes(amenity) ? current.filter((a) => a !== amenity) : [...current, amenity],
    )

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={isEdit ? `Edit ${existing.data?.name ?? 'property'}` : 'Add a property'}
        description={
          isEdit
            ? 'Update the details for this property.'
            : 'Start with the basics — you can add units next.'
        }
        backTo={isEdit ? `/properties/${propertyId}` : '/properties'}
      />

      <form
        className="space-y-5"
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
      >
        <Card>
          <CardHeader>
            <CardTitle>Basics</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Property name" required error={errors.name?.message} className="sm:col-span-2">
              <Input
                placeholder="Kilimani Heights"
                invalid={Boolean(errors.name)}
                {...register('name')}
              />
            </Field>

            <Field label="Type" error={errors.property_type?.message}>
              <Select {...register('property_type')}>
                {PROPERTY_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="County" error={errors.county?.message}>
              <Select {...register('county')}>
                <option value="">Select a county</option>
                {COUNTIES.map((county) => (
                  <option key={county} value={county}>
                    {county}
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Street address"
              required
              error={errors.address?.message}
              className="sm:col-span-2"
            >
              <Input
                placeholder="Argwings Kodhek Road, opposite Yaya Centre"
                invalid={Boolean(errors.address)}
                {...register('address')}
              />
            </Field>

            <Field label="Estate or sub-county" error={errors.sub_county?.message}>
              <Input placeholder="Kilimani" {...register('sub_county')} />
            </Field>

            <Field
              label="Rent grace period"
              hint="Days after the due date before rent counts as late."
              error={errors.grace_period_days?.message}
            >
              <Input type="number" min={0} max={90} {...register('grace_period_days')} />
            </Field>

            <Field
              label="Monthly maintenance budget (KES)"
              hint="Optional. Repair spend is reported against it each month."
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="15000.00"
                {...register('maintenance_budget_monthly')}
              />
            </Field>

            <Field label="Description" className="sm:col-span-2">
              <Textarea
                placeholder="Anything a caretaker or tenant should know about this property."
                {...register('description')}
              />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Late fees</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Applied automatically once rent is past the grace period above. Tenants are told on
              WhatsApp when a fee is added, and you can waive one at any time.
            </p>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field
              label="How it is charged"
              hint="Leave as “No late fee” to charge nothing here."
              error={errors.late_fee_type?.message}
            >
              <Select {...register('late_fee_type')}>
                <option value="">No late fee</option>
                <option value="fixed">Fixed amount, once</option>
                <option value="percent">Percentage of the balance</option>
                <option value="daily">Per day overdue</option>
              </Select>
            </Field>
            <Field
              label={
                lateFeeType === 'percent' ? 'Percentage (%)' : 'Amount (KES)'
              }
              hint={
                lateFeeType === 'daily'
                  ? 'Charged for each day past the grace period.'
                  : lateFeeType === 'percent'
                    ? 'Of whatever is still outstanding.'
                    : 'A single flat charge.'
              }
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                disabled={!lateFeeType}
                placeholder={lateFeeType === 'percent' ? '5' : '500.00'}
                {...register('late_fee_amount')}
              />
            </Field>
            <Field
              label="Cap (KES)"
              hint="Optional ceiling, so an old arrear cannot compound past it."
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                disabled={!lateFeeType}
                placeholder="3000.00"
                {...register('late_fee_cap')}
              />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Utility rates</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Water rate (KES per unit)"
              hint="Leave blank if water is not metered here."
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="150.00"
                {...register('water_rate_per_unit')}
              />
            </Field>
            <Field
              label="Electricity rate (KES per unit)"
              hint="Leave blank if electricity is billed directly by the supplier."
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="25.00"
                {...register('electricity_rate_per_unit')}
              />
            </Field>
            <p className="text-xs text-slate-500 sm:col-span-2">
              Meter readings are priced with these rates and added to the tenant&apos;s next invoice
              automatically.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Amenities</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="flex flex-wrap gap-2">
              {AMENITIES.map((amenity) => {
                const selected = amenities.includes(amenity)
                return (
                  <button
                    key={amenity}
                    type="button"
                    onClick={() => toggleAmenity(amenity)}
                    aria-pressed={selected}
                    className={
                      selected
                        ? 'rounded-full border border-brand-600 bg-brand-50 px-3 py-1.5 text-sm text-brand-700'
                        : 'rounded-full border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50'
                    }
                  >
                    {amenity}
                  </button>
                )
              })}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Photos</CardTitle>
          </CardHeader>
          <CardBody>
            <FileUpload
              value={photos}
              onChange={setPhotos}
              category="property_photo"
              max={10}
              hint="Up to 10 photos. The first one becomes the cover image."
            />
          </CardBody>
        </Card>

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => navigate(isEdit ? `/properties/${propertyId}` : '/properties')}
          >
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {isEdit ? 'Save changes' : 'Create property'}
          </Button>
        </div>
      </form>
    </div>
  )
}
