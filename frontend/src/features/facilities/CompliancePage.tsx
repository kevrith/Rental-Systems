import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock, Download, FileText, Plus, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { complianceApi, propertiesApi } from '@/api'
import type { ComplianceStatus, ComplianceType } from '@/api/types'
import { apiClient } from '@/lib/api-client'
import { PageHeader, StatCard } from '@/components/PageHeader'
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
  Textarea,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const TYPES: ComplianceType[] = [
  'fire_safety',
  'health_inspection',
  'nema',
  'lift_inspection',
  'electrical_inspection',
  'water_safety',
  'insurance',
  'business_permit',
  'structural_survey',
  'other',
]

const STATUS_TONE: Record<ComplianceStatus, 'success' | 'warn' | 'danger' | 'neutral'> = {
  valid: 'success',
  expiring_soon: 'warn',
  expired: 'danger',
  missing: 'neutral',
}

const STATUS_LABEL: Record<ComplianceStatus, string> = {
  valid: 'Valid',
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
  missing: 'No expiry recorded',
}

/** The compliance calendar (US-078). Red is the day an insurer refuses a claim,
 *  so it is the loudest thing on the page. */
export function CompliancePage() {
  const [adding, setAdding] = useState(false)
  const [renewing, setRenewing] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const dashboard = useQuery({
    queryKey: queryKeys.complianceDashboard,
    queryFn: complianceApi.dashboard,
  })
  const items = useQuery({
    queryKey: queryKeys.compliance(),
    queryFn: () => complianceApi.list(),
  })

  const downloadReport = async () => {
    setError(null)
    try {
      const response = await apiClient.get(complianceApi.reportUrl(), { responseType: 'blob' })
      const url = URL.createObjectURL(response.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `compliance-report-${today()}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    } catch (downloadError) {
      setError(errorMessage(downloadError))
    }
  }

  if (dashboard.isPending) return <PageLoader />

  const counts = dashboard.data!.counts

  return (
    <div>
      <PageHeader
        title="Compliance"
        description="Every certificate, licence and policy your buildings depend on — and when each one runs out."
        actions={
          <>
            <Button
              variant="outline"
              icon={<Download className="h-4 w-4" />}
              onClick={downloadReport}
            >
              Report
            </Button>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
              Add an item
            </Button>
          </>
        }
      />

      {counts.expired > 0 && (
        <Alert
          tone="danger"
          className="mb-4"
          icon={<ShieldAlert className="h-4 w-4" />}
          title={`${counts.expired} certificate${counts.expired === 1 ? ' has' : 's have'} expired`}
        >
          An expired certificate is the day an insurer refuses a claim. Renew these first.
        </Alert>
      )}

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Valid"
          value={String(counts.valid)}
          tone="success"
          icon={<CheckCircle2 className="h-4 w-4" />}
        />
        <StatCard
          label="Expiring in 60 days"
          value={String(counts.expiring_soon)}
          tone={counts.expiring_soon > 0 ? 'warn' : 'default'}
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          label="Expired"
          value={String(counts.expired)}
          tone={counts.expired > 0 ? 'danger' : 'default'}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <StatCard
          label="No expiry recorded"
          value={String(counts.missing)}
          hint="Held, but unverified"
          icon={<FileText className="h-4 w-4" />}
        />
      </div>

      {dashboard.data!.properties.length ? (
        <div className="space-y-5">
          {dashboard.data!.properties.map((property) => (
            <Card key={property.property_id}>
              <CardHeader>
                <CardTitle>
                  <Link
                    to={`/properties/${property.property_id}`}
                    className="hover:text-brand-700"
                  >
                    {property.property_name}
                  </Link>
                </CardTitle>
                <Badge tone={STATUS_TONE[property.worst]}>{STATUS_LABEL[property.worst]}</Badge>
              </CardHeader>
              <CardBody className="p-0">
                <ul className="divide-y divide-slate-100">
                  {property.items.map((item) => (
                    <li
                      key={item.id}
                      className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
                    >
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900">{item.name}</p>
                        <p className="text-xs text-slate-500">
                          {humanize(item.type)}
                          {item.expires_on ? ` · expires ${shortDate(item.expires_on)}` : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        {item.days_until_expiry !== null && (
                          <span
                            className={
                              item.days_until_expiry < 0
                                ? 'text-sm font-medium text-danger-700'
                                : 'text-sm text-slate-500'
                            }
                          >
                            {item.days_until_expiry < 0
                              ? `${Math.abs(item.days_until_expiry)} days overdue`
                              : `${item.days_until_expiry} days left`}
                          </span>
                        )}
                        <Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</Badge>
                        <button
                          type="button"
                          className="text-sm text-brand-600 hover:text-brand-700"
                          onClick={() => setRenewing(item.id)}
                        >
                          Renew
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="Nothing recorded yet"
            description="Add your fire certificate, NEMA licence and insurance policy, and we will remind you before each one expires."
            action={
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => setAdding(true)}>
                Add an item
              </Button>
            }
          />
        </Card>
      )}

      <AddDialog open={adding} onClose={() => setAdding(false)} />
      <RenewDialog
        itemId={renewing}
        item={items.data?.find((row) => row.id === renewing)}
        onClose={() => setRenewing(null)}
      />
    </div>
  )
}

function AddDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    property_id: '',
    compliance_type: 'fire_safety',
    name: '',
    reference_number: '',
    issued_on: '',
    expires_on: '',
    issuing_authority: '',
    responsible_party: '',
    responsible_phone: '',
    insurer_name: '',
    coverage_amount: '',
    premium_amount: '',
    premium_due_on: '',
    notes: '',
  })

  const properties = useQuery({
    queryKey: queryKeys.properties(),
    queryFn: () => propertiesApi.list(),
    enabled: open,
  })

  const create = useMutation({
    mutationFn: () =>
      complianceApi.create({
        property_id: form.property_id,
        compliance_type: form.compliance_type,
        name: form.name,
        reference_number: form.reference_number || null,
        issued_on: form.issued_on || null,
        expires_on: form.expires_on || null,
        issuing_authority: form.issuing_authority || null,
        responsible_party: form.responsible_party || null,
        responsible_phone: form.responsible_phone || null,
        insurer_name: form.insurer_name || null,
        coverage_amount: form.coverage_amount || null,
        premium_amount: form.premium_amount || null,
        premium_due_on: form.premium_due_on || null,
        notes: form.notes || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['compliance'] })
      onClose()
    },
    onError: (createError) => setError(errorMessage(createError)),
  })

  const isInsurance = form.compliance_type === 'insurance'

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a compliance item"
      description="We will remind you at 90, 60, 30 and 7 days before it expires."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!form.property_id || form.name.length < 2}
            loading={create.isPending}
            onClick={() => {
              setError(null)
              create.mutate()
            }}
          >
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Property" required>
          <Select
            value={form.property_id}
            onChange={(event) => setForm({ ...form, property_id: event.target.value })}
          >
            <option value="">Choose a property</option>
            {properties.data?.map((property) => (
              <option key={property.id} value={property.id}>
                {property.name}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Type" required>
            <Select
              value={form.compliance_type}
              onChange={(event) =>
                setForm({
                  ...form,
                  compliance_type: event.target.value,
                  name: form.name || humanize(event.target.value),
                })
              }
            >
              {TYPES.map((type) => (
                <option key={type} value={type}>
                  {humanize(type)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Name" required>
            <Input
              placeholder="Fire safety certificate"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Issued on">
            <Input
              type="date"
              value={form.issued_on}
              onChange={(event) => setForm({ ...form, issued_on: event.target.value })}
            />
          </Field>
          <Field label="Expires on" hint="Leave blank and we will flag it as unverified">
            <Input
              type="date"
              value={form.expires_on}
              onChange={(event) => setForm({ ...form, expires_on: event.target.value })}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Certificate number">
            <Input
              value={form.reference_number}
              onChange={(event) => setForm({ ...form, reference_number: event.target.value })}
            />
          </Field>
          <Field label="Issued by">
            <Input
              placeholder="Nairobi County Fire Services"
              value={form.issuing_authority}
              onChange={(event) => setForm({ ...form, issuing_authority: event.target.value })}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Who chases the renewal?">
            <Input
              value={form.responsible_party}
              onChange={(event) => setForm({ ...form, responsible_party: event.target.value })}
            />
          </Field>
          <Field label="Their phone">
            <Input
              value={form.responsible_phone}
              onChange={(event) => setForm({ ...form, responsible_phone: event.target.value })}
            />
          </Field>
        </div>

        {isInsurance && (
          <div className="space-y-4 rounded-lg bg-slate-50 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Policy details</p>
            <Field label="Insurer">
              <Input
                value={form.insurer_name}
                onChange={(event) => setForm({ ...form, insurer_name: event.target.value })}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Cover (KES)">
                <Input
                  type="number"
                  min="0"
                  value={form.coverage_amount}
                  onChange={(event) => setForm({ ...form, coverage_amount: event.target.value })}
                />
              </Field>
              <Field label="Premium (KES)">
                <Input
                  type="number"
                  min="0"
                  value={form.premium_amount}
                  onChange={(event) => setForm({ ...form, premium_amount: event.target.value })}
                />
              </Field>
              <Field label="Premium due">
                <Input
                  type="date"
                  value={form.premium_due_on}
                  onChange={(event) => setForm({ ...form, premium_due_on: event.target.value })}
                />
              </Field>
            </div>
          </div>
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

function RenewDialog({
  itemId,
  item,
  onClose,
}: {
  itemId: string | null
  item: import('@/api/types').ComplianceItem | undefined
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [expires, setExpires] = useState('')
  const [reference, setReference] = useState('')
  const [error, setError] = useState<string | null>(null)

  const renew = useMutation({
    mutationFn: () =>
      complianceApi.update(itemId!, {
        expires_on: expires,
        issued_on: today(),
        reference_number: reference || undefined,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['compliance'] })
      setExpires('')
      setReference('')
      onClose()
    },
    onError: (renewError) => setError(errorMessage(renewError)),
  })

  return (
    <Dialog
      open={itemId !== null}
      onClose={onClose}
      title={item ? `Renew ${item.name}` : 'Renew'}
      description="Recording the new expiry restarts the reminder ladder."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!expires}
            loading={renew.isPending}
            onClick={() => {
              setError(null)
              renew.mutate()
            }}
          >
            Record renewal
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {item?.coverage_amount && (
          <p className="text-sm text-slate-600">
            Current cover {kes(item.coverage_amount)}
            {item.insurer_name ? ` with ${item.insurer_name}` : ''}.
          </p>
        )}
        <Field label="New expiry date" required>
          <Input
            type="date"
            min={today()}
            value={expires}
            onChange={(event) => setExpires(event.target.value)}
          />
        </Field>
        <Field label="New certificate number">
          <Input value={reference} onChange={(event) => setReference(event.target.value)} />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}
