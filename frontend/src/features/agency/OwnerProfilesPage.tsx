import { useQuery } from '@tanstack/react-query'
import { Eye, EyeOff, Plus, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { agencyApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  PageLoader,
  Table,
  Td,
  Th,
  linkButtonClass,
} from '@/components/ui'
import { errorMessage, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

export function OwnerProfilesPage() {
  const owners = useQuery({ queryKey: queryKeys.ownerProfiles, queryFn: agencyApi.ownerProfiles })

  if (owners.isPending) return <PageLoader />

  if (owners.isError) {
    return (
      <div>
        <PageHeader title="Owner clients" backTo="/agency" backLabel="Agency" />
        <Alert tone="danger">{errorMessage(owners.error)}</Alert>
      </div>
    )
  }

  const rows = owners.data

  return (
    <div>
      <PageHeader
        title="Owner clients"
        description="The landlords whose properties you manage, and the terms you manage them on."
        backTo="/agency"
        backLabel="Agency"
        actions={
          <Link to="/agency/owners/new" className={linkButtonClass('primary')}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add owner client
          </Link>
        }
      />

      {rows.length === 0 ? (
        <EmptyState
          icon={<Users className="h-6 w-6" />}
          title="No owner clients yet"
          description="Add a landlord to start attributing properties, rent and management fees to them."
          action={
            <Link to="/agency/owners/new" className={linkButtonClass('primary')}>
              Add owner client
            </Link>
          }
        />
      ) : (
        <Card>
          <Table>
            <thead>
              <tr>
                <Th>Owner</Th>
                <Th>Contact</Th>
                <Th>Fee</Th>
                <Th>Pays on</Th>
                <Th>Approval limits</Th>
                <Th>Portal</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((owner) => (
                <tr key={owner.id}>
                  <Td>
                    <Link
                      to={`/agency/owners/${owner.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {owner.full_name}
                    </Link>
                    <p className="text-xs text-slate-400">{owner.reference_code}</p>
                  </Td>
                  <Td>
                    <p>{owner.phone_number}</p>
                    {owner.email && <p className="text-xs text-slate-400">{owner.email}</p>}
                  </Td>
                  <Td>{owner.management_fee_percent}%</Td>
                  <Td>Day {owner.disbursement_day}</Td>
                  <Td className="text-xs text-slate-500">
                    Auto {kes(owner.maintenance_auto_approve_limit)}
                    <br />
                    Notify {kes(owner.maintenance_notify_limit)}
                  </Td>
                  <Td>
                    {owner.portal_user_id ? (
                      <Badge tone="success">
                        <Eye className="mr-1 h-3 w-3" />
                        {owner.portal_invited_at ? shortDate(owner.portal_invited_at) : 'Active'}
                      </Badge>
                    ) : (
                      <Badge tone="neutral">
                        <EyeOff className="mr-1 h-3 w-3" />
                        Not invited
                      </Badge>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </div>
  )
}
