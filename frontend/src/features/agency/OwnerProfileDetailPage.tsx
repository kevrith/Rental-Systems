import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Banknote,
  Building2,
  CheckCircle2,
  Eye,
  Mail,
  Pencil,
  Percent,
  Phone,
  Send,
  ShieldCheck,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { agencyApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  PageLoader,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { DISBURSEMENT_STATUS_TONE } from '@/features/agency/disbursement-status'
import { ManagementAgreementPanel } from '@/features/agency/ManagementAgreementPanel'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-right text-sm font-medium text-slate-900">{value || '—'}</span>
    </div>
  )
}

export function OwnerProfileDetailPage() {
  const { ownerId } = useParams<{ ownerId: string }>()
  const queryClient = useQueryClient()
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteError, setInviteError] = useState<string | null>(null)

  const owner = useQuery({
    queryKey: queryKeys.ownerProfile(ownerId!),
    queryFn: () => agencyApi.ownerProfile(ownerId!),
  })
  const summaries = useQuery({
    queryKey: queryKeys.ownerSummaries,
    queryFn: agencyApi.ownerSummaries,
  })
  const disbursements = useQuery({
    queryKey: queryKeys.disbursements({ owner: ownerId }),
    queryFn: () => agencyApi.disbursements({ owner_profile_id: ownerId! }),
  })

  const invite = useMutation({
    mutationFn: () => agencyApi.invitePortal(ownerId!),
    onSuccess: async () => {
      setInviteOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['agency'] })
    },
    onError: (error) => setInviteError(errorMessage(error)),
  })

  if (owner.isPending) return <PageLoader />

  if (owner.isError) {
    return (
      <div>
        <PageHeader title="Owner client" backTo="/agency/owners" backLabel="Owner clients" />
        <Alert tone="danger">{errorMessage(owner.error)}</Alert>
      </div>
    )
  }

  const record = owner.data
  const summary = summaries.data?.find((row) => row.owner_profile_id === record.id)
  const payouts = disbursements.data ?? []
  const hasPortal = Boolean(record.portal_user_id)

  return (
    <div>
      <PageHeader
        title={record.full_name}
        description={`${record.reference_code} · owner client`}
        backTo="/agency/owners"
        backLabel="Owner clients"
        actions={
          <>
            {!hasPortal && (
              <Button
                variant="secondary"
                icon={<Send className="h-4 w-4" />}
                onClick={() => {
                  setInviteError(null)
                  setInviteOpen(true)
                }}
              >
                Invite to portal
              </Button>
            )}
            <Link to={`/agency/owners/${record.id}/edit`} className={linkButtonClass('primary')}>
              <Pencil className="mr-1.5 h-4 w-4" />
              Edit
            </Link>
          </>
        }
      />

      {summary && (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Units managed"
            value={String(summary.unit_count)}
            icon={<Building2 className="h-4 w-4" />}
            hint={`${summary.property_count} properties · ${summary.occupancy_rate}% occupied`}
          />
          <StatCard
            label="Collected this month"
            value={kes(summary.collected_this_month)}
            tone="success"
            icon={<Banknote className="h-4 w-4" />}
            hint={
              summary.billed_this_month > 0
                ? `${summary.collection_rate}% of ${kes(summary.billed_this_month)} billed`
                : 'Nothing billed yet this month'
            }
          />
          <StatCard
            label="Arrears"
            value={kes(summary.arrears)}
            tone={summary.arrears > 0 ? 'danger' : 'default'}
            icon={<Percent className="h-4 w-4" />}
          />
          <StatCard
            label="Owner portal"
            value={hasPortal ? 'Active' : 'Not invited'}
            icon={<Eye className="h-4 w-4" />}
            hint={
              record.portal_invited_at
                ? `Invited ${shortDate(record.portal_invited_at)}`
                : 'Read-only access to their own properties'
            }
          />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Management agreement</CardTitle>
            <CardDescription>The terms you manage this owner’s portfolio on.</CardDescription>
          </CardHeader>
          <CardBody className="divide-y divide-slate-100">
            <DetailRow
              label="Management fee"
              value={`${record.management_fee_percent}% of rent collected`}
            />
            <DetailRow label="Disbursement day" value={`Day ${record.disbursement_day} of each month`} />
            <DetailRow
              label="Repairs you approve alone"
              value={`Up to ${kes(record.maintenance_auto_approve_limit)}`}
            />
            <DetailRow
              label="Owner must approve above"
              value={kes(record.maintenance_notify_limit)}
            />
            {record.notes && <DetailRow label="Notes" value={record.notes} />}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Contact and payout</CardTitle>
            <CardDescription>Where statements go, and where their money is sent.</CardDescription>
          </CardHeader>
          <CardBody className="divide-y divide-slate-100">
            <DetailRow label="Phone" value={record.phone_number} />
            <DetailRow label="Email" value={record.email} />
            <DetailRow label="National ID / reg. no." value={record.national_id} />
            <DetailRow label="KRA PIN" value={record.kra_pin} />
            <DetailRow label="M-Pesa" value={record.mpesa_phone} />
            <DetailRow
              label="Bank"
              value={
                record.bank_name
                  ? `${record.bank_name} · ${record.bank_account_number ?? 'no account no.'}`
                  : null
              }
            />
            <DetailRow label="Account name" value={record.bank_account_name} />
          </CardBody>
        </Card>
      </div>

      <div className="mt-4">
        <ManagementAgreementPanel ownerProfileId={ownerId!} />
      </div>

      <Card className="mt-4">
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Disbursement history</CardTitle>
          <Link to="/agency/disbursements" className={linkButtonClass('ghost', 'sm')}>
            Manage disbursements
          </Link>
        </CardHeader>
        <CardBody>
          {disbursements.isPending ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : payouts.length === 0 ? (
            <p className="text-sm text-slate-500">
              No disbursements yet. Once rent is collected against this owner’s properties you can
              calculate and pay out their net rent.
            </p>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Period</Th>
                  <Th>Gross</Th>
                  <Th>Fee</Th>
                  <Th>Repairs</Th>
                  <Th>Net</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {payouts.map((row) => (
                  <tr key={row.id}>
                    <Td className="font-medium">{row.reference_code}</Td>
                    <Td className="text-xs text-slate-500">
                      {shortDate(row.period_start)} – {shortDate(row.period_end)}
                    </Td>
                    <Td>{kes(row.gross_rent)}</Td>
                    <Td className="text-slate-500">−{kes(row.management_fee)}</Td>
                    <Td className="text-slate-500">−{kes(row.maintenance_costs)}</Td>
                    <Td className="font-semibold text-money-700">{kes(row.net_amount)}</Td>
                    <Td>
                      <Badge tone={DISBURSEMENT_STATUS_TONE[row.status]}>{humanize(row.status)}</Badge>
                      {row.paid_at && (
                        <p className="mt-0.5 text-xs text-slate-400">{dateTime(row.paid_at)}</p>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Dialog
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        title="Invite to the owner portal"
        description={`${record.full_name} will get a link to set up read-only access.`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setInviteOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={invite.isPending}
              icon={<Send className="h-4 w-4" />}
              onClick={() => invite.mutate()}
            >
              Send invitation
            </Button>
          </>
        }
      >
        {inviteError && (
          <Alert tone="danger" className="mb-3">
            {inviteError}
          </Alert>
        )}
        <div className="space-y-2 text-sm text-slate-600">
          <p className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-money-700" />
            They will see only their own properties — never another owner’s data.
          </p>
          <p className="flex items-start gap-2">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-money-700" />
            Strictly read-only. They cannot edit anything or contact tenants directly.
          </p>
          <p className="flex items-start gap-2">
            <Phone className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
            Sent to {record.phone_number}
            {record.email ? (
              <>
                {' '}
                and <Mail className="mx-1 inline h-3.5 w-3.5" />
                {record.email}
              </>
            ) : null}
          </p>
        </div>
      </Dialog>
    </div>
  )
}
