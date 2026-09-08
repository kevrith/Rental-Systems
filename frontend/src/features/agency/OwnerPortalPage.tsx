import { useQuery } from '@tanstack/react-query'
import { Banknote, Building2, DoorOpen, Lock, Wallet } from 'lucide-react'

import { agencyApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  PageLoader,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { DISBURSEMENT_STATUS_TONE } from '@/features/agency/disbursement-status'
import { dateTime, errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/**
 * Mode 3 — what a property owner sees of their own portfolio inside an agency
 * account. Read-only by construction: the API only ever returns this owner's
 * properties, and nothing here offers an action.
 */
export function OwnerPortalPage() {
  const summary = useQuery({
    queryKey: queryKeys.ownerPortalSummary,
    queryFn: agencyApi.ownerPortal,
  })

  if (summary.isPending) return <PageLoader />

  if (summary.isError) {
    return (
      <div>
        <PageHeader title="My portfolio" />
        <Alert tone="danger">{errorMessage(summary.error)}</Alert>
      </div>
    )
  }

  const data = summary.data
  const owner = data.owner_profile
  const payouts = data.recent_disbursements

  return (
    <div>
      <PageHeader
        title="My portfolio"
        description={`${owner.full_name} · managed on ${owner.management_fee_percent}% · paid out on day ${owner.disbursement_day}`}
      />

      <Alert tone="info" className="mb-6">
        <Lock className="mr-2 inline h-4 w-4" />
        This is your read-only view. Your agency handles all day-to-day management — reach out to
        them for any changes.
      </Alert>

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Properties"
          value={String(data.properties.length)}
          icon={<Building2 className="h-4 w-4" />}
        />
        <StatCard
          label="Units"
          value={String(data.total_units)}
          icon={<DoorOpen className="h-4 w-4" />}
          hint={`${data.occupied_units} occupied`}
        />
        <StatCard
          label="Occupancy"
          value={`${data.occupancy_rate}%`}
          tone={data.occupancy_rate >= 90 ? 'success' : data.occupancy_rate >= 70 ? 'warn' : 'danger'}
        />
        <StatCard
          label="Collected this month"
          value={kes(data.collected_this_month)}
          tone="success"
          icon={<Wallet className="h-4 w-4" />}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>My properties</CardTitle>
          </CardHeader>
          <CardBody>
            {data.properties.length === 0 ? (
              <EmptyState
                icon={<Building2 className="h-6 w-6" />}
                title="No properties linked yet"
                description="Your agency has not yet attributed any properties to your profile."
              />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Property</Th>
                    <Th>Location</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.properties.map((property) => (
                    <tr key={property.id}>
                      <Td className="font-medium">{property.name}</Td>
                      <Td className="text-slate-500">
                        {property.address}
                        {property.county ? `, ${property.county}` : ''}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>My statements</CardTitle>
            <CardDescription>
              Every deduction your agency has made, itemised.
            </CardDescription>
          </CardHeader>
          <CardBody>
            {payouts.length === 0 ? (
              <EmptyState
                icon={<Banknote className="h-6 w-6" />}
                title="No disbursements yet"
                description="Once your agency pays out rent, each statement appears here with a full breakdown."
              />
            ) : (
              <ul className="divide-y divide-slate-100">
                {payouts.map((payout) => (
                  <li key={payout.id} className="py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-slate-900">
                          {shortDate(payout.period_start)} – {shortDate(payout.period_end)}
                        </p>
                        <p className="text-xs text-slate-400">{payout.reference_code}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-money-700">
                          {kes(payout.net_amount)}
                        </p>
                        <Badge tone={DISBURSEMENT_STATUS_TONE[payout.status]}>
                          {humanize(payout.status)}
                        </Badge>
                      </div>
                    </div>
                    <dl className="mt-2 grid grid-cols-3 gap-2 rounded-md bg-slate-50 p-2 text-xs">
                      <div>
                        <dt className="text-slate-500">Gross rent</dt>
                        <dd className="font-medium text-slate-900">{kes(payout.gross_rent)}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Management fee</dt>
                        <dd className="font-medium text-slate-700">−{kes(payout.management_fee)}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Repairs</dt>
                        <dd className="font-medium text-slate-700">
                          −{kes(payout.maintenance_costs)}
                        </dd>
                      </div>
                    </dl>
                    {payout.paid_at && (
                      <p className="mt-1.5 text-xs text-slate-400">
                        Paid {dateTime(payout.paid_at)}
                        {payout.payment_reference ? ` · ref ${payout.payment_reference}` : ''}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
