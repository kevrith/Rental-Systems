import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Download,
  FileText,
  FolderOpen,
  Mail,
  Pencil,
  Phone,
  Send,
  ShieldAlert,
  ShieldCheck,
  UserPlus,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { paymentsApi, portalApi, privacyApi, tenanciesApi, tenantsApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
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
  PAYMENT_STATUS_TONE,
  PageLoader,
  TENANCY_STATUS_TONE,
  linkButtonClass,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function TenantDetailPage() {
  const { tenantId } = useParams<{ tenantId: string }>()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const permissions = useAuthStore((state) => state.user?.permissions)
  const canManage = permissions?.includes('tenant:manage')

  const tenant = useQuery({
    queryKey: queryKeys.tenant(tenantId!),
    queryFn: () => tenantsApi.get(tenantId!),
    enabled: Boolean(tenantId),
  })

  const tenancies = useQuery({
    queryKey: queryKeys.tenancies({ tenant_id: tenantId }),
    queryFn: () => tenanciesApi.list({ tenant_id: tenantId }),
    enabled: Boolean(tenantId),
  })

  const documents = useQuery({
    queryKey: queryKeys.tenantDocuments(tenantId!),
    queryFn: () => tenantsApi.documents(tenantId!),
    enabled: Boolean(tenantId),
  })

  const activeTenancy = tenancies.data?.find((tenancy) =>
    ['active', 'expiring_soon', 'notice_given'].includes(tenancy.status),
  )

  const payments = useQuery({
    queryKey: queryKeys.payments({ tenancy_id: activeTenancy?.id }),
    queryFn: () => paymentsApi.list({ tenancy_id: activeTenancy!.id, limit: 10 }),
    enabled: Boolean(activeTenancy),
  })

  const invitePortal = useMutation({
    mutationFn: () => portalApi.invite(tenantId!),
    onSuccess: (result) => {
      setNotice({ tone: 'success', text: result.message })
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenant(tenantId!) })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  if (tenant.isPending) return <PageLoader />
  if (tenant.isError) {
    return (
      <Alert tone="danger" title="Could not load this tenant">
        {errorMessage(tenant.error)}
      </Alert>
    )
  }

  const record = tenant.data

  return (
    <div>
      <PageHeader
        title={record.full_name}
        description={`${record.reference_code} · ${record.phone_number}`}
        backTo="/tenants"
        backLabel="All tenants"
        actions={
          <>
            <Link to={`/tenants/${tenantId}/documents`} className={linkButtonClass('outline')}>
              <FolderOpen className="h-4 w-4" />
              Documents
            </Link>
            {canManage && !record.portal_user_id && (
              <Button
                variant="outline"
                icon={<Send className="h-4 w-4" />}
                loading={invitePortal.isPending}
                onClick={() => invitePortal.mutate()}
              >
                Invite to portal
              </Button>
            )}
            {canManage && (
              <Link to={`/tenants/${tenantId}/edit`} className={linkButtonClass('outline')}>
                <Pencil className="h-4 w-4" />
                Edit
              </Link>
            )}
            {!activeTenancy && canManage && (
              <Link to={`/tenancies/new?tenant_id=${tenantId}`} className={linkButtonClass()}>
                <UserPlus className="h-4 w-4" />
                Create tenancy
              </Link>
            )}
          </>
        }
      />

      {notice && (
        <Alert tone={notice.tone} className="mb-5">
          {notice.text}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Tenancies</CardTitle>
            </CardHeader>
            {tenancies.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {tenancies.data.map((tenancy) => (
                  <li key={tenancy.id} className="px-5 py-3">
                    <Link
                      to={`/tenancies/${tenancy.id}`}
                      className="flex flex-wrap items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">
                          {tenancy.property_name} · Unit {tenancy.unit_number}
                        </p>
                        <p className="text-xs text-slate-500">
                          {shortDate(tenancy.start_date)} –{' '}
                          {tenancy.is_open_ended ? 'open-ended' : shortDate(tenancy.end_date)} ·{' '}
                          {kes(tenancy.monthly_rent)}/mo
                        </p>
                      </div>
                      <Badge tone={TENANCY_STATUS_TONE[tenancy.status] ?? 'neutral'}>
                        {humanize(tenancy.status)}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                title="No tenancy yet"
                description="Link this tenant to a unit to start their tenancy and generate a lease."
                action={
                  canManage ? (
                    <Link to={`/tenancies/new?tenant_id=${tenantId}`} className={linkButtonClass()}>
                      Create tenancy
                    </Link>
                  ) : undefined
                }
              />
            )}
          </Card>

          {activeTenancy && (
            <Card>
              <CardHeader>
                <CardTitle>Recent payments</CardTitle>
                <Link
                  to={`/payments?tenancy_id=${activeTenancy.id}`}
                  className="text-sm text-brand-600 hover:underline"
                >
                  View all
                </Link>
              </CardHeader>
              {payments.data?.length ? (
                <ul className="divide-y divide-slate-100">
                  {payments.data.map((payment) => (
                    <li
                      key={payment.id}
                      className="flex items-center justify-between gap-3 px-5 py-3"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">{kes(payment.amount)}</p>
                        <p className="text-xs text-slate-500">
                          {humanize(payment.method)} · {payment.reference_code} ·{' '}
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
                <EmptyState title="No payments yet" description="Nothing has been recorded." />
              )}
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Document vault</CardTitle>
            </CardHeader>
            {documents.data?.length ? (
              <ul className="divide-y divide-slate-100">
                {documents.data.map((document) => (
                  <li key={document.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                      <div className="min-w-0">
                        <p className="truncate text-sm text-slate-900">{document.filename}</p>
                        <p className="text-xs text-slate-500">
                          {humanize(document.category)} · {shortDate(document.created_at)}
                        </p>
                      </div>
                    </div>
                    <a
                      href={document.url}
                      target="_blank"
                      rel="noreferrer"
                      className={linkButtonClass('ghost', 'sm')}
                    >
                      <Download className="h-3.5 w-3.5" />
                      Open
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<FileText className="h-6 w-6" />}
                title="No documents yet"
                description="Leases, receipts and notices are filed here automatically."
              />
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Contact</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3 text-sm">
              <a
                href={`tel:${record.phone_number}`}
                className="flex items-center gap-2 text-slate-700 hover:text-brand-700"
              >
                <Phone className="h-4 w-4 text-slate-400" />
                {record.phone_number}
              </a>
              {record.email && (
                <a
                  href={`mailto:${record.email}`}
                  className="flex items-center gap-2 text-slate-700 hover:text-brand-700"
                >
                  <Mail className="h-4 w-4 text-slate-400" />
                  {record.email}
                </a>
              )}
              {record.portal_user_id && (
                <div className="flex items-center gap-2 text-money-700">
                  <ShieldCheck className="h-4 w-4" />
                  Portal access active
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3 text-sm">
              <Detail label="Reference" value={record.reference_code} />
              <Detail label="National ID" value={record.national_id ?? '—'} />
              <Detail label="Employer" value={record.employer_name ?? '—'} />
              <Detail label="Occupation" value={record.occupation ?? '—'} />
              <Detail
                label="Monthly income"
                value={record.monthly_income ? kes(record.monthly_income) : '—'}
              />
              <Detail label="Added" value={dateTime(record.created_at)} />
            </CardBody>
          </Card>

          <DataPrivacyCard
            tenantId={tenantId!}
            erasedAt={record.erased_at}
            canManage={permissions?.includes('data_request:manage')}
          />

          {record.emergency_contact_name && (
            <Card>
              <CardHeader>
                <CardTitle>Emergency contact</CardTitle>
              </CardHeader>
              <CardBody className="space-y-3 text-sm">
                <Detail label="Name" value={record.emergency_contact_name} />
                <Detail label="Phone" value={record.emergency_contact_phone ?? '—'} />
                <Detail
                  label="Relationship"
                  value={record.emergency_contact_relationship ?? '—'}
                />
              </CardBody>
            </Card>
          )}

          {record.notes && (
            <Card>
              <CardHeader>
                <CardTitle>Notes</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="whitespace-pre-wrap text-sm text-slate-700">{record.notes}</p>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
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

/** Raise a data export or erasure request on the tenant's behalf (Sprint 25,
 * US-106). A tenant can also do both themselves from their own portal. */
function DataPrivacyCard({
  tenantId,
  erasedAt,
  canManage,
}: {
  tenantId: string
  erasedAt: string | null
  canManage?: boolean
}) {
  const [eraseOpen, setEraseOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const exportData = useMutation({
    mutationFn: () => privacyApi.requestExport(tenantId),
    onSuccess: (result) => {
      if (result.export_url) window.open(result.export_url, '_blank', 'noopener')
      setNotice('Data export generated.')
    },
    onError: (exportError) => setError(errorMessage(exportError)),
  })

  const eraseData = useMutation({
    mutationFn: () => privacyApi.requestErasure(tenantId),
    onSuccess: () => {
      setEraseOpen(false)
      setNotice('Personal data erased. Financial records were retained.')
    },
    onError: (eraseError) => setError(errorMessage(eraseError)),
  })

  if (!canManage) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Data privacy</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        {notice && <Alert tone="success">{notice}</Alert>}
        {error && <Alert tone="danger">{error}</Alert>}

        {erasedAt ? (
          <Alert tone="warn" icon={<AlertTriangle className="h-4 w-4" />}>
            This tenant's personal data was erased on {dateTime(erasedAt)}.
          </Alert>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              icon={<Download className="h-3.5 w-3.5" />}
              loading={exportData.isPending}
              onClick={() => exportData.mutate()}
            >
              Export data
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-danger-600"
              icon={<ShieldAlert className="h-3.5 w-3.5" />}
              onClick={() => setEraseOpen(true)}
            >
              Erase data
            </Button>
          </div>
        )}
      </CardBody>

      <Dialog
        open={eraseOpen}
        onClose={() => setEraseOpen(false)}
        title="Erase this tenant's personal data?"
        description="This cannot be undone."
        footer={
          <>
            <Button variant="ghost" onClick={() => setEraseOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={eraseData.isPending} onClick={() => eraseData.mutate()}>
              Erase data
            </Button>
          </>
        }
      >
        <Alert tone="warn" icon={<AlertTriangle className="h-4 w-4" />}>
          Name, contact details, ID and documents will be permanently redacted. Tenancy, invoice
          and payment records are retained, as Kenyan law requires.
        </Alert>
      </Dialog>
    </Card>
  )
}
