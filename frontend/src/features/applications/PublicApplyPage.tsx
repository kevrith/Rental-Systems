import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, BedDouble, Check, MapPin, Ruler } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { publicScreeningApi } from '@/api'
import { FileUpload, type UploadedFile } from '@/components/FileUpload'
import { AuthLayout } from '@/features/auth/AuthLayout'
import {
  Alert,
  Button,
  Field,
  Input,
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { errorMessage, humanize, kes } from '@/lib/format'

const EMPLOYMENT = [
  'employed',
  'self_employed',
  'business_owner',
  'student',
  'retired',
  'unemployed',
]

const STEPS = ['About you', 'Where you live now', 'How you will pay', 'Guarantor']

/** The public application form (US-064). Four short steps rather than one long
 *  page, because most of these are filled in on a phone. */
export function PublicApplyPage() {
  const { unitId } = useParams<{ unitId: string }>()
  const [step, setStep] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [reference, setReference] = useState<string | null>(null)

  const [idDocs, setIdDocs] = useState<UploadedFile[]>([])
  const [photo, setPhoto] = useState<UploadedFile[]>([])
  const [form, setForm] = useState({
    full_name: '',
    phone_number: '',
    email: '',
    national_id: '',
    current_address: '',
    current_landlord_name: '',
    current_landlord_phone: '',
    years_at_current_address: '',
    reason_for_moving: '',
    employment_status: 'employed',
    employer_name: '',
    employer_phone: '',
    job_title: '',
    monthly_income: '',
    months_in_employment: '',
    occupants: '1',
    intended_move_in: '',
    guarantor_name: '',
    guarantor_relationship: '',
    guarantor_phone: '',
  })

  const listing = useQuery({
    queryKey: ['public-listing', unitId],
    queryFn: () => publicScreeningApi.listing(unitId!),
    enabled: Boolean(unitId),
    retry: false,
  })

  const submit = useMutation({
    mutationFn: () =>
      publicScreeningApi.apply(unitId!, {
        unit_id: unitId,
        full_name: form.full_name,
        phone_number: form.phone_number,
        email: form.email || null,
        national_id: form.national_id || null,
        current_address: form.current_address || null,
        current_landlord_name: form.current_landlord_name || null,
        current_landlord_phone: form.current_landlord_phone || null,
        years_at_current_address: form.years_at_current_address || null,
        reason_for_moving: form.reason_for_moving || null,
        employment_status: form.employment_status,
        employer_name: form.employer_name || null,
        employer_phone: form.employer_phone || null,
        job_title: form.job_title || null,
        monthly_income: form.monthly_income || null,
        months_in_employment: form.months_in_employment || null,
        occupants: Number(form.occupants) || 1,
        intended_move_in: form.intended_move_in || null,
        id_document_id: idDocs[0]?.id ?? null,
        passport_photo_id: photo[0]?.id ?? null,
        guarantors: form.guarantor_name
          ? [
              {
                full_name: form.guarantor_name,
                relationship_to_applicant: form.guarantor_relationship || 'Guarantor',
                phone_number: form.guarantor_phone,
              },
            ]
          : [],
      }),
    onSuccess: (result) => setReference(result.reference_code),
    onError: (submitError) => setError(errorMessage(submitError)),
  })

  if (listing.isPending) return <PageLoader />

  if (listing.isError) {
    return (
      <AuthLayout title="This unit is not available">
        <Alert tone="warn">
          The link may be old, or the unit has already been let. Ask the landlord for a current
          link.
        </Alert>
      </AuthLayout>
    )
  }

  if (reference) {
    return (
      <AuthLayout title="Application received">
        <div className="flex flex-col items-center gap-3 text-center">
          <Check className="h-10 w-10 text-money-600" />
          <p className="text-sm text-slate-600">
            Thank you. The landlord has been notified and will be in touch on the number you gave
            us.
          </p>
          <p className="rounded-lg bg-slate-50 px-4 py-2 font-mono text-sm text-slate-800">
            {reference}
          </p>
          <p className="text-xs text-slate-500">Keep this reference — quote it if you call.</p>
        </div>
      </AuthLayout>
    )
  }

  const unit = listing.data
  const canContinue = [
    form.full_name.trim().length > 1 && form.phone_number.trim().length >= 10,
    true,
    form.employment_status === 'unemployed' || Boolean(form.monthly_income),
    true,
  ][step]

  return (
    <AuthLayout
      title={`Apply for unit ${unit.unit_number}`}
      subtitle={`${unit.property_name} · ${kes(unit.monthly_rent)} a month`}
    >
      <div className="space-y-5">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="flex items-start gap-1.5 text-sm text-slate-700">
            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
            {unit.property_address}
          </p>
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
            {unit.bedrooms !== null && (
              <span className="inline-flex items-center gap-1">
                <BedDouble className="h-3.5 w-3.5" />
                {unit.bedrooms} bedroom{unit.bedrooms === 1 ? '' : 's'}
              </span>
            )}
            {unit.unit_type && (
              <span className="inline-flex items-center gap-1">
                <Ruler className="h-3.5 w-3.5" />
                {humanize(unit.unit_type)}
              </span>
            )}
            <span>Deposit {kes(unit.deposit_amount)}</span>
          </div>
        </div>

        <ol className="flex gap-1">
          {STEPS.map((label, index) => (
            <li key={label} className="flex-1">
              <span
                className={
                  index <= step ? 'block h-1 rounded-full bg-brand-500' : 'block h-1 rounded-full bg-slate-200'
                }
              />
              <span
                className={
                  index === step
                    ? 'mt-1 block text-[11px] font-medium text-slate-700'
                    : 'mt-1 block text-[11px] text-slate-400'
                }
              >
                {label}
              </span>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <div className="space-y-4">
            <Field label="Full name" required>
              <Input
                value={form.full_name}
                onChange={(event) => setForm({ ...form, full_name: event.target.value })}
              />
            </Field>
            <Field label="Phone number" required hint="We will contact you on WhatsApp">
              <Input
                placeholder="+2547XXXXXXXX"
                value={form.phone_number}
                onChange={(event) => setForm({ ...form, phone_number: event.target.value })}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="National ID">
                <Input
                  value={form.national_id}
                  onChange={(event) => setForm({ ...form, national_id: event.target.value })}
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm({ ...form, email: event.target.value })}
                />
              </Field>
            </div>
            <FileUpload
              value={photo}
              onChange={setPhoto}
              category="tenant_document"
              max={1}
              label="Passport photo"
              hint="A clear photo of your face"
            />
            <FileUpload
              value={idDocs}
              onChange={setIdDocs}
              category="tenant_document"
              max={1}
              label="ID document"
              hint="A photo of your national ID"
            />
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <Field label="Where do you live now?">
              <Input
                placeholder="Estate, area, town"
                value={form.current_address}
                onChange={(event) => setForm({ ...form, current_address: event.target.value })}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Current landlord's name">
                <Input
                  value={form.current_landlord_name}
                  onChange={(event) =>
                    setForm({ ...form, current_landlord_name: event.target.value })
                  }
                />
              </Field>
              <Field
                label="Their phone"
                hint="We ask them two quick questions about you"
              >
                <Input
                  value={form.current_landlord_phone}
                  onChange={(event) =>
                    setForm({ ...form, current_landlord_phone: event.target.value })
                  }
                />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Years there">
                <Input
                  type="number"
                  step="0.5"
                  min="0"
                  value={form.years_at_current_address}
                  onChange={(event) =>
                    setForm({ ...form, years_at_current_address: event.target.value })
                  }
                />
              </Field>
              <Field label="People moving in">
                <Input
                  type="number"
                  min="1"
                  value={form.occupants}
                  onChange={(event) => setForm({ ...form, occupants: event.target.value })}
                />
              </Field>
            </div>
            <Field label="Why are you moving?">
              <Textarea
                value={form.reason_for_moving}
                onChange={(event) => setForm({ ...form, reason_for_moving: event.target.value })}
              />
            </Field>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <Field label="Employment status" required>
              <Select
                value={form.employment_status}
                onChange={(event) => setForm({ ...form, employment_status: event.target.value })}
              >
                {EMPLOYMENT.map((value) => (
                  <option key={value} value={value}>
                    {humanize(value)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Employer or business name"
              required={['employed', 'business_owner'].includes(form.employment_status)}
            >
              <Input
                value={form.employer_name}
                onChange={(event) => setForm({ ...form, employer_name: event.target.value })}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Your role">
                <Input
                  value={form.job_title}
                  onChange={(event) => setForm({ ...form, job_title: event.target.value })}
                />
              </Field>
              <Field label="Months in this job">
                <Input
                  type="number"
                  min="0"
                  value={form.months_in_employment}
                  onChange={(event) =>
                    setForm({ ...form, months_in_employment: event.target.value })
                  }
                />
              </Field>
            </div>
            <Field
              label="Monthly income (KES)"
              required={form.employment_status !== 'unemployed'}
              hint={`Rent here is ${kes(unit.monthly_rent)} — most landlords look for rent under a third of income`}
            >
              <Input
                type="number"
                min="0"
                value={form.monthly_income}
                onChange={(event) => setForm({ ...form, monthly_income: event.target.value })}
              />
            </Field>
            <Field label="When would you like to move in?">
              <Input
                type="date"
                value={form.intended_move_in}
                onChange={(event) => setForm({ ...form, intended_move_in: event.target.value })}
              />
            </Field>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              A guarantor is someone who agrees to cover the rent if you cannot. We message them to
              confirm — naming someone who has not agreed will not help your application.
            </p>
            <Field label="Guarantor's name">
              <Input
                value={form.guarantor_name}
                onChange={(event) => setForm({ ...form, guarantor_name: event.target.value })}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Relationship to you">
                <Input
                  placeholder="Father, employer, sibling"
                  value={form.guarantor_relationship}
                  onChange={(event) =>
                    setForm({ ...form, guarantor_relationship: event.target.value })
                  }
                />
              </Field>
              <Field label="Their phone">
                <Input
                  placeholder="+2547XXXXXXXX"
                  value={form.guarantor_phone}
                  onChange={(event) => setForm({ ...form, guarantor_phone: event.target.value })}
                />
              </Field>
            </div>
          </div>
        )}

        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}

        <div className="flex gap-2">
          {step > 0 && (
            <Button variant="outline" onClick={() => setStep(step - 1)}>
              Back
            </Button>
          )}
          {step < STEPS.length - 1 ? (
            <Button
              className="flex-1 justify-center"
              disabled={!canContinue}
              onClick={() => setStep(step + 1)}
            >
              Continue
            </Button>
          ) : (
            <Button
              className="flex-1 justify-center"
              size="lg"
              loading={submit.isPending}
              onClick={() => {
                setError(null)
                submit.mutate()
              }}
            >
              Submit application
            </Button>
          )}
        </div>
      </div>
    </AuthLayout>
  )
}
