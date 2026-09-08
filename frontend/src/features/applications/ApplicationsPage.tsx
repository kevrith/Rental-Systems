import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Search, ShieldCheck, UserCheck, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { applicationsApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Badge,
  Card,
  EmptyState,
  Input,
  Skeleton,
  Tab,
  Tabs,
  linkButtonClass,
} from '@/components/ui'
import { humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

import { ScoreDot } from './score'

const STATUS_TABS = [
  { key: '', label: 'All' },
  { key: 'submitted', label: 'New' },
  { key: 'under_review', label: 'In review' },
  { key: 'interview_scheduled', label: 'Interview' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
]

export const APPLICATION_STATUS_TONE: Record<string, 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info'> = {
  submitted: 'warn',
  under_review: 'info',
  interview_scheduled: 'brand',
  approved: 'success',
  rejected: 'danger',
  withdrawn: 'neutral',
}

export function ApplicationsPage() {
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('application:manage'))

  const summary = useQuery({
    queryKey: queryKeys.screeningSummary,
    queryFn: applicationsApi.summary,
  })

  const applications = useQuery({
    queryKey: queryKeys.applications({ status, search }),
    queryFn: () =>
      applicationsApi.list({
        application_status: status || undefined,
        search: search || undefined,
        limit: 200,
      }),
  })

  return (
    <div>
      <PageHeader
        title="Applications"
        description="Everyone who wants a unit, scored on what they can afford and who vouches for them."
        actions={
          canManage && (
            <Link to="/applications/new" className={linkButtonClass()}>
              <UserPlus className="h-4 w-4" />
              Take an application
            </Link>
          )
        }
      />

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Open applications"
          value={String(summary.data?.open ?? 0)}
          hint={`${summary.data?.last_30_days ?? 0} received in 30 days`}
          icon={<ClipboardList className="h-4 w-4" />}
        />
        <StatCard
          label="Awaiting review"
          value={String(summary.data?.awaiting_review ?? 0)}
          tone={(summary.data?.awaiting_review ?? 0) > 0 ? 'warn' : 'default'}
          icon={<Search className="h-4 w-4" />}
        />
        <StatCard
          label="Waiting on a guarantor"
          value={String(summary.data?.awaiting_guarantor ?? 0)}
          icon={<ShieldCheck className="h-4 w-4" />}
        />
        <StatCard
          label="Waiting on a reference"
          value={String(summary.data?.awaiting_reference ?? 0)}
          icon={<UserCheck className="h-4 w-4" />}
        />
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={status} onChange={setStatus}>
          {STATUS_TABS.map((tab) => (
            <Tab key={tab.key} value={tab.key}>
              {tab.label}
            </Tab>
          ))}
        </Tabs>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Name, phone or reference"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
      </div>

      {applications.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-20" />
          ))}
        </div>
      ) : applications.data?.length ? (
        <div className="space-y-3">
          {applications.data.map((application) => (
            <Link
              key={application.id}
              to={`/applications/${application.id}`}
              className="block rounded-card border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-slate-900">{application.full_name}</p>
                    <Badge tone={APPLICATION_STATUS_TONE[application.status] ?? 'neutral'}>
                      {humanize(application.status)}
                    </Badge>
                    {application.submitted_online && <Badge tone="neutral">Online</Badge>}
                  </div>
                  <p className="mt-1 text-sm text-slate-600">
                    {application.property_name} unit {application.unit_number}
                    {application.monthly_rent ? ` · ${kes(application.monthly_rent)}/month` : ''}
                  </p>
                  <p className="mt-1.5 text-xs text-slate-400">
                    {application.reference_code} · {application.phone_number} · applied{' '}
                    {shortDate(application.created_at)}
                  </p>
                </div>
                <ScoreDot score={application.score} band={application.band} />
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<ClipboardList className="h-6 w-6" />}
            title="No applications"
            description="Share a vacant unit's application link and the applications land here, already scored."
          />
        </Card>
      )}
    </div>
  )
}
