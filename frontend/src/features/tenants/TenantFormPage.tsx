import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, AlertTriangle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'

import { tenantsApi } from '@/api'
import { SinglePhotoUpload, type UploadedFile } from '@/components/FileUpload'
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
  Textarea,
} from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const schema = z.object({
  full_name: z.string().min(2, 'Enter the tenant’s full name'),
  phone_number: z
    .string()
    .regex(/^(\+?254|0)?[17]\d{8}$/, 'Enter a Kenyan mobile number, e.g. 0712345678'),
  email: z.string().email('Enter a valid email address').or(z.literal('')).optional(),
  national_id: z.string().optional(),
  employer_name: z.string().optional(),
  occupation: z.string().optional(),
  monthly_income: z.string().optional(),
  emergency_contact_name: z.string().optional(),
  emergency_contact_phone: z.string().optional(),
  emergency_contact_relationship: z.string().optional(),
  notes: z.string().optional(),
})
type FormValues = z.infer<typeof schema>

interface DuplicateWarning {
  field: string
  value: string
  existing_tenant_id: string
  existing_tenant_name: string
}

export function TenantFormPage() {
  const { tenantId } = useParams<{ tenantId: string }>()
  const isEdit = Boolean(tenantId)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [serverError, setServerError] = useState<string | null>(null)
  const [duplicates, setDuplicates] = useState<DuplicateWarning[]>([])
  const [idFront, setIdFront] = useState<UploadedFile | null>(null)
  const [idBack, setIdBack] = useState<UploadedFile | null>(null)
  const [passportPhoto, setPassportPhoto] = useState<UploadedFile | null>(null)

  const existing = useQuery({
    queryKey: queryKeys.tenant(tenantId!),
    queryFn: () => tenantsApi.get(tenantId!),
    enabled: isEdit,
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  useEffect(() => {
    if (!existing.data) return
    reset({
      full_name: existing.data.full_name,
      phone_number: existing.data.phone_number,
      email: existing.data.email ?? '',
      national_id: existing.data.national_id ?? '',
      employer_name: existing.data.employer_name ?? '',
      occupation: existing.data.occupation ?? '',
      monthly_income: existing.data.monthly_income ?? '',
      emergency_contact_name: existing.data.emergency_contact_name ?? '',
      emergency_contact_phone: existing.data.emergency_contact_phone ?? '',
      emergency_contact_relationship: existing.data.emergency_contact_relationship ?? '',
      notes: existing.data.notes ?? '',
    })
  }, [existing.data, reset])

  const buildBody = (values: FormValues, acknowledge: boolean) => ({
    ...values,
    email: values.email || null,
    national_id: values.national_id || null,
    employer_name: values.employer_name || null,
    occupation: values.occupation || null,
    monthly_income: values.monthly_income || null,
    emergency_contact_name: values.emergency_contact_name || null,
    emergency_contact_phone: values.emergency_contact_phone || null,
    emergency_contact_relationship: values.emergency_contact_relationship || null,
    notes: values.notes || null,
    id_photo_front_id: idFront?.id ?? null,
    id_photo_back_id: idBack?.id ?? null,
    passport_photo_id: passportPhoto?.id ?? null,
    acknowledge_duplicate: acknowledge,
  })

  const mutation = useMutation({
    mutationFn: ({ values, acknowledge }: { values: FormValues; acknowledge: boolean }) =>
      isEdit
        ? tenantsApi.update(tenantId!, buildBody(values, acknowledge))
        : tenantsApi.create(buildBody(values, acknowledge)),
    onSuccess: async (tenant) => {
      await queryClient.invalidateQueries({ queryKey: ['tenants'] })
      navigate(`/tenants/${tenant.id}`)
    },
    onError: (error) => {
      // A duplicate comes back as a structured 409 so the UI can show who it
      // clashes with, rather than a bare error string (US-014).
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
        ?.detail
      if (detail && typeof detail === 'object' && 'duplicates' in detail) {
        setDuplicates((detail as { duplicates: DuplicateWarning[] }).duplicates)
        setServerError(null)
        return
      }
      setDuplicates([])
      setServerError(errorMessage(error))
    },
  })

  if (isEdit && existing.isPending) return <PageLoader />

  const submit = (acknowledge: boolean) =>
    handleSubmit((values) => {
      setServerError(null)
      mutation.mutate({ values, acknowledge })
    })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={isEdit ? `Edit ${existing.data?.full_name ?? 'tenant'}` : 'Add a tenant'}
        description={
          isEdit ? undefined : 'Capture their details once — the lease fills itself in later.'
        }
        backTo={isEdit ? `/tenants/${tenantId}` : '/tenants'}
      />

      <form className="space-y-5" onSubmit={submit(false)}>
        <Card>
          <CardHeader>
            <CardTitle>Identity</CardTitle>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Full name"
              required
              error={errors.full_name?.message}
              className="sm:col-span-2"
            >
              <Input
                placeholder="Peter Otieno"
                invalid={Boolean(errors.full_name)}
                {...register('full_name')}
              />
            </Field>

            <Field
              label="Phone number"
              required
              error={errors.phone_number?.message}
              hint="Receipts and reminders go here."
            >
              <Input
                type="tel"
                placeholder="0712 345 678"
                invalid={Boolean(errors.phone_number)}
                {...register('phone_number')}
              />
            </Field>

            <Field label="Email" error={errors.email?.message}>
              <Input
                type="email"
                placeholder="peter@example.com"
                invalid={Boolean(errors.email)}
                {...register('email')}
              />
            </Field>

            <Field label="National ID number">
              <Input placeholder="12345678" {...register('national_id')} />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>KYC documents</CardTitle>
            <span className="text-xs text-slate-500">Stored securely in the tenant vault</span>
          </CardHeader>
          <CardBody className="grid gap-5 sm:grid-cols-3">
            <SinglePhotoUpload
              value={idFront}
              onChange={setIdFront}
              category="tenant_id"
              label="ID — front"
            />
            <SinglePhotoUpload
              value={idBack}
              onChange={setIdBack}
              category="tenant_id"
              label="ID — back"
            />
            <SinglePhotoUpload
              value={passportPhoto}
              onChange={setPassportPhoto}
              category="tenant_passport_photo"
              label="Passport photo"
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Employment</CardTitle>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-3">
            <Field label="Employer">
              <Input placeholder="Safaricom PLC" {...register('employer_name')} />
            </Field>
            <Field label="Occupation">
              <Input placeholder="Engineer" {...register('occupation')} />
            </Field>
            <Field label="Monthly income (KES)">
              <Input type="number" step="0.01" min="0" {...register('monthly_income')} />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Emergency contact</CardTitle>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-3">
            <Field label="Name">
              <Input placeholder="Mary Otieno" {...register('emergency_contact_name')} />
            </Field>
            <Field label="Phone">
              <Input type="tel" placeholder="0722 000 000" {...register('emergency_contact_phone')} />
            </Field>
            <Field label="Relationship">
              <Input placeholder="Sister" {...register('emergency_contact_relationship')} />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardBody>
            <Field label="Internal notes" hint="Only your team can see this.">
              <Textarea placeholder="Anything worth remembering about this tenant." {...register('notes')} />
            </Field>
          </CardBody>
        </Card>

        {duplicates.length > 0 && (
          <Alert
            tone="warn"
            icon={<AlertTriangle className="h-4 w-4" />}
            title="Possible duplicate tenant"
          >
            <ul className="mt-1 space-y-1">
              {duplicates.map((duplicate) => (
                <li key={duplicate.existing_tenant_id}>
                  <Link
                    to={`/tenants/${duplicate.existing_tenant_id}`}
                    className="font-medium underline"
                  >
                    {duplicate.existing_tenant_name}
                  </Link>{' '}
                  already uses this {duplicate.field.replace(/_/g, ' ')}.
                </li>
              ))}
            </ul>
            {duplicates.some((duplicate) => duplicate.field === 'phone_number') ? (
              <p className="mt-2">
                A phone number can only belong to one tenant. Change it, or open the existing record.
              </p>
            ) : (
              <div className="mt-2">
                <Button type="button" size="sm" variant="secondary" onClick={submit(true)}>
                  Save anyway — this is a different person
                </Button>
              </div>
            )}
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
            {isEdit ? 'Save changes' : 'Create tenant'}
          </Button>
        </div>
      </form>
    </div>
  )
}
