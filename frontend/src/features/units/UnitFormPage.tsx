import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Info } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

import { propertiesApi, unitsApi, customerSuccessApi } from '@/api'
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
} from '@/components/ui'
import { errorMessage, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const UNIT_TYPES = [
  'Bedsitter', 'Single room', 'Studio', '1 bedroom', '2 bedroom', '3 bedroom', '4 bedroom',
  'Maisonette', 'Bungalow', 'Shop', 'Office', 'Godown', 'Stall',
]

const USE_CLASSES = [
  'office',
  'retail',
  'warehouse',
  'industrial',
  'restaurant',
  'medical',
  'other',
]

const schema = z.object({
  property_id: z.string().uuid('Choose a property'),
  unit_number: z.string().min(1, 'Give the unit a number or name'),
  unit_type: z.string().optional(),
  floor: z.string().optional(),
  size_sqm: z.string().optional(),
  bedrooms: z.string().optional(),
  bathrooms: z.string().optional(),
  monthly_rent: z.string().min(1, 'Enter the monthly rent'),
  deposit_amount: z.string().optional(),
  // Commercial lettings (US-069)
  use_class: z.string().optional(),
  car_bays: z.string().optional(),
})
// `z.coerce` makes the parsed output differ from the raw form input, so both
// sides are named explicitly and threaded through useForm's generics.
type FormInput = z.input<typeof schema>
type FormValues = z.output<typeof schema>

function toNumberOrNull(value?: string): number | null {
  if (!value?.trim()) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function UnitFormPage() {
  const { unitId } = useParams<{ unitId: string }>()
  const [params] = useSearchParams()
  const isEdit = Boolean(unitId)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [serverError, setServerError] = useState<string | null>(null)
  const [photos, setPhotos] = useState<UploadedFile[]>([])

  const properties = useQuery({
    queryKey: queryKeys.properties({ forForm: true }),
    queryFn: () => propertiesApi.list(),
  })

  const existing = useQuery({
    queryKey: queryKeys.unit(unitId!),
    queryFn: () => unitsApi.get(unitId!),
    enabled: isEdit,
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      property_id: params.get('property_id') ?? '',
      monthly_rent: '',
      deposit_amount: '',
    },
  })

  useEffect(() => {
    if (!existing.data) return
    reset({
      property_id: existing.data.property_id,
      unit_number: existing.data.unit_number,
      unit_type: existing.data.unit_type ?? '',
      floor: existing.data.floor ?? '',
      size_sqm: existing.data.size_sqm?.toString() ?? '',
      bedrooms: existing.data.bedrooms?.toString() ?? '',
      bathrooms: existing.data.bathrooms?.toString() ?? '',
      monthly_rent: existing.data.monthly_rent,
      deposit_amount: existing.data.deposit_amount,
      use_class: existing.data.use_class ?? '',
      car_bays: existing.data.car_bays ? String(existing.data.car_bays) : '',
    })
    setPhotos(existing.data.photos.map((p) => ({ id: p.id, url: p.url, filename: p.filename })))
  }, [existing.data, reset])

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const body = {
        property_id: values.property_id,
        unit_number: values.unit_number,
        unit_type: values.unit_type || null,
        floor: values.floor || null,
        size_sqm: toNumberOrNull(values.size_sqm),
        bedrooms: toNumberOrNull(values.bedrooms),
        bathrooms: toNumberOrNull(values.bathrooms),
        monthly_rent: values.monthly_rent,
        deposit_amount: values.deposit_amount || '0',
        use_class: values.use_class || null,
        car_bays: Number(values.car_bays) || 0,
        photo_file_ids: photos.map((photo) => photo.id),
      }
      // The property of an existing unit is fixed — moving a unit between
      // buildings would silently rewrite its tenancy history.
      const { property_id: _fixed, ...editable } = body
      return isEdit ? unitsApi.update(unitId!, editable) : unitsApi.create(body)
    },
    onSuccess: async (unit) => {
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      await queryClient.invalidateQueries({ queryKey: ['properties'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      if (!isEdit) {
        void customerSuccessApi.markOnboardingStep('added_units').then(() =>
          queryClient.invalidateQueries({ queryKey: ['onboarding'] })
        )
      }
      navigate(`/units/${unit.id}`)
    },
    onError: (error) => setServerError(errorMessage(error)),
  })

  if (isEdit && existing.isPending) return <PageLoader />

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title={isEdit ? `Edit unit ${existing.data?.unit_number ?? ''}` : 'Add a unit'}
        backTo={isEdit ? `/units/${unitId}` : '/units'}
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
            <CardTitle>Unit details</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Property" required error={errors.property_id?.message} className="sm:col-span-2">
              <Select disabled={isEdit} invalid={Boolean(errors.property_id)} {...register('property_id')}>
                <option value="">Choose a property</option>
                {properties.data?.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Unit number or name" required error={errors.unit_number?.message}>
              <Input placeholder="A12" invalid={Boolean(errors.unit_number)} {...register('unit_number')} />
            </Field>

            <Field label="Type">
              <Select {...register('unit_type')}>
                <option value="">Not specified</option>
                {UNIT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Floor">
              <Input placeholder="Ground, 1, 2…" {...register('floor')} />
            </Field>

            <Field label="Size (sqm)">
              <Input type="number" step="0.1" min="0" placeholder="45" {...register('size_sqm')} />
            </Field>

            <Field label="Bedrooms">
              <Input type="number" min="0" max="50" placeholder="1" {...register('bedrooms')} />
            </Field>

            <Field label="Bathrooms">
              <Input type="number" min="0" max="50" placeholder="1" {...register('bathrooms')} />
            </Field>

            <Field
              label="Commercial use"
              hint="Only for offices, shops and the like — leave blank for residential"
            >
              <Select {...register('use_class')}>
                <option value="">Residential</option>
                {USE_CLASSES.map((value) => (
                  <option key={value} value={value}>
                    {humanize(value)}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Parking bays">
              <Input type="number" min="0" max="500" placeholder="0" {...register('car_bays')} />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Rent and deposit</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Monthly rent (KES)" required error={errors.monthly_rent?.message}>
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="25000"
                invalid={Boolean(errors.monthly_rent)}
                {...register('monthly_rent')}
              />
            </Field>
            <Field label="Deposit (KES)" hint="Often one month's rent.">
              <Input type="number" step="0.01" min="0" placeholder="25000" {...register('deposit_amount')} />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Photos</CardTitle>
          </CardHeader>
          <CardBody>
            <FileUpload value={photos} onChange={setPhotos} category="unit_photo" max={5} />
          </CardBody>
        </Card>

        {!isEdit && (
          <Alert tone="info" icon={<Info className="h-4 w-4" />}>
            New units start as <strong>Vacant</strong>. They become occupied automatically when you
            create a tenancy.
          </Alert>
        )}

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {isEdit ? 'Save changes' : 'Create unit'}
          </Button>
        </div>
      </form>
    </div>
  )
}

// ------------------------------------------------------------------ bulk create

const bulkSchema = z.object({
  property_id: z.string().uuid('Choose a property'),
  count: z.coerce.number().int().min(1, 'At least one unit').max(500, 'Maximum 500 at a time'),
  name_prefix: z.string().max(32).optional(),
  start_number: z.coerce.number().int().min(0),
  number_padding: z.coerce.number().int().min(0).max(6),
  unit_type: z.string().optional(),
  bedrooms: z.string().optional(),
  bathrooms: z.string().optional(),
  monthly_rent: z.string().min(1, 'Enter the monthly rent'),
  deposit_amount: z.string().optional(),
})
type BulkInput = z.input<typeof bulkSchema>
type BulkValues = z.output<typeof bulkSchema>

/** "This property has 24 identical units" (US-008). */
export function BulkUnitsPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [serverError, setServerError] = useState<string | null>(null)

  const properties = useQuery({
    queryKey: queryKeys.properties({ forBulk: true }),
    queryFn: () => propertiesApi.list(),
  })

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<BulkInput, unknown, BulkValues>({
    resolver: zodResolver(bulkSchema),
    defaultValues: {
      property_id: params.get('property_id') ?? '',
      count: 12,
      name_prefix: 'A',
      start_number: 1,
      number_padding: 2,
      monthly_rent: '',
    },
  })

  const values = watch()

  /** Live preview of the names about to be created — the surest way to catch a
   *  padding or prefix mistake before 24 rows exist. */
  const preview = useMemo(() => {
    const count = Number(values.count) || 0
    const start = Number(values.start_number) || 0
    const padding = Number(values.number_padding) || 0
    const prefix = values.name_prefix ?? ''

    const names: string[] = []
    for (let index = 0; index < Math.min(count, 3); index += 1) {
      const value = String(start + index)
      names.push(`${prefix}${padding ? value.padStart(padding, '0') : value}`)
    }
    if (count > 4) names.push('…')
    if (count > 3) {
      const last = String(start + count - 1)
      names.push(`${prefix}${padding ? last.padStart(padding, '0') : last}`)
    }
    return names
  }, [values.count, values.start_number, values.number_padding, values.name_prefix])

  const mutation = useMutation({
    mutationFn: (formValues: BulkValues) =>
      unitsApi.bulkCreate({
        property_id: formValues.property_id,
        count: formValues.count,
        name_prefix: formValues.name_prefix ?? '',
        start_number: formValues.start_number,
        number_padding: formValues.number_padding,
        unit_type: formValues.unit_type || null,
        bedrooms: toNumberOrNull(formValues.bedrooms),
        bathrooms: toNumberOrNull(formValues.bathrooms),
        monthly_rent: formValues.monthly_rent,
        deposit_amount: formValues.deposit_amount || '0',
      }),
    onSuccess: async (result, formValues) => {
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      await queryClient.invalidateQueries({ queryKey: ['properties'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void customerSuccessApi.markOnboardingStep('added_units').then(() =>
        queryClient.invalidateQueries({ queryKey: ['onboarding'] })
      )
      navigate(`/properties/${formValues.property_id}`, {
        state: { message: `${result.created} units created` },
      })
    },
    onError: (error) => setServerError(errorMessage(error)),
  })

  const unitCount = Number(values.count) || 0
  const totalRent = unitCount * (Number(values.monthly_rent) || 0)

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Add many units at once"
        description="Create a whole block of identical units with sequential names."
        backTo="/units"
      />

      <form
        className="space-y-5"
        onSubmit={handleSubmit((formValues) => {
          setServerError(null)
          mutation.mutate(formValues)
        })}
      >
        <Card>
          <CardHeader>
            <CardTitle>Naming</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Property" required error={errors.property_id?.message} className="sm:col-span-2">
              <Select invalid={Boolean(errors.property_id)} {...register('property_id')}>
                <option value="">Choose a property</option>
                {properties.data?.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="How many units?" required error={errors.count?.message}>
              <Input type="number" min="1" max="500" {...register('count')} />
            </Field>

            <Field label="Name prefix" hint="e.g. A gives A01, A02…">
              <Input placeholder="A" {...register('name_prefix')} />
            </Field>

            <Field label="Start numbering at">
              <Input type="number" min="0" {...register('start_number')} />
            </Field>

            <Field label="Zero padding" hint="2 gives 01, 3 gives 001. Use 0 for none.">
              <Input type="number" min="0" max="6" {...register('number_padding')} />
            </Field>

            <div className="sm:col-span-2">
              <p className="mb-1.5 text-sm font-medium text-slate-700">Preview</p>
              <div className="flex flex-wrap gap-1.5 rounded-lg bg-slate-50 p-3">
                {preview.map((name, index) => (
                  <span
                    key={`${name}-${index}`}
                    className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-xs text-slate-700"
                  >
                    {name}
                  </span>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Shared details</CardTitle>
            <span className="text-xs text-slate-500">Applied to every unit</span>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Type">
              <Select {...register('unit_type')}>
                <option value="">Not specified</option>
                {UNIT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Bedrooms">
              <Input type="number" min="0" placeholder="1" {...register('bedrooms')} />
            </Field>
            <Field label="Bathrooms">
              <Input type="number" min="0" placeholder="1" {...register('bathrooms')} />
            </Field>
            <Field label="Monthly rent (KES)" required error={errors.monthly_rent?.message}>
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="18000"
                invalid={Boolean(errors.monthly_rent)}
                {...register('monthly_rent')}
              />
            </Field>
            <Field label="Deposit (KES)">
              <Input type="number" step="0.01" min="0" {...register('deposit_amount')} />
            </Field>
          </CardBody>
        </Card>

        {totalRent > 0 && (
          <Alert tone="info" icon={<Info className="h-4 w-4" />}>
            {unitCount} units at {kes(values.monthly_rent)} each adds{' '}
            <strong>{kes(totalRent)}</strong> of monthly rent potential.
          </Alert>
        )}

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Create {unitCount} unit{unitCount === 1 ? '' : 's'}
          </Button>
        </div>
      </form>
    </div>
  )
}
