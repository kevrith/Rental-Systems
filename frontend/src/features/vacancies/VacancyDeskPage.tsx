import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarX, Check, Copy, DoorOpen, Eye, Phone, TrendingDown, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { vacanciesApi } from '@/api'
import type { InquiryRow } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  PageLoader,
  Skeleton,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { humanize, kes, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const STAGE_TONE: Record<string, 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info'> = {
  inquired: 'warn',
  applied: 'info',
  under_review: 'brand',
  approved: 'success',
  rejected: 'danger',
  lost: 'neutral',
}

/** The vacancy desk: what is empty, what it is costing, and who has asked. */
export function VacancyDeskPage() {
  const desk = useQuery({ queryKey: queryKeys.vacancyDesk, queryFn: vacanciesApi.desk })
  const conversion = useQuery({
    queryKey: queryKeys.vacancyConversion,
    queryFn: vacanciesApi.conversion,
  })
  const leads = useQuery({
    queryKey: queryKeys.inquiries(),
    queryFn: () => vacanciesApi.inquiries(),
  })

  if (desk.isPending) return <PageLoader />

  const report = desk.data!

  return (
    <div>
      <PageHeader
        title="Vacancies"
        description="Every empty unit, what it is costing you, and everyone who has asked about it."
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Empty units"
          value={String(report.vacant_units)}
          icon={<DoorOpen className="h-4 w-4" />}
        />
        <StatCard
          label="Rent lost so far"
          value={kes(report.total_revenue_lost)}
          tone={report.total_revenue_lost > 0 ? 'danger' : 'default'}
          hint="Days empty × daily rent"
          icon={<TrendingDown className="h-4 w-4" />}
        />
        <StatCard
          label="Monthly rent at risk"
          value={kes(report.monthly_revenue_at_risk)}
          hint="If nothing is let"
          icon={<CalendarX className="h-4 w-4" />}
        />
        <StatCard
          label="Open leads"
          value={String(leads.data?.length ?? 0)}
          hint={
            conversion.data?.stale_leads
              ? `${conversion.data.stale_leads} gone cold`
              : 'All followed up'
          }
          tone={conversion.data?.stale_leads ? 'warn' : 'default'}
          icon={<Users className="h-4 w-4" />}
        />
      </div>

      {conversion.data && conversion.data.inquiries > 0 && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle>How enquiries turn into tenancies</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <Funnel label="Enquiries" value={conversion.data.inquiries} />
              <Arrow percent={conversion.data.inquiry_to_application_percent} />
              <Funnel label="Applications" value={conversion.data.applications} />
              <Arrow percent={conversion.data.application_to_approval_percent} />
              <Funnel label="Approved" value={conversion.data.approvals} />
            </div>
          </CardBody>
        </Card>
      )}

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Empty units</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {report.units.length ? (
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <Th>Unit</Th>
                    <Th>Empty for</Th>
                    <Th>Rent lost</Th>
                    <Th>Interest</Th>
                    <Th>Link</Th>
                  </tr>
                </thead>
                <tbody>
                  {report.units.map((unit) => (
                    <tr key={unit.unit_id}>
                      <Td>
                        <Link
                          to={`/units/${unit.unit_id}`}
                          className="font-medium text-slate-800 hover:text-brand-700"
                        >
                          {unit.property_name} {unit.unit_number}
                        </Link>
                        <p className="text-xs text-slate-400">
                          {kes(unit.monthly_rent)}/month · {humanize(unit.status)}
                        </p>
                      </Td>
                      <Td>
                        {unit.days_vacant === null ? (
                          '—'
                        ) : (
                          <span
                            className={
                              unit.days_vacant > 60 ? 'font-medium text-danger-700' : undefined
                            }
                          >
                            {unit.days_vacant} day{unit.days_vacant === 1 ? '' : 's'}
                          </span>
                        )}
                        {unit.vacant_since && (
                          <p className="text-xs text-slate-400">
                            since {shortDate(unit.vacant_since)}
                          </p>
                        )}
                      </Td>
                      <Td className={unit.revenue_lost > 0 ? 'text-danger-700' : undefined}>
                        {kes(unit.revenue_lost)}
                      </Td>
                      <Td className="text-slate-600">
                        <span className="inline-flex items-center gap-1 text-xs">
                          <Eye className="h-3.5 w-3.5 text-slate-400" />
                          {unit.views}
                        </span>
                        <span className="ml-3 text-xs">
                          {unit.open_leads} lead{unit.open_leads === 1 ? '' : 's'} ·{' '}
                          {unit.applications} application{unit.applications === 1 ? '' : 's'}
                        </span>
                      </Td>
                      <Td>
                        {unit.listing_slug ? (
                          <CopyLink slug={unit.listing_slug} />
                        ) : (
                          <Link
                            to={`/units/${unit.unit_id}`}
                            className="text-sm text-brand-600 hover:text-brand-700"
                          >
                            Create one
                          </Link>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          ) : (
            <EmptyState
              icon={<DoorOpen className="h-6 w-6" />}
              title="Everything is let"
              description="No empty units — nothing is costing you rent right now."
            />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Leads</CardTitle>
          <span className="text-sm text-slate-500">Newest first</span>
        </CardHeader>
        <CardBody className="p-0">
          {leads.isPending ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-12" />
              ))}
            </div>
          ) : leads.data?.length ? (
            <ul className="divide-y divide-slate-100">
              {leads.data.map((lead) => (
                <LeadRow key={lead.id} lead={lead} />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={<Users className="h-6 w-6" />}
              title="Nobody has asked yet"
              description="Share a listing link on WhatsApp and enquiries land here."
            />
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function Funnel({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-50 px-4 py-3 text-center">
      <p className="text-2xl font-semibold text-slate-900">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  )
}

function Arrow({ percent }: { percent: number | null }) {
  return (
    <div className="text-center text-xs text-slate-400">
      <span className="block">&rarr;</span>
      {percent !== null && <span className="font-medium text-slate-600">{percent}%</span>}
    </div>
  )
}

function CopyLink({ slug }: { slug: string }) {
  const [copied, setCopied] = useState(false)
  const url = `${window.location.origin}/listing/${slug}`

  return (
    <button
      type="button"
      className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700"
      onClick={async () => {
        await navigator.clipboard.writeText(url)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 2000)
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : 'Copy link'}
    </button>
  )
}

function LeadRow({ lead }: { lead: InquiryRow }) {
  const queryClient = useQueryClient()

  const contacted = useMutation({
    mutationFn: () => vacanciesApi.updateInquiry(lead.id, { mark_contacted: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['vacancies'] }),
  })

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 px-5 py-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-slate-900">{lead.full_name}</p>
          <Badge tone={STAGE_TONE[lead.stage] ?? 'neutral'}>{humanize(lead.stage)}</Badge>
          {lead.is_stale && <Badge tone="danger">Gone cold</Badge>}
        </div>
        <p className="mt-0.5 text-sm text-slate-600">
          {lead.property_name} {lead.unit_number} · asked {shortDate(lead.created_at)}
        </p>
        {lead.message && <p className="mt-1 text-sm text-slate-500">{lead.message}</p>}
        {lead.notes && <p className="mt-1 text-xs text-slate-400">{lead.notes}</p>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <a
          href={`tel:${lead.phone_number}`}
          className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700"
        >
          <Phone className="h-3.5 w-3.5" />
          {lead.phone_number}
        </a>
        {lead.application_id ? (
          <Link
            to={`/applications/${lead.application_id}`}
            className="text-xs text-brand-600 hover:text-brand-700"
          >
            See their application
          </Link>
        ) : (
          <button
            type="button"
            className="text-xs text-slate-500 hover:text-slate-800"
            onClick={() => contacted.mutate()}
          >
            {contacted.isPending ? 'Saving…' : 'Mark as contacted'}
          </button>
        )}
      </div>
    </li>
  )
}
