import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Check, FileText, Home, UserRound } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { propertiesApi, tenanciesApi, tenantsApi, unitsApi } from '@/api'
import type { Unit } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Field,
  Input,
  Select,
  Spinner,
  linkButtonClass,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { errorMessage, kes, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

type Step = 'unit' | 'tenant' | 'terms' | 'review'

const STEPS: { key: Step; label: string; icon: React.ReactNode }[] = [
  { key: 'unit', label: 'Unit', icon: <Home className="h-4 w-4" /> },
  { key: 'tenant', label: 'Tenant', icon: <UserRound className="h-4 w-4" /> },
  { key: 'terms', label: 'Terms', icon: <FileText className="h-4 w-4" /> },
  { key: 'review', label: 'Review', icon: <Check className="h-4 w-4" /> },
]

interface Terms {
  start_date: string
  end_date: string
  is_open_ended: boolean
  monthly_rent: string
  deposit_amount: string
  billing_day: string
  notice_period_days: string
  payment_method: string
  generate_lease: boolean
}

/**
 * Tenancy creation wizard (US-015, US-016).
 *
 * Four steps, because this is the one flow where a mistake is expensive: the
 * unit flips to occupied and a lease PDF is generated the moment it is
 * submitted. The review step shows exactly what is about to happen.
 */
export function TenancyWizardPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [step, setStep] = useState<Step>(params.get('unit_id') ? 'tenant' : 'unit')
  const [unitId, setUnitId] = useState(params.get('unit_id') ?? '')
  const [tenantId, setTenantId] = useState(params.get('tenant_id') ?? '')
  const [serverError, setServerError] = useState<string | null>(null)
  const [terms, setTerms] = useState<Terms>({
    start_date: today(),
    end_date: '',
    is_open_ended: false,
    monthly_rent: '',
    deposit_amount: '',
    billing_day: '1',
    notice_period_days: '30',
    payment_method: 'mpesa',
    generate_lease: true,
  })

  const vacantUnits = useQuery({
    queryKey: queryKeys.units({ unit_status: 'vacant' }),
    queryFn: () => unitsApi.list({ unit_status: 'vacant' }),
  })

  const properties = useQuery({
    queryKey: queryKeys.properties({ forWizard: true }),
    queryFn: () => propertiesApi.list(),
  })

  const tenants = useQuery({
    queryKey: queryKeys.tenants({ forWizard: true }),
    queryFn: () => tenantsApi.list(),
  })

  const selectedUnit = vacantUnits.data?.find((unit) => unit.id === unitId)
  const selectedTenant = tenants.data?.find((tenant) => tenant.id === tenantId)
  const propertyName = (id: string) =>
    properties.data?.find((property) => property.id === id)?.name ?? ''

  const create = useMutation({
    mutationFn: () =>
      tenanciesApi.create({
        tenant_id: tenantId,
        unit_id: unitId,
        start_date: terms.start_date,
        end_date: terms.is_open_ended ? null : terms.end_date,
        is_open_ended: terms.is_open_ended,
        monthly_rent: terms.monthly_rent,
        deposit_amount: terms.deposit_amount || '0',
        billing_day: Number(terms.billing_day),
        notice_period_days: Number(terms.notice_period_days),
        payment_method: terms.payment_method,
        generate_lease: terms.generate_lease,
      }),
    onSuccess: async (tenancy) => {
      await queryClient.invalidateQueries({ queryKey: ['tenancies'] })
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      await queryClient.invalidateQueries({ queryKey: ['tenants'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      navigate(`/tenancies/${tenancy.id}`)
    },
    onError: (error) => setServerError(errorMessage(error)),
  })

  /** Selecting a unit seeds the rent and deposit from the unit's own figures. */
  const chooseUnit = (unit: Unit) => {
    setUnitId(unit.id)
    setTerms((current) => ({
      ...current,
      monthly_rent: current.monthly_rent || unit.monthly_rent,
      deposit_amount: current.deposit_amount || unit.deposit_amount,
    }))
    setStep('tenant')
  }

  const canContinue = {
    unit: Boolean(unitId),
    tenant: Boolean(tenantId),
    terms:
      Boolean(terms.start_date && terms.monthly_rent) &&
      (terms.is_open_ended || Boolean(terms.end_date)),
    review: true,
  }[step]

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="New tenancy"
        description="Link a tenant to a unit and generate their lease."
        backTo="/tenancies"
      />

      <Stepper current={step} />

      <div className="mt-5">
        {step === 'unit' && (
          <Card>
            <CardHeader>
              <CardTitle>Choose a vacant unit</CardTitle>
              <span className="text-xs text-slate-500">
                {vacantUnits.data?.length ?? 0} available
              </span>
            </CardHeader>
            {vacantUnits.isPending ? (
              <CardBody className="flex justify-center py-10">
                <Spinner />
              </CardBody>
            ) : vacantUnits.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {vacantUnits.data.map((unit) => (
                  <li key={unit.id}>
                    <button
                      type="button"
                      onClick={() => chooseUnit(unit)}
                      className={cn(
                        'flex w-full items-center justify-between gap-3 px-5 py-3 text-left hover:bg-slate-50',
                        unitId === unit.id && 'bg-brand-50',
                      )}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">
                          Unit {unit.unit_number}
                        </p>
                        <p className="truncate text-xs text-slate-500">
                          {propertyName(unit.property_id)}
                          {unit.unit_type ? ` · ${unit.unit_type}` : ''}
                        </p>
                      </div>
                      <span className="shrink-0 text-sm font-medium text-slate-700">
                        {kes(unit.monthly_rent)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Home className="h-6 w-6" />}
                title="No vacant units"
                description="Every unit is currently occupied or under maintenance."
                action={
                  <Link to="/units/new" className={linkButtonClass('outline')}>
                    Add a unit
                  </Link>
                }
              />
            )}
          </Card>
        )}

        {step === 'tenant' && (
          <Card>
            <CardHeader>
              <CardTitle>Choose the tenant</CardTitle>
              <Link to="/tenants/new" className={linkButtonClass('outline', 'sm')}>
                Add new tenant
              </Link>
            </CardHeader>
            {tenants.isPending ? (
              <CardBody className="flex justify-center py-10">
                <Spinner />
              </CardBody>
            ) : tenants.data?.length ? (
              <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
                {tenants.data.map((tenant) => {
                  const hasActive = Boolean(tenant.tenancy_id)
                  return (
                    <li key={tenant.id}>
                      <button
                        type="button"
                        disabled={hasActive}
                        onClick={() => {
                          setTenantId(tenant.id)
                          setStep('terms')
                        }}
                        className={cn(
                          'flex w-full items-center justify-between gap-3 px-5 py-3 text-left',
                          hasActive
                            ? 'cursor-not-allowed opacity-50'
                            : 'hover:bg-slate-50',
                          tenantId === tenant.id && 'bg-brand-50',
                        )}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-900">{tenant.full_name}</p>
                          <p className="text-xs text-slate-500">{tenant.phone_number}</p>
                        </div>
                        {hasActive && <Badge tone="warn">Already renting</Badge>}
                      </button>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <EmptyState
                icon={<UserRound className="h-6 w-6" />}
                title="No tenants yet"
                description="Create the tenant's profile first."
                action={
                  <Link to="/tenants/new" className={linkButtonClass()}>
                    Add a tenant
                  </Link>
                }
              />
            )}
          </Card>
        )}

        {step === 'terms' && (
          <Card>
            <CardHeader>
              <CardTitle>Tenancy terms</CardTitle>
            </CardHeader>
            <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Start date" required>
                <Input
                  type="date"
                  value={terms.start_date}
                  onChange={(event) =>
                    setTerms({ ...terms, start_date: event.target.value })
                  }
                />
              </Field>

              <Field label="End date" required={!terms.is_open_ended}>
                <Input
                  type="date"
                  disabled={terms.is_open_ended}
                  value={terms.end_date}
                  onChange={(event) => setTerms({ ...terms, end_date: event.target.value })}
                />
              </Field>

              <label className="flex items-center gap-2 text-sm text-slate-600 sm:col-span-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-brand-600"
                  checked={terms.is_open_ended}
                  onChange={(event) =>
                    setTerms({ ...terms, is_open_ended: event.target.checked })
                  }
                />
                Open-ended (month to month, no fixed end date)
              </label>

              <Field label="Monthly rent (KES)" required>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={terms.monthly_rent}
                  onChange={(event) => setTerms({ ...terms, monthly_rent: event.target.value })}
                />
              </Field>

              <Field label="Deposit (KES)">
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={terms.deposit_amount}
                  onChange={(event) => setTerms({ ...terms, deposit_amount: event.target.value })}
                />
              </Field>

              <Field label="Rent due on" hint="Day of the month the invoice is raised.">
                <Select
                  value={terms.billing_day}
                  onChange={(event) => setTerms({ ...terms, billing_day: event.target.value })}
                >
                  {Array.from({ length: 28 }, (_, index) => index + 1).map((day) => (
                    <option key={day} value={day}>
                      Day {day}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Notice period (days)">
                <Input
                  type="number"
                  min="0"
                  max="365"
                  value={terms.notice_period_days}
                  onChange={(event) =>
                    setTerms({ ...terms, notice_period_days: event.target.value })
                  }
                />
              </Field>

              <Field label="Preferred payment method" className="sm:col-span-2">
                <Select
                  value={terms.payment_method}
                  onChange={(event) => setTerms({ ...terms, payment_method: event.target.value })}
                >
                  <option value="mpesa">M-Pesa</option>
                  <option value="bank_transfer">Bank transfer</option>
                  <option value="cash">Cash</option>
                  <option value="cheque">Cheque</option>
                </Select>
              </Field>

              <label className="flex items-start gap-2 text-sm text-slate-600 sm:col-span-2">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-brand-600"
                  checked={terms.generate_lease}
                  onChange={(event) =>
                    setTerms({ ...terms, generate_lease: event.target.checked })
                  }
                />
                <span>
                  Generate the lease agreement now
                  <span className="block text-xs text-slate-400">
                    A professional PDF is filed in the tenant&apos;s document vault.
                  </span>
                </span>
              </label>
            </CardBody>
          </Card>
        )}

        {step === 'review' && (
          <Card>
            <CardHeader>
              <CardTitle>Review and confirm</CardTitle>
            </CardHeader>
            <CardBody className="space-y-4">
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Summary label="Tenant" value={selectedTenant?.full_name ?? '—'} />
                <Summary label="Phone" value={selectedTenant?.phone_number ?? '—'} />
                <Summary
                  label="Unit"
                  value={
                    selectedUnit
                      ? `${selectedUnit.unit_number} · ${propertyName(selectedUnit.property_id)}`
                      : '—'
                  }
                />
                <Summary label="Monthly rent" value={kes(terms.monthly_rent)} />
                <Summary label="Deposit" value={kes(terms.deposit_amount || '0')} />
                <Summary
                  label="Term"
                  value={
                    terms.is_open_ended
                      ? `From ${terms.start_date} (open-ended)`
                      : `${terms.start_date} → ${terms.end_date}`
                  }
                />
                <Summary label="Rent due on" value={`Day ${terms.billing_day} of each month`} />
                <Summary label="Notice period" value={`${terms.notice_period_days} days`} />
              </dl>

              <Alert tone="info">
                On confirmation, unit {selectedUnit?.unit_number} becomes{' '}
                <strong>occupied</strong>
                {terms.generate_lease && ', and the lease PDF is generated and filed'}.
              </Alert>

              {serverError && (
                <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
                  {serverError}
                </Alert>
              )}
            </CardBody>
          </Card>
        )}
      </div>

      <div className="mt-5 flex items-center justify-between">
        <Button
          variant="ghost"
          disabled={step === 'unit'}
          onClick={() => {
            const index = STEPS.findIndex((entry) => entry.key === step)
            setStep(STEPS[Math.max(0, index - 1)].key)
          }}
        >
          Back
        </Button>

        {step === 'review' ? (
          <Button
            loading={create.isPending}
            onClick={() => {
              setServerError(null)
              create.mutate()
            }}
          >
            Create tenancy
          </Button>
        ) : (
          <Button
            disabled={!canContinue}
            onClick={() => {
              const index = STEPS.findIndex((entry) => entry.key === step)
              setStep(STEPS[Math.min(STEPS.length - 1, index + 1)].key)
            }}
          >
            Continue
          </Button>
        )}
      </div>
    </div>
  )
}

function Stepper({ current }: { current: Step }) {
  const currentIndex = STEPS.findIndex((step) => step.key === current)

  return (
    <ol className="flex items-center gap-1 overflow-x-auto">
      {STEPS.map((step, index) => {
        const done = index < currentIndex
        const active = index === currentIndex
        return (
          <li key={step.key} className="flex flex-1 items-center gap-1">
            <div
              className={cn(
                'flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm',
                active
                  ? 'bg-brand-50 font-medium text-brand-700'
                  : done
                    ? 'text-money-700'
                    : 'text-slate-400',
              )}
            >
              <span
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-full text-xs',
                  active
                    ? 'bg-brand-600 text-white'
                    : done
                      ? 'bg-money-100 text-money-700'
                      : 'bg-slate-100 text-slate-400',
                )}
              >
                {done ? <Check className="h-3.5 w-3.5" /> : index + 1}
              </span>
              {step.label}
            </div>
            {index < STEPS.length - 1 && (
              <span
                className={cn('h-px flex-1', done ? 'bg-money-300' : 'bg-slate-200')}
                aria-hidden
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-slate-800">{value}</dd>
    </div>
  )
}
