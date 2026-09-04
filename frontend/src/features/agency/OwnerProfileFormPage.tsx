import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'

import { agencyApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardDescription,
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
  full_name: z.string().min(2, 'Enter the owner’s full name'),
  phone_number: z
    .string()
    .regex(/^(\+?254|0)?[17]\d{8}$/, 'Enter a Kenyan mobile number, e.g. 0712345678'),
  email: z.string().email('Enter a valid email address').or(z.literal('')).optional(),
  national_id: z.string().optional(),
  kra_pin: z.string().optional(),
  bank_name: z.string().optional(),
  bank_account_number: z.string().optional(),
  bank_account_name: z.string().optional(),
  mpesa_phone: z.string().optional(),
  management_fee_percent: z.coerce
    .number()
    .min(0, 'Fee cannot be negative')
    .max(100, 'Fee cannot exceed 100%'),
  disbursement_day: z.coerce
    .number()
    .int()
    .min(1, 'Pick a day between 1 and 28')
    .max(28, 'Use 28 or lower so every month has that day'),
  maintenance_auto_approve_limit: z.coerce.number().min(0, 'Cannot be negative'),
  maintenance_notify_limit: z.coerce.number().min(0, 'Cannot be negative'),
  notes: z.string().optional(),
})
// `z.coerce` makes the parsed output differ from the raw form input, so both
// sides are named explicitly and threaded through useForm's generics.
type FormInput = z.input<typeof schema>
type FormValues = z.output<typeof schema>

export function OwnerProfileFormPage() {
  const { ownerId } = useParams<{ ownerId: string }>()
  const isEdit = Boolean(ownerId)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [serverError, setServerError] = useState<string | null>(null)

  const existing = useQuery({
    queryKey: queryKeys.ownerProfile(ownerId!),
    queryFn: () => agencyApi.ownerProfile(ownerId!),
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
      management_fee_percent: 8,
      disbursement_day: 5,
      maintenance_auto_approve_limit: 5000,
      maintenance_notify_limit: 20000,
    },
  })

  useEffect(() => {
    if (!existing.data) return
    const owner = existing.data
    reset({
      full_name: owner.full_name,
      phone_number: owner.phone_number,
      email: owner.email ?? '',
      national_id: owner.national_id ?? '',
      kra_pin: owner.kra_pin ?? '',
      bank_name: owner.bank_name ?? '',
      bank_account_number: owner.bank_account_number ?? '',
      bank_account_name: owner.bank_account_name ?? '',
      mpesa_phone: owner.mpesa_phone ?? '',
      management_fee_percent: Number(owner.management_fee_percent),
      disbursement_day: owner.disbursement_day,
      maintenance_auto_approve_limit: Number(owner.maintenance_auto_approve_limit),
      maintenance_notify_limit: Number(owner.maintenance_notify_limit),
      notes: owner.notes ?? '',
    })
  }, [existing.data, reset])

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      const body = {
        ...values,
        email: values.email || null,
        national_id: values.national_id || null,
        kra_pin: values.kra_pin || null,
        bank_name: values.bank_name || null,
        bank_account_number: values.bank_account_number || null,
        bank_account_name: values.bank_account_name || null,
        mpesa_phone: values.mpesa_phone || null,
        notes: values.notes || null,
        management_fee_percent: String(values.management_fee_percent),
        maintenance_auto_approve_limit: String(values.maintenance_auto_approve_limit),
        maintenance_notify_limit: String(values.maintenance_notify_limit),
      }
      return isEdit ? agencyApi.updateOwnerProfile(ownerId!, body) : agencyApi.createOwnerProfile(body)
    },
    onSuccess: async (owner) => {
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
      navigate(`/agency/owners/${owner.id}`)
    },
    onError: (error) => setServerError(errorMessage(error)),
  })

  if (isEdit && existing.isPending) return <PageLoader />

  return (
    <div>
      <PageHeader
        title={isEdit ? 'Edit owner client' : 'Add owner client'}
        description="Contact details, payout destination, and the terms of your management agreement."
        backTo={isEdit ? `/agency/owners/${ownerId}` : '/agency/owners'}
        backLabel={isEdit ? 'Owner' : 'Owner clients'}
      />

      {serverError && (
        <Alert tone="danger" className="mb-4">
          {serverError}
        </Alert>
      )}

      <form
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
        className="space-y-4"
      >
        <Card>
          <CardHeader>
            <CardTitle>Who they are</CardTitle>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" required error={errors.full_name?.message}>
              <Input {...register('full_name')} placeholder="Margaret Wanjiku" />
            </Field>
            <Field label="Phone number" required error={errors.phone_number?.message}>
              <Input {...register('phone_number')} placeholder="0712345678" />
            </Field>
            <Field label="Email" error={errors.email?.message}>
              <Input {...register('email')} type="email" placeholder="margaret@example.com" />
            </Field>
            <Field
              label="National ID or company reg. no."
              error={errors.national_id?.message}
            >
              <Input {...register('national_id')} />
            </Field>
            <Field
              label="KRA PIN"
              hint="Used on eTIMS receipts issued in this owner's name."
              error={errors.kra_pin?.message}
            >
              <Input {...register('kra_pin')} placeholder="A012345678Z" />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Where their money goes</CardTitle>
            <CardDescription>
              Used when you disburse their net rent. M-Pesa is usually fastest.
            </CardDescription>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field label="M-Pesa number" error={errors.mpesa_phone?.message}>
              <Input {...register('mpesa_phone')} placeholder="0712345678" />
            </Field>
            <Field label="Bank name" error={errors.bank_name?.message}>
              <Input {...register('bank_name')} placeholder="Equity Bank" />
            </Field>
            <Field label="Account name" error={errors.bank_account_name?.message}>
              <Input {...register('bank_account_name')} />
            </Field>
            <Field label="Account number" error={errors.bank_account_number?.message}>
              <Input {...register('bank_account_number')} />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Management agreement</CardTitle>
            <CardDescription>
              The terms this owner has agreed to. These drive fee deductions and how much you
              can spend on repairs without asking.
            </CardDescription>
          </CardHeader>
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Management fee (%)"
              required
              hint="Deducted from every payment collected for this owner."
              error={errors.management_fee_percent?.message}
            >
              <Input {...register('management_fee_percent')} type="number" step="0.01" />
            </Field>
            <Field
              label="Disbursement day"
              required
              hint="Day of the month you pay them out. 28 or lower so it exists in February."
              error={errors.disbursement_day?.message}
            >
              <Input {...register('disbursement_day')} type="number" min={1} max={28} />
            </Field>
            <Field
              label="Auto-approve repairs up to (KES)"
              hint="You proceed without asking the owner."
              error={errors.maintenance_auto_approve_limit?.message}
            >
              <Input {...register('maintenance_auto_approve_limit')} type="number" step="1" />
            </Field>
            <Field
              label="Notify owner above (KES)"
              hint="Above this, the owner must approve before work begins."
              error={errors.maintenance_notify_limit?.message}
            >
              <Input {...register('maintenance_notify_limit')} type="number" step="1" />
            </Field>
            <Field label="Notes" className="sm:col-span-2" error={errors.notes?.message}>
              <Textarea {...register('notes')} rows={3} />
            </Field>
          </CardBody>
        </Card>

        <div className="flex items-center gap-2">
          <Button type="submit" loading={mutation.isPending}>
            {isEdit ? 'Save changes' : 'Add owner client'}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => navigate(isEdit ? `/agency/owners/${ownerId}` : '/agency/owners')}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  )
}
