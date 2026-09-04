import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, ShieldAlert, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { inspectionsApi } from '@/api'
import type { ComplianceRow } from '@/api/types'
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

function GapTable({ rows, showLastSeen }: { rows: ComplianceRow[]; showLastSeen?: boolean }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Property</Th>
          <Th>Unit</Th>
          <Th>Tenant</Th>
          <Th>{showLastSeen ? 'Last inspected' : 'Tenancy started'}</Th>
          <Th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.tenancy_id}>
            <Td>{row.property_name}</Td>
            <Td className="font-medium">{row.unit_number}</Td>
            <Td>{row.tenant_name}</Td>
            <Td className="text-sm text-slate-500">
              {showLastSeen
                ? row.last_inspected_at
                  ? shortDate(row.last_inspected_at)
                  : 'Never'
                : shortDate(row.start_date)}
            </Td>
            <Td>
              <Link
                to={`/inspections/new?unit_id=${row.unit_id}&tenancy_id=${row.tenancy_id}&type=${showLastSeen ? 'routine' : 'move_in'}`}
                className="text-sm text-brand-700 hover:underline"
              >
                Inspect now
              </Link>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}

/**
 * The compliance gaps, named (US-052).
 *
 * A count on its own is not actionable; what a manager needs is the list of
 * units to send someone to, with a link that opens the right inspection type
 * already pointed at the right unit.
 */
export function InspectionComplianceCard({ className }: { className?: string }) {
  const compliance = useQuery({
    queryKey: queryKeys.inspectionCompliance,
    queryFn: inspectionsApi.compliance,
  })

  if (!compliance.data) return null
  const { missing_move_in: missing, overdue_routine: overdue } = compliance.data

  if (missing.length === 0 && overdue.length === 0) {
    return (
      <Card className={className}>
        <CardBody className="flex items-center gap-2 text-sm text-money-700">
          <CheckCircle2 className="h-4 w-4" />
          Every active tenancy has a move-in inspection and has been seen in the last year.
        </CardBody>
      </Card>
    )
  }

  return (
    <div className={className}>
      {missing.length > 0 && (
        <Card className="mb-3">
          <CardHeader>
            <CardTitle className="text-base text-danger-700">
              <ShieldAlert className="mr-1.5 inline h-4 w-4" />
              No move-in inspection ({missing.length})
            </CardTitle>
            <p className="text-sm text-slate-500">
              Without a baseline there is nothing to compare a move-out against, so any deposit
              deduction on these units is unarguable in the tenant's favour.
            </p>
          </CardHeader>
          <CardBody>
            <GapTable rows={missing} />
          </CardBody>
        </Card>
      )}

      {overdue.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-amber-700">
              <TriangleAlert className="mr-1.5 inline h-4 w-4" />
              Not inspected in over a year ({overdue.length})
            </CardTitle>
          </CardHeader>
          <CardBody>
            <GapTable rows={overdue} showLastSeen />
          </CardBody>
        </Card>
      )}
    </div>
  )
}
