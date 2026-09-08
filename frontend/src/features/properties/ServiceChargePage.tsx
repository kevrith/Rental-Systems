import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Building2, PiggyBank, Receipt, Scale } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { propertiesApi, serviceChargesApi } from '@/api'
import type { ServiceChargeCategory } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
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
  PageLoader,
  Select,
  Table,
  Tab,
  Tabs,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const CATEGORIES: ServiceChargeCategory[] = [
  'security',
  'cleaning',
  'common_area_maintenance',
  'generator',
  'lift',
  'water',
  'landscaping',
  'insurance',
  'management',
  'other',
]

const APPORTIONMENTS = [
  { value: 'fixed_per_unit', label: 'The same amount per unit' },
  { value: 'by_floor_area', label: 'Split the pool by floor area' },
  { value: 'by_occupied_unit', label: 'Split the pool between occupied units' },
]

function firstOfMonth(): string {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10)
}

export function ServiceChargePage() {
  const { propertyId } = useParams<{ propertyId: string }>()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('setup')
  const [error, setError] = useState<string | null>(null)

  const property = useQuery({
    queryKey: queryKeys.property(propertyId!),
    queryFn: () => propertiesApi.get(propertyId!),
    enabled: Boolean(propertyId),
  })

  const scheme = useQuery({
    queryKey: queryKeys.serviceCharge(propertyId!),
    queryFn: () => serviceChargesApi.forProperty(propertyId!),
    enabled: Boolean(propertyId),
  })

  const [form, setForm] = useState({
    name: 'Service charge',
    apportionment: 'fixed_per_unit',
    fixed_amount: '',
    monthly_pool: '',
    sinking_fund_percent: '0',
    is_active: true,
    bill_with_rent: true,
  })
  const [budgets, setBudgets] = useState<{ category: ServiceChargeCategory; monthly_budget: string }[]>(
    [],
  )

  useEffect(() => {
    if (!scheme.data) return
    setForm({
      name: scheme.data.name,
      apportionment: scheme.data.apportionment,
      fixed_amount: scheme.data.fixed_amount,
      monthly_pool: scheme.data.monthly_pool,
      sinking_fund_percent: scheme.data.sinking_fund_percent,
      is_active: scheme.data.is_active,
      bill_with_rent: scheme.data.bill_with_rent,
    })
    setBudgets(
      scheme.data.budgets.map((line) => ({
        category: line.category,
        monthly_budget: line.monthly_budget,
      })),
    )
  }, [scheme.data])

  const save = useMutation({
    mutationFn: () =>
      serviceChargesApi.save(propertyId!, {
        ...form,
        fixed_amount: form.fixed_amount || '0',
        monthly_pool: form.monthly_pool || '0',
        sinking_fund_percent: form.sinking_fund_percent || '0',
        budgets: budgets.filter((line) => Number(line.monthly_budget) > 0),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['service-charges'] }),
    onError: (saveError) => setError(errorMessage(saveError)),
  })

  if (property.isPending || scheme.isPending) return <PageLoader />

  const record = scheme.data
  const proportional = form.apportionment !== 'fixed_per_unit'

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Service charge"
        description={property.data?.name}
        backTo={`/properties/${propertyId}`}
        backLabel="Back to the property"
        actions={
          record && !record.is_active ? <Badge tone="neutral">Not charging</Badge> : undefined
        }
      />

      {record && (
        <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard
            label="Billed each month"
            value={kes(record.monthly_total)}
            hint={`Across ${record.units.length} unit(s)`}
            icon={<Receipt className="h-4 w-4" />}
          />
          <StatCard
            label="Reserve balance"
            value={kes(record.sinking_fund_balance)}
            hint={`${record.sinking_fund_percent}% of every charge`}
            icon={<PiggyBank className="h-4 w-4" />}
          />
          <StatCard
            label="Method"
            value={humanize(record.apportionment)}
            icon={<Scale className="h-4 w-4" />}
          />
        </div>
      )}

      <Tabs value={tab} onChange={setTab}>
        <Tab value="setup">Setup</Tab>
        <Tab value="expenses">Expenses</Tab>
        <Tab value="reconciliation">Reconciliation</Tab>
        <Tab value="reserve">Reserve</Tab>
      </Tabs>

      <div className="mt-4">
        {tab === 'setup' && (
          <div className="space-y-5">
            <Card>
              <CardHeader>
                <CardTitle>How the charge works</CardTitle>
              </CardHeader>
              <CardBody className="space-y-4">
                <Field label="Name on the invoice">
                  <Input
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                  />
                </Field>

                <Field label="How is it split?" required>
                  <Select
                    value={form.apportionment}
                    onChange={(event) => setForm({ ...form, apportionment: event.target.value })}
                  >
                    {APPORTIONMENTS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </Field>

                {proportional ? (
                  <Field
                    label="The building's monthly cost (KES)"
                    required
                    hint="This whole amount is divided between the units"
                  >
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.monthly_pool}
                      onChange={(event) => setForm({ ...form, monthly_pool: event.target.value })}
                    />
                  </Field>
                ) : (
                  <Field label="Amount per unit per month (KES)" required>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.fixed_amount}
                      onChange={(event) => setForm({ ...form, fixed_amount: event.target.value })}
                    />
                  </Field>
                )}

                <Field
                  label="Hold back for capital work (%)"
                  hint="Moved into the reserve as each charge is billed, for roofs and lifts rather than this month's cleaning"
                >
                  <Input
                    type="number"
                    min="0"
                    max="50"
                    step="0.5"
                    value={form.sinking_fund_percent}
                    onChange={(event) =>
                      setForm({ ...form, sinking_fund_percent: event.target.value })
                    }
                  />
                </Field>

                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300"
                      checked={form.is_active}
                      onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                    />
                    Charge this property a service charge
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300"
                      checked={form.bill_with_rent}
                      onChange={(event) =>
                        setForm({ ...form, bill_with_rent: event.target.checked })
                      }
                    />
                    Add it to the monthly rent invoice
                  </label>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>What the money is for</CardTitle>
                <span className="text-sm text-slate-500">
                  Budget per category, per month
                </span>
              </CardHeader>
              <CardBody className="space-y-3">
                {CATEGORIES.map((category) => {
                  const line = budgets.find((item) => item.category === category)
                  return (
                    <div key={category} className="grid grid-cols-[1fr_auto] items-center gap-3">
                      <span className="text-sm text-slate-700">{humanize(category)}</span>
                      <Input
                        className="w-36"
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        value={line?.monthly_budget ?? ''}
                        onChange={(event) => {
                          const value = event.target.value
                          setBudgets((state) => {
                            const rest = state.filter((item) => item.category !== category)
                            return value
                              ? [...rest, { category, monthly_budget: value }]
                              : rest
                          })
                        }}
                      />
                    </div>
                  )
                })}
              </CardBody>
            </Card>

            {error && (
              <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
                {error}
              </Alert>
            )}

            <Button
              size="lg"
              loading={save.isPending}
              onClick={() => {
                setError(null)
                save.mutate()
              }}
            >
              Save the scheme
            </Button>

            {record && record.units.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>What each unit pays</CardTitle>
                </CardHeader>
                <CardBody className="p-0">
                  <div className="overflow-x-auto">
                    <Table>
                      <thead>
                        <tr>
                          <Th>Unit</Th>
                          <Th>Floor area</Th>
                          <Th>Status</Th>
                          <Th>Monthly charge</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {record.units.map((unit) => (
                          <tr key={unit.unit_id}>
                            <Td>{unit.unit_number}</Td>
                            <Td className="text-slate-500">
                              {unit.size_sqm ? `${unit.size_sqm} m²` : '—'}
                            </Td>
                            <Td>
                              <Badge tone={unit.occupied ? 'success' : 'warn'}>
                                {unit.occupied ? 'Occupied' : 'Vacant'}
                              </Badge>
                            </Td>
                            <Td>{kes(unit.monthly_charge)}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </CardBody>
              </Card>
            )}
          </div>
        )}

        {tab === 'expenses' && record && <ExpensesTab schemeId={record.id} />}
        {tab === 'reconciliation' && record && <ReconciliationTab schemeId={record.id} />}
        {tab === 'reserve' && record && <ReserveTab schemeId={record.id} />}

        {tab !== 'setup' && !record && (
          <Card>
            <EmptyState
              icon={<Building2 className="h-6 w-6" />}
              title="No scheme yet"
              description="Set the charge up first, then come back to record what the building spends."
            />
          </Card>
        )}
      </div>
    </div>
  )
}

