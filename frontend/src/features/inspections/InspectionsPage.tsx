import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, ShieldAlert, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { inspectionsApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Field,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { InspectionComplianceCard } from '@/features/inspections/InspectionComplianceCard'
import { dateTime, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

export function InspectionsPage() {
  const [kind, setKind] = useState('')

  const inspections = useQuery({
    queryKey: queryKeys.inspections({ kind }),
    queryFn: () => inspectionsApi.list(kind ? { inspection_type: kind } : undefined),
  })
  const compliance = useQuery({
    queryKey: queryKeys.inspectionCompliance,
    queryFn: inspectionsApi.compliance,
  })

  if (inspections.isPending) return <PageLoader />

  const rows = inspections.data ?? []

  return (
    <div>
      <PageHeader
        title="Inspections"
        description="Move-in, move-out and routine condition reports."
      />

      {compliance.data && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <StatCard
            label="Move-in coverage"
            value={`${compliance.data.coverage_percent}%`}
            hint={`${compliance.data.total_active_tenancies} active tenancies`}
          />
          <StatCard
            label="Missing a baseline"
            value={String(compliance.data.missing_move_in_inspection)}
            hint="No move-in inspection on record"
            tone={compliance.data.missing_move_in_inspection > 0 ? 'danger' : 'default'}
          />
          <StatCard
            label="Not inspected in a year"
            value={String(compliance.data.overdue_routine_inspection)}
            hint="Due a routine inspection"
            tone={compliance.data.overdue_routine_inspection > 0 ? 'warn' : 'default'}
          />
        </div>
      )}

      <InspectionComplianceCard className="mb-4" />

      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>All inspections</CardTitle>
          <Field label="Type" className="w-48">
            <Select value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="">All types</option>
              <option value="move_in">Move-in</option>
              <option value="move_out">Move-out</option>
              <option value="routine">Routine</option>
            </Select>
          </Field>
        </CardHeader>
        <CardBody>
          {rows.length === 0 ? (
            <EmptyState
              icon={<ClipboardCheck className="h-6 w-6" />}
              title="No inspections yet"
              description="Start one from a unit — the caretaker walks the rooms on their phone."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Type</Th>
                  <Th>Rooms</Th>
                  <Th>Inspector</Th>
                  <Th>Status</Th>
                  <Th>Deduction</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <Td>
                      <Link
                        to={
                          row.status === 'draft'
                            ? `/inspections/${row.id}/capture`
                            : `/inspections/${row.id}`
                        }
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {row.reference_code}
                      </Link>
                      <p className="text-xs text-slate-400">{shortDate(row.created_at)}</p>
                    </Td>
                    <Td>{humanize(row.inspection_type)}</Td>
                    <Td>{row.rooms_data.length}</Td>
                    <Td className="text-sm text-slate-600">{row.inspector_name ?? '—'}</Td>
                    <Td>
                      <Badge tone={row.status === 'submitted' ? 'success' : 'warn'}>
                        {humanize(row.status)}
                      </Badge>
                      {row.submitted_at && (
                        <p className="mt-0.5 text-xs text-slate-400">
                          {dateTime(row.submitted_at)}
                        </p>
                      )}
                    </Td>
                    <Td>
                      {row.deposit_deduction ? (
                        <span className="font-medium text-danger-700">
                          {kes(row.deposit_deduction)}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

/** Compact version for the main dashboard. */
export function InspectionComplianceWidget() {
  const compliance = useQuery({
    queryKey: queryKeys.inspectionCompliance,
    queryFn: inspectionsApi.compliance,
  })

  if (!compliance.data || compliance.data.total_active_tenancies === 0) return null
  const { missing_move_in_inspection: missing, overdue_routine_inspection: overdue } =
    compliance.data

  if (missing === 0 && overdue === 0) return null

  return (
    <Alert tone={missing > 0 ? 'danger' : 'warn'}>
      {missing > 0 ? (
        <ShieldAlert className="mr-1.5 inline h-4 w-4" />
      ) : (
        <TriangleAlert className="mr-1.5 inline h-4 w-4" />
      )}
      {missing > 0 && (
        <>
          {missing} active tenanc{missing === 1 ? 'y has' : 'ies have'} no move-in inspection — a
          deposit deduction with no baseline is hard to defend.{' '}
        </>
      )}
      {overdue > 0 && (
        <>
          {overdue} unit{overdue === 1 ? '' : 's'} not inspected in over a year.{' '}
        </>
      )}
      <Link to="/inspections" className="font-medium underline">
        Review inspections
      </Link>
    </Alert>
  )
}
