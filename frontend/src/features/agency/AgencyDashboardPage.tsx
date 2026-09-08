import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  DoorOpen,
  Eye,
  EyeOff,
  Percent,
  Send,
  Users,
  Wallet,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { agencyApi } from '@/api'
import type { OwnerSummary } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  PageLoader,
  linkButtonClass,
} from '@/components/ui'
import { DISBURSEMENT_STATUS_TONE } from '@/features/agency/disbursement-status'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** Collection rate colours: below 70% is a problem worth surfacing, not decoration. */
function collectionTone(rate: number, billed: number): 'success' | 'warn' | 'danger' | 'default' {
  if (billed <= 0) return 'default'
  if (rate >= 95) return 'success'
  if (rate >= 70) return 'warn'
  return 'danger'
}

function OwnerCard({ owner }: { owner: OwnerSummary }) {
  const tone = collectionTone(owner.collection_rate, owner.billed_this_month)
  const last = owner.last_disbursement

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <CardTitle className="truncate">{owner.full_name}</CardTitle>
          <p className="mt-0.5 text-xs text-slate-400">
            {owner.reference_code} · {owner.management_fee_percent}% fee · pays on day{' '}
            {owner.disbursement_day}
          </p>
        </div>
        {owner.portal_invited ? (
          <Badge tone="success">
            <Eye className="mr-1 h-3 w-3" />
            Portal active
          </Badge>
        ) : (
          <Badge tone="neutral">
            <EyeOff className="mr-1 h-3 w-3" />
            No portal
          </Badge>
        )}
      </CardHeader>

      <CardBody className="space-y-3">
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-xs text-slate-500">Properties</p>
            <p className="font-semibold text-slate-900">{owner.property_count}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Units</p>
            <p className="font-semibold text-slate-900">{owner.unit_count}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Occupancy</p>
            <p className="font-semibold text-slate-900">
              {owner.occupancy_rate}%
              <span className="ml-1 text-xs font-normal text-slate-400">
                {owner.occupied_units}/{owner.unit_count}
              </span>
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-3 text-sm">
          <div>
            <p className="text-xs text-slate-500">Collected this month</p>
            <p className="font-semibold text-money-700">{kes(owner.collected_this_month)}</p>
            {owner.billed_this_month > 0 && (
              <p className={`text-xs ${tone === 'danger' ? 'text-danger-700' : 'text-slate-400'}`}>
                {owner.collection_rate}% of {kes(owner.billed_this_month)} billed
              </p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-500">Arrears</p>
            <p
              className={`font-semibold ${owner.arrears > 0 ? 'text-danger-700' : 'text-slate-900'}`}
            >
              {kes(owner.arrears)}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <div className="text-xs text-slate-500">
            {last ? (
              <span className="inline-flex items-center gap-1.5">
                Last payout
                <Badge tone={DISBURSEMENT_STATUS_TONE[last.status] ?? 'neutral'}>
                  {humanize(last.status)}
                </Badge>
                {kes(last.net_amount)} · {shortDate(last.period_end)}
              </span>
            ) : (
              'No disbursement yet'
            )}
          </div>
          <Link
            to={`/agency/owners/${owner.owner_profile_id}`}
            className={linkButtonClass('ghost', 'sm')}
          >
            Open
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Link>
        </div>
      </CardBody>
    </Card>
  )
}

export function AgencyDashboardPage() {
  const dashboard = useQuery({ queryKey: queryKeys.agencyDashboard, queryFn: agencyApi.dashboard })
  const owners = useQuery({ queryKey: queryKeys.ownerSummaries, queryFn: agencyApi.ownerSummaries })

  if (dashboard.isPending) return <PageLoader />

  if (dashboard.isError) {
    return (
      <div>
        <PageHeader title="Agency" />
        <Alert tone="danger">{errorMessage(dashboard.error)}</Alert>
      </div>
    )
  }

  const stats = dashboard.data
  const ownerRows = owners.data ?? []
  const totalArrears = ownerRows.reduce((sum, owner) => sum + owner.arrears, 0)

  return (
    <div>
      <PageHeader
        title="Agency portfolio"
        description="Every owner client you manage, and where their money is right now."
        actions={
          <>
            <Link to="/agency/disbursements" className={linkButtonClass('secondary')}>
              <Send className="mr-1.5 h-4 w-4" />
              Disbursements
            </Link>
            <Link to="/agency/owners" className={linkButtonClass('primary')}>
              <Users className="mr-1.5 h-4 w-4" />
              Owner clients
            </Link>
          </>
        }
      />

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Owner clients"
          value={String(stats.owner_count)}
          icon={<Users className="h-4 w-4" />}
          hint={`${stats.total_properties} properties managed`}
        />
        <StatCard
          label="Units managed"
          value={String(stats.total_units)}
          icon={<Building2 className="h-4 w-4" />}
          hint={`${stats.occupied_units} occupied · ${stats.occupancy_rate}%`}
        />
        <StatCard
          label="Collected this month"
          value={kes(stats.collected_this_month)}
          tone="success"
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Fees earned this month"
          value={kes(stats.management_fees_this_month)}
          icon={<Percent className="h-4 w-4" />}
          hint={
            stats.pending_disbursements > 0
              ? `${stats.pending_disbursements} disbursement(s) pending`
              : 'No pending disbursements'
          }
        />
      </div>

      {totalArrears > 0 && (
        <Alert tone="warn" className="mb-6">
          <AlertTriangle className="mr-2 inline h-4 w-4" />
          {kes(totalArrears)} outstanding across your owner clients. Owners with a portal can
          see this themselves.
        </Alert>
      )}

      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Owner clients</CardTitle>
          {ownerRows.length > 0 && (
            <span className="text-xs text-slate-400">{ownerRows.length} active</span>
          )}
        </CardHeader>
        <CardBody>
          {owners.isPending ? (
            <p className="text-sm text-slate-500">Loading owner summaries…</p>
          ) : owners.isError ? (
            <Alert tone="danger">{errorMessage(owners.error)}</Alert>
          ) : ownerRows.length === 0 ? (
            <EmptyState
              icon={<DoorOpen className="h-6 w-6" />}
              title="No owner clients yet"
              description="Add the landlords whose properties you manage. Each one gets their own statements, fee settings and optional read-only portal."
              action={
                <Link to="/agency/owners/new" className={linkButtonClass('primary')}>
                  Add an owner client
                </Link>
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {ownerRows.map((owner) => (
                <OwnerCard key={owner.owner_profile_id} owner={owner} />
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