function ExpensesTab({ schemeId }: { schemeId: string }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    category: 'security',
    amount: '',
    incurred_on: today(),
    description: '',
  })
  const [error, setError] = useState<string | null>(null)

  const expenses = useQuery({
    queryKey: queryKeys.serviceChargeExpenses(schemeId),
    queryFn: () => serviceChargesApi.expenses(schemeId),
  })

  const record = useMutation({
    mutationFn: () => serviceChargesApi.recordExpense(schemeId, form),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['service-charges'] })
      setForm({ ...form, amount: '', description: '' })
    },
    onError: (recordError) => setError(errorMessage(recordError)),
  })

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Record what was spent</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Category" required>
              <Select
                value={form.category}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {humanize(category)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Amount (KES)" required>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={form.amount}
                onChange={(event) => setForm({ ...form, amount: event.target.value })}
              />
            </Field>
            <Field label="Date" required>
              <Input
                type="date"
                max={today()}
                value={form.incurred_on}
                onChange={(event) => setForm({ ...form, incurred_on: event.target.value })}
              />
            </Field>
          </div>
          <Field label="What was it for?" required>
            <Textarea
              placeholder="Guards for the month — Alpha Security"
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button
            disabled={!form.amount || form.description.length < 3}
            loading={record.isPending}
            onClick={() => {
              setError(null)
              record.mutate()
            }}
          >
            Record it
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent spend</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {expenses.data?.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Category</Th>
                    <Th>What</Th>
                    <Th>Amount</Th>
                  </tr>
                </thead>
                <tbody>
                  {expenses.data.map((expense) => (
                    <tr key={expense.id}>
                      <Td className="text-slate-500">{shortDate(expense.incurred_on)}</Td>
                      <Td>{humanize(expense.category)}</Td>
                      <Td className="text-slate-600">{expense.description}</Td>
                      <Td>{kes(expense.amount)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<Receipt className="h-6 w-6" />}
              title="Nothing recorded"
              description="Log what the building actually spends, and the reconciliation writes itself."
            />
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function ReconciliationTab({ schemeId }: { schemeId: string }) {
  const [from, setFrom] = useState(firstOfMonth())
  const [to, setTo] = useState(today())

  const report = useQuery({
    queryKey: queryKeys.serviceChargeReconciliation(schemeId, from, to),
    queryFn: () =>
      serviceChargesApi.reconciliation(schemeId, { period_start: from, period_end: to }),
  })

  return (
    <div className="space-y-5">
      <Card>
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="From">
            <Input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
          </Field>
          <Field label="To">
            <Input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
          </Field>
        </CardBody>
      </Card>

      {report.data && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Budgeted" value={kes(report.data.total_budgeted)} />
            <StatCard label="Charged to tenants" value={kes(report.data.total_charged)} />
            <StatCard label="Actually spent" value={kes(report.data.total_spent)} />
            <StatCard
              label={report.data.surplus_or_deficit >= 0 ? 'Surplus' : 'Deficit'}
              value={kes(Math.abs(report.data.surplus_or_deficit))}
              tone={report.data.surplus_or_deficit >= 0 ? 'success' : 'danger'}
              hint={
                report.data.surplus_or_deficit >= 0
                  ? 'Owed back to tenants or into the reserve'
                  : 'The landlord is subsidising the building'
              }
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>By category</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              {report.data.lines.length ? (
                <div className="overflow-x-auto">
                  <Table>
                    <thead>
                      <tr>
                        <Th>Category</Th>
                        <Th>Budgeted</Th>
                        <Th>Spent</Th>
                        <Th>Variance</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.data.lines.map((line) => (
                        <tr key={line.category}>
                          <Td>{humanize(line.category)}</Td>
                          <Td>{kes(line.budgeted)}</Td>
                          <Td>{kes(line.spent)}</Td>
                          <Td>
                            <span
                              className={
                                line.over_budget ? 'font-medium text-danger-700' : 'text-money-700'
                              }
                            >
                              {line.over_budget ? '−' : '+'}
                              {kes(Math.abs(line.variance))}
                            </span>
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              ) : (
                <EmptyState
                  icon={<Scale className="h-6 w-6" />}
                  title="Nothing to reconcile"
                  description="Set budgets and record expenses, and this fills itself in."
                />
              )}
            </CardBody>
          </Card>
        </>
      )}
    </div>
  )
}

function ReserveTab({ schemeId }: { schemeId: string }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    movement: 'withdrawal',
    amount: '',
    entry_date: today(),
    description: '',
  })
  const [error, setError] = useState<string | null>(null)

  const entries = useQuery({
    queryKey: queryKeys.sinkingFund(schemeId),
    queryFn: () => serviceChargesApi.sinkingFund(schemeId),
  })

  const record = useMutation({
    mutationFn: () => serviceChargesApi.recordSinkingFund(schemeId, form),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['service-charges'] })
      setForm({ ...form, amount: '', description: '' })
    },
    onError: (recordError) => setError(errorMessage(recordError)),
  })

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Move money in or out of the reserve</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Movement" required>
              <Select
                value={form.movement}
                onChange={(event) => setForm({ ...form, movement: event.target.value })}
              >
                <option value="withdrawal">Spend from the reserve</option>
                <option value="contribution">Pay into the reserve</option>
              </Select>
            </Field>
            <Field label="Amount (KES)" required>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={form.amount}
                onChange={(event) => setForm({ ...form, amount: event.target.value })}
              />
            </Field>
            <Field label="Date" required>
              <Input
                type="date"
                value={form.entry_date}
                onChange={(event) => setForm({ ...form, entry_date: event.target.value })}
              />
            </Field>
          </div>
          <Field label="What for?" required>
            <Input
              placeholder="Lift motor replacement"
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button
            disabled={!form.amount || form.description.length < 3}
            loading={record.isPending}
            onClick={() => {
              setError(null)
              record.mutate()
            }}
          >
            Record the movement
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Reserve ledger</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {entries.data?.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Movement</Th>
                    <Th>What</Th>
                    <Th>Amount</Th>
                  </tr>
                </thead>
                <tbody>
                  {entries.data.map((entry) => (
                    <tr key={entry.id}>
                      <Td className="text-slate-500">{shortDate(entry.entry_date)}</Td>
                      <Td>
                        <Badge tone={entry.movement === 'contribution' ? 'success' : 'warn'}>
                          {humanize(entry.movement)}
                        </Badge>
                      </Td>
                      <Td className="text-slate-600">{entry.description}</Td>
                      <Td>
                        {entry.movement === 'withdrawal' ? '−' : '+'}
                        {kes(entry.amount)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<PiggyBank className="h-6 w-6" />}
              title="The reserve is empty"
              description="It fills automatically as service charges are billed, if you set a percentage."
            />
          )}
        </CardBody>
      </Card>
    </div>
  )
}
