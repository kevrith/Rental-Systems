import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Download, Eye, LogOut, Receipt, RefreshCw, UserPlus, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { coTenantsApi, invoicesApi, noticesApi, paymentsApi, tenanciesApi, tenantsApi } from '@/api'
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
  INVOICE_STATUS_TONE,
  Input,
  PAYMENT_STATUS_TONE,
  PageLoader,
  Select,
  TENANCY_STATUS_TONE,
  Textarea,
  linkButtonClass,
} from '@/components/ui'
import { API_BASE_URL } from '@/lib/api-client'
import { errorMessage, humanize, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function TenancyDetailPage() {
  const { tenancyId } = useParams<{ tenancyId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [vacateOpen, setVacateOpen] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManage = permissions?.includes('tenancy:manage')
  const canInvoice = permissions?.includes('invoice:manage')
  const canPay = permissions?.includes('payment:record')

  const tenancy = useQuery({
    queryKey: queryKeys.tenancy(tenancyId!),
    queryFn: () => tenanciesApi.get(tenancyId!),
    enabled: Boolean(tenancyId),
  })

  const invoices = useQuery({
    queryKey: queryKeys.invoices({ tenancy_id: tenancyId }),
    queryFn: () => invoicesApi.list({ tenancy_id: tenancyId, limit: 12 }),
    enabled: Boolean(tenancyId),
  })

  const payments = useQuery({
    queryKey: queryKeys.payments({ tenancy_id: tenancyId }),
    queryFn: () => paymentsApi.list({ tenancy_id: tenancyId, limit: 12 }),
    enabled: Boolean(tenancyId),
  })

  const notices = useQuery({
    queryKey: queryKeys.vacateNotices({ tenancy_id: tenancyId }),
    queryFn: () => noticesApi.list({ tenancy_id: tenancyId }),
    enabled: Boolean(tenancyId),
  })

  const generateInvoice = useMutation({
    mutationFn: () => invoicesApi.generate({ tenancy_id: tenancyId! }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['invoices'] })
      await queryClient.invalidateQueries({ queryKey: ['tenancy'] })
      setNotice({ tone: 'success', text: 'Invoice generated and sent to the tenant.' })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const regenerateLease = useMutation({
    mutationFn: () => tenanciesApi.regenerateLease(tenancyId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tenancy'] })
      setNotice({ tone: 'success', text: 'A fresh lease PDF was generated and filed.' })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  if (tenancy.isPending) return <PageLoader />
  if (tenancy.isError) {
    return (
      <Alert tone="danger" title="Could not load this tenancy">
        {errorMessage(tenancy.error)}
      </Alert>
    )
  }

  const record = tenancy.data
  const activeNotice = notices.data?.find((entry) => entry.status !== 'withdrawn')

  return (
    <div>
      <PageHeader
        title={`${record.tenant_name} · Unit ${record.unit_number}`}
        description={`${record.reference_code} · ${record.property_name}`}
        backTo="/tenancies"
        backLabel="All tenancies"
        actions={
          <>
            {canPay && record.status !== 'vacated' && (
              <Link
                to={`/payments/new?tenancy_id=${tenancyId}`}
                className={linkButtonClass('outline')}
              >
                <CreditCard className="h-4 w-4" />
                Record payment
              </Link>
            )}
            {canInvoice && record.status !== 'vacated' && (
              <Button
                variant="outline"
                icon={<Receipt className="h-4 w-4" />}
                loading={generateInvoice.isPending}
                onClick={() => generateInvoice.mutate()}
              >
                Generate invoice
              </Button>
            )}
            {canManage && record.status !== 'vacated' && (
              <Button
                variant="ghost"
                icon={<LogOut className="h-4 w-4" />}
                onClick={() => setVacateOpen(true)}
              >
                End tenancy
              </Button>
            )}
          </>
        }
      />

      {notice && (
        <Alert tone={notice.tone} className="mb-5">
          {notice.text}
        </Alert>
      )}

      {activeNotice && (
        <Alert
          tone={activeNotice.meets_notice_period ? 'warn' : 'danger'}
          className="mb-5"
          title={`Notice to vacate on ${shortDate(activeNotice.move_out_date)}`}
        >
          {activeNotice.notice_days_given} days&apos; notice given
          {!activeNotice.meets_notice_period &&
            ` — short of the ${activeNotice.required_notice_days} days required`}
          . {activeNotice.status === 'submitted' && 'Acknowledge it and schedule the move-out inspection.'}
          {activeNotice.document_url && (
            <>
              {' '}
              <a href={activeNotice.document_url} target="_blank" rel="noreferrer" className="underline">
                Download the notice
              </a>
              .
            </>
          )}
        </Alert>
      )}

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Monthly rent" value={kes(record.monthly_rent)} />
        <StatCard
          label="Outstanding balance"
          value={kes(record.balance)}
          tone={Number(record.balance) > 0 ? 'danger' : 'success'}
        />
        <StatCard label="Deposit held" value={kes(record.deposit_amount)} />
        <StatCard
          label="Days to expiry"
          value={
            record.is_open_ended
              ? 'Open-ended'
              : record.days_to_expiry != null
                ? `${record.days_to_expiry}`
                : '—'
          }
          tone={
            record.days_to_expiry != null && record.days_to_expiry <= 60 ? 'warn' : 'default'
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Invoices</CardTitle>
            </CardHeader>
            {invoices.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {invoices.data.map((invoice) => (
                  <li key={invoice.id} className="px-5 py-3">
                    <Link
                      to={`/invoices/${invoice.id}`}
                      className="flex flex-wrap items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">
                          {invoice.reference_code}
                        </p>
                        <p className="text-xs text-slate-500">
                          {shortDate(invoice.period_start)} – {shortDate(invoice.period_end)} · due{' '}
                          {shortDate(invoice.due_date)}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium">{kes(invoice.total)}</span>
                        <Badge tone={INVOICE_STATUS_TONE[invoice.status] ?? 'neutral'}>
                          {humanize(invoice.status)}
                        </Badge>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Receipt className="h-6 w-6" />}
                title="No invoices yet"
                description={`Invoices are raised automatically on day ${record.billing_day} of each month.`}
              />
            )}
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Payments</CardTitle>
            </CardHeader>
            {payments.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {payments.data.map((payment) => (
                  <li key={payment.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-900">{kes(payment.amount)}</p>
                      <p className="text-xs text-slate-500">
                        {humanize(payment.method)}
                        {payment.mpesa_receipt && ` · ${payment.mpesa_receipt}`} ·{' '}
                        {shortDate(payment.payment_date)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={PAYMENT_STATUS_TONE[payment.status] ?? 'neutral'}>
                        {humanize(payment.status)}
                      </Badge>
                      {payment.receipt_url && (
                        <a
                          href={payment.receipt_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label="Download receipt"
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-brand-600"
                        >
                          <Download className="h-4 w-4" />
                        </a>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<CreditCard className="h-6 w-6" />}
                title="No payments recorded"
                description="Payments appear here as soon as they are confirmed."
              />
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Terms</CardTitle>
              <Badge tone={TENANCY_STATUS_TONE[record.status] ?? 'neutral'}>
                {humanize(record.status)}
              </Badge>
            </CardHeader>
            <CardBody className="space-y-3 text-sm">
              <Detail label="Reference" value={record.reference_code} />
              <Detail label="Start date" value={shortDate(record.start_date)} />
              <Detail
                label="End date"
                value={record.is_open_ended ? 'Open-ended' : shortDate(record.end_date)}
              />
              <Detail label="Rent due" value={`Day ${record.billing_day} of each month`} />
              <Detail label="Notice period" value={`${record.notice_period_days} days`} />
              <Detail label="Payment method" value={humanize(record.payment_method)} />
              {record.move_out_date && (
                <Detail label="Move-out date" value={shortDate(record.move_out_date)} />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Lease agreement</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {record.lease_url ? (
                <>
                  <a
                    href={record.lease_url}
                    target="_blank"
                    rel="noreferrer"
                    className={`${linkButtonClass('outline')} w-full justify-center`}
                  >
                    <Download className="h-4 w-4" />
                    Download lease
                  </a>
                  <a
                    href={`${API_BASE_URL}${tenanciesApi.leasePreviewUrl(tenancyId!)}`}
                    target="_blank"
                    rel="noreferrer"
                    className={`${linkButtonClass('ghost')} w-full justify-center`}
                  >
                    <Eye className="h-4 w-4" />
                    Preview in browser
                  </a>
                </>
              ) : (
                <p className="text-sm text-slate-500">
                  No lease has been generated for this tenancy yet.
                </p>
              )}
              {canManage && (
                <Button
                  variant="ghost"
                  className="w-full justify-center"
                  icon={<RefreshCw className="h-4 w-4" />}
                  loading={regenerateLease.isPending}
                  onClick={() => regenerateLease.mutate()}
                >
                  {record.lease_url ? 'Regenerate lease' : 'Generate lease'}
                </Button>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Tenant</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 text-sm">
              <Link
                to={`/tenants/${record.tenant_id}`}
                className="font-medium text-brand-700 hover:underline"
              >
                {record.tenant_name}
              </Link>
              <p className="text-slate-600">{record.tenant_phone}</p>
              <Link
                to={`/units/${record.unit_id}`}
                className="block pt-1 text-brand-600 hover:underline"
              >
                View unit {record.unit_number}
              </Link>
            </CardBody>
          </Card>

          <CoTenantsCard tenancyId={tenancyId!} primaryTenantId={record.tenant_id} canManage={canManage} />
        </div>
      </div>

      <VacateDialog
        open={vacateOpen}
        onClose={() => setVacateOpen(false)}
        tenancyId={tenancyId!}
        unitNumber={record.unit_number ?? ''}
        onDone={() => navigate('/tenancies')}
      />
    </div>
  )
}

function VacateDialog({
  open,
  onClose,
  tenancyId,
  unitNumber,
  onDone,
}: {
  open: boolean
  onClose: () => void
  tenancyId: string
  unitNumber: string
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const [moveOutDate, setMoveOutDate] = useState(today())
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      tenanciesApi.vacate(tenancyId, { move_out_date: moveOutDate, notes: notes || null }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tenancies'] })
      await queryClient.invalidateQueries({ queryKey: ['units'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      onClose()
      onDone()
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="End this tenancy"
      description={`Unit ${unitNumber} becomes vacant and available to re-let.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={mutation.isPending}
            onClick={() => {
              setError(null)
              mutation.mutate()
            }}
          >
            End tenancy
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Move-out date" required>
          <Input
            type="date"
            value={moveOutDate}
            onChange={(event) => setMoveOutDate(event.target.value)}
          />
        </Field>
        <Field label="Notes" hint="Saved to the audit log.">
          <Textarea
            placeholder="Relocated for work. Deposit refund pending inspection."
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
        <Alert tone="info">
          The tenant is notified. Any outstanding balance stays on record and remains collectable.
        </Alert>
        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{value}</dd>
    </div>
  )
}

/** Co-tenants beyond the primary tenant (Sprint 25, US-107) — couples,
 * roommates, or business partners who share one tenancy. */
function CoTenantsCard({
  tenancyId,
  primaryTenantId,
  canManage,
}: {
  tenancyId: string
  primaryTenantId: string
  canManage?: boolean
}) {
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [selectedTenantId, setSelectedTenantId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const coTenants = useQuery({
    queryKey: queryKeys.coTenants(tenancyId),
    queryFn: () => coTenantsApi.list(tenancyId),
  })

  const allTenants = useQuery({
    queryKey: queryKeys.tenants({}),
    queryFn: () => tenantsApi.list(),
    enabled: addOpen,
  })

  const add = useMutation({
    mutationFn: () => coTenantsApi.add(tenancyId, selectedTenantId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.coTenants(tenancyId) })
      setAddOpen(false)
      setSelectedTenantId('')
    },
    onError: (addError) => setError(errorMessage(addError)),
  })

  const remove = useMutation({
    mutationFn: (tenantId: string) => coTenantsApi.remove(tenancyId, tenantId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.coTenants(tenancyId) })
    },
  })

  const promote = useMutation({
    mutationFn: (tenantId: string) => coTenantsApi.promote(tenancyId, tenantId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.coTenants(tenancyId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.tenancy(tenancyId) })
    },
    onError: (promoteError) => setError(errorMessage(promoteError)),
  })

  const available = (allTenants.data ?? []).filter(
    (tenant) =>
      tenant.id !== primaryTenantId && !coTenants.data?.some((row) => row.tenant_id === tenant.id),
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Co-tenants</CardTitle>
        {canManage && (
          <Button
            variant="outline"
            size="sm"
            icon={<UserPlus className="h-3.5 w-3.5" />}
            onClick={() => setAddOpen(true)}
          >
            Add
          </Button>
        )}
      </CardHeader>
      <CardBody className="space-y-2">
        {error && !addOpen && <Alert tone="danger">{error}</Alert>}
        {coTenants.data?.length ? (
          coTenants.data.map((row) => (
            <div key={row.id} className="flex items-center justify-between text-sm">
              <div>
                <Link
                  to={`/tenants/${row.tenant_id}`}
                  className="font-medium text-brand-700 hover:underline"
                >
                  {row.tenant_name}
                </Link>
                <p className="text-xs text-slate-500">{row.tenant_phone}</p>
              </div>
              {canManage && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={promote.isPending}
                    onClick={() => promote.mutate(row.tenant_id)}
                    title="Make this co-tenant the primary tenant — for when the current primary is moving out but this person is staying"
                  >
                    Make primary
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<X className="h-3.5 w-3.5" />}
                    loading={remove.isPending}
                    onClick={() => remove.mutate(row.tenant_id)}
                  />
                </div>
              )}
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500">
            No co-tenants. Add one for a shared unit — both will see this tenancy in their own
            portal login and both are asked to sign the lease.
          </p>
        )}
      </CardBody>

      <Dialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add a co-tenant"
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!selectedTenantId}
              loading={add.isPending}
              onClick={() => {
                setError(null)
                add.mutate()
              }}
            >
              Add co-tenant
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Tenant">
            <Select value={selectedTenantId} onChange={(event) => setSelectedTenantId(event.target.value)}>
              <option value="">Choose an existing tenant record</option>
              {available.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.full_name} — {tenant.phone_number}
                </option>
              ))}
            </Select>
          </Field>
          <p className="text-xs text-slate-500">
            The tenant must already have a profile — create one from Tenants first if they don&apos;t.
          </p>
          {error && <Alert tone="danger">{error}</Alert>}
        </div>
      </Dialog>
    </Card>
  )
}
