import { useQuery } from '@tanstack/react-query'
import { Mail, Phone, Star, Wallet, Wrench } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { vendorsApi } from '@/api'
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
  MAINTENANCE_STATUS_TONE,
  PageLoader,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { errorMessage, humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

import { DeactivateVendorButton, Rating, VendorDialog } from './VendorsPage'

export function VendorDetailPage() {
  const { vendorId } = useParams<{ vendorId: string }>()
  const [editing, setEditing] = useState(false)
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('vendor:manage'))

  const vendor = useQuery({
    queryKey: queryKeys.vendor(vendorId!),
    queryFn: () => vendorsApi.get(vendorId!),
    enabled: Boolean(vendorId),
  })

  if (vendor.isPending) return <PageLoader />
  if (vendor.isError) {
    return (
      <Alert tone="danger" title="Could not load this vendor">
        {errorMessage(vendor.error)}
      </Alert>
    )
  }

  const record = vendor.data

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={record.name}
        description={record.company_name ?? undefined}
        backTo="/vendors"
        backLabel="All vendors"
        actions={
          canManage && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              Edit
            </Button>
          )
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Jobs completed"
          value={String(record.jobs_completed)}
          icon={<Wrench className="h-4 w-4" />}
        />
        <StatCard
          label="Average rating"
          value={record.average_rating ? `${record.average_rating.toFixed(1)} / 5` : '—'}
          hint={record.rating_count ? `${record.rating_count} rated jobs` : 'No ratings yet'}
          icon={<Star className="h-4 w-4" />}
        />
        <StatCard
          label="Average job cost"
          value={record.jobs_completed ? kes(record.average_job_cost) : '—'}
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Open jobs"
          value={String(record.open_jobs)}
          tone={record.open_jobs > 0 ? 'warn' : 'default'}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader>
            <CardTitle>Contact</CardTitle>
            {!record.is_active && <Badge tone="neutral">Inactive</Badge>}
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="flex flex-wrap gap-1.5">
              {record.specialties.map((value) => (
                <Badge key={value} tone="brand">
                  {humanize(value)}
                </Badge>
              ))}
            </div>

            <div className="space-y-2 text-sm">
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
            </div>

            {record.rate_notes && (
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">Rates</p>
                <p className="mt-0.5 text-sm text-slate-700">{record.rate_notes}</p>
              </div>
            )}

            {record.notes && (
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="whitespace-pre-wrap text-sm text-slate-700">{record.notes}</p>
              </div>
            )}

            <p className="text-xs text-slate-400">
              Total billed to date: {kes(record.total_billed)}
            </p>

            {canManage && <DeactivateVendorButton vendor={record} openJobs={record.open_jobs} />}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Job history</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            {record.recent_jobs.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <thead>
                    <tr>
                      <Th>Job</Th>
                      <Th>Status</Th>
                      <Th>Cost</Th>
                      <Th>Rating</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {record.recent_jobs.map((job) => (
                      <tr key={job.id}>
                        <Td>
                          <Link
                            to={`/maintenance/${job.id}`}
                            className="font-medium text-slate-800 hover:text-brand-700"
                          >
                            {job.title}
                          </Link>
                          <p className="text-xs text-slate-400">
                            {job.property_name}
                            {job.unit_number ? ` unit ${job.unit_number}` : ''}
                            {job.completed_at ? ` · ${shortDate(job.completed_at)}` : ''}
                          </p>
                        </Td>
                        <Td>
                          <Badge tone={MAINTENANCE_STATUS_TONE[job.status] ?? 'neutral'}>
                            {humanize(job.status)}
                          </Badge>
                        </Td>
                        <Td>{job.cost ? kes(job.cost) : '—'}</Td>
                        <Td>
                          <Rating value={job.rating} />
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            ) : (
              <EmptyState
                icon={<Wrench className="h-6 w-6" />}
                title="No jobs yet"
                description="Assign this vendor a maintenance job and it will show up here."
              />
            )}
          </CardBody>
        </Card>
      </div>

      <VendorDialog open={editing} vendor={record} onClose={() => setEditing(false)} />
    </div>
  )
}
