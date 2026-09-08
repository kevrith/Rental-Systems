import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSignature, Send, Undo2, XCircle } from 'lucide-react'
import { useState } from 'react'

import { filesApi, managementAgreementsApi } from '@/api'
import type { ManagementAgreement, ManagementAgreementStatus } from '@/api/types'
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
  Field,
  Input,
  Skeleton,
  Textarea,
  type BadgeTone,
} from '@/components/ui'
import { errorMessage, kes, shortDate, today } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/**
 * The owner-agency management agreement (masterplan, Management Agreement Module).
 *
 * Shown on the owner's own page because that is where an agency admin is when
 * the question "what did we actually agree with this client?" comes up.
 *
 * The terms shown here are the ones *as signed*, not the ones on the owner
 * profile above. When the two differ — because somebody edited the profile
 * after signing — that difference is the point, and seeing both is the
 * difference between an argument and an audit.
 */

const STATUS_TONE: Record<ManagementAgreementStatus, BadgeTone> = {
  draft: 'neutral',
  pending_signatures: 'warn',
  active: 'success',
  termination_notice: 'warn',
  terminated: 'neutral',
  expired: 'neutral',
  cancelled: 'neutral',
}

const STATUS_LABEL: Record<ManagementAgreementStatus, string> = {
  draft: 'Draft',
  pending_signatures: 'Awaiting signatures',
  active: 'In force',
  termination_notice: 'Notice served',
  terminated: 'Ended',
  expired: 'Expired',
  cancelled: 'Cancelled',
}

export function ManagementAgreementPanel({ ownerProfileId }: { ownerProfileId: string }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [sending, setSending] = useState<ManagementAgreement | null>(null)
  const [terminating, setTerminating] = useState<ManagementAgreement | null>(null)

  const [startDate, setStartDate] = useState(today())
  const [termMonths, setTermMonths] = useState('12')
  const [noticeDays, setNoticeDays] = useState('90')
  const [signatoryName, setSignatoryName] = useState('')
  const [signatoryPhone, setSignatoryPhone] = useState('')
  const [terminationReason, setTerminationReason] = useState('')

  const agreements = useQuery({
    queryKey: queryKeys.managementAgreements({ ownerProfileId }),
    queryFn: () => managementAgreementsApi.list({ owner_profile_id: ownerProfileId }),
  })

  const settled = async () => {
    setError(null)
    setCreating(false)
    setSending(null)
    setTerminating(null)
    setTerminationReason('')
    await queryClient.invalidateQueries({ queryKey: ['agency', 'management-agreements'] })
  }
  const failed = (mutationError: unknown) => setError(errorMessage(mutationError))

  const create = useMutation({
    mutationFn: () =>
      managementAgreementsApi.create({
        owner_profile_id: ownerProfileId,
        start_date: startDate,
        term_months: Number(termMonths) || 12,
        notice_period_days: Number(noticeDays) || 90,
      }),
    onSuccess: settled,
    onError: failed,
  })

  const send = useMutation({
    mutationFn: (id: string) =>
      managementAgreementsApi.send(id, {
        agency_signatory_name: signatoryName.trim(),
        agency_signatory_phone: signatoryPhone.trim(),
      }),
    onSuccess: settled,
    onError: failed,
  })

  const terminate = useMutation({
    mutationFn: (id: string) =>
      managementAgreementsApi.terminate(id, {
        requested_by: 'agency',
        reason: terminationReason.trim() || undefined,
      }),
    onSuccess: settled,
    onError: failed,
  })

  const withdraw = useMutation({
    mutationFn: (id: string) => managementAgreementsApi.withdrawTermination(id),
    onSuccess: settled,
    onError: failed,
  })

  // Stored documents are handed out as short-lived signed URLs rather than
  // being publicly addressable, so the link has to be fetched on click.
  const openDocument = useMutation({
    mutationFn: (fileId: string) => filesApi.get(fileId),
    onSuccess: (file) => window.open(file.url, '_blank', 'noopener'),
    onError: failed,
  })

  const rows = agreements.data ?? []
  const live = rows.find(
    (row) => row.status === 'active' || row.status === 'termination_notice',
  )

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Management agreement</CardTitle>
          <p className="text-xs text-slate-500">
            The contract itself. The terms below are as both parties signed them — editing the
            profile above changes what the software does from now on, not what was agreed.
          </p>
        </CardHeader>
        <CardBody className="space-y-3">
          {error && <Alert tone="danger">{error}</Alert>}

          {agreements.isPending ? (
            <Skeleton className="h-24" />
          ) : rows.length === 0 ? (
            <EmptyState
              icon={<FileSignature className="h-6 w-6" />}
              title="No agreement on file"
              description="Draft one from this owner's current terms. Nothing is binding until both parties sign."
              action={
                <Button variant="secondary" onClick={() => setCreating(true)}>
                  Draft an agreement
                </Button>
              }
            />
          ) : (
            <>
              {rows.map((row) => (
                <div key={row.id} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="flex items-center gap-2 text-sm font-medium text-slate-900">
                        {row.reference_code}
                        <Badge tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Badge>
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {row.management_fee_percent}% of rent collected · paid out on day{' '}
                        {row.disbursement_day} · {row.notice_period_days} days&apos; notice
                      </p>
                      <p className="text-xs text-slate-500">
                        From {shortDate(row.start_date)}
                        {row.end_date ? ` to ${shortDate(row.end_date)}` : ' (open-ended)'} ·
                        repairs to {kes(row.maintenance_auto_approve_limit)} without asking
                      </p>
                      {row.termination_effective_date && (
                        <p className="mt-1 text-xs font-medium text-warn-700">
                          Notice served by the {row.termination_requested_by} — management ends{' '}
                          {shortDate(row.termination_effective_date)}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {row.document_id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={openDocument.isPending && openDocument.variables === row.document_id}
                          onClick={() => openDocument.mutate(row.document_id!)}
                        >
                          Open PDF
                        </Button>
                      )}
                      {(row.status === 'draft' || row.status === 'pending_signatures') && (
                        <Button
                          size="sm"
                          variant="outline"
                          icon={<Send className="h-4 w-4" />}
                          onClick={() => {
                            setError(null)
                            setSending(row)
                          }}
                        >
                          Send for signature
                        </Button>
                      )}
                      {row.status === 'active' && (
                        <Button
                          size="sm"
                          variant="outline"
                          icon={<XCircle className="h-4 w-4" />}
                          onClick={() => {
                            setError(null)
                            setTerminating(row)
                          }}
                        >
                          Serve notice
                        </Button>
                      )}
                      {row.status === 'termination_notice' && (
                        <Button
                          size="sm"
                          variant="outline"
                          icon={<Undo2 className="h-4 w-4" />}
                          loading={withdraw.isPending}
                          onClick={() => withdraw.mutate(row.id)}
                        >
                          Withdraw notice
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {!live && (
                <Button variant="secondary" onClick={() => setCreating(true)}>
                  Draft a new agreement
                </Button>
              )}
            </>
          )}
        </CardBody>
      </Card>

      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Draft a management agreement"
        description="The fee, disbursement day and authority limits are copied from this owner's profile and frozen as agreed."
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button loading={create.isPending} onClick={() => create.mutate()}>
              Create draft
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Start date" required>
            <Input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Initial term (months)" hint="0 for an open-ended agreement.">
              <Input
                type="number"
                min="0"
                max="120"
                value={termMonths}
                onChange={(event) => setTermMonths(event.target.value)}
              />
            </Field>
            <Field label="Notice period (days)" hint="At least 30 — deposits and tenants have to be handed over.">
              <Input
                type="number"
                min="30"
                max="365"
                value={noticeDays}
                onChange={(event) => setNoticeDays(event.target.value)}
              />
            </Field>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={sending !== null}
        onClose={() => setSending(null)}
        title="Send for signature"
        description="The owner gets a link on the number in their profile. Whoever signs for the agency gets their own — neither party can sign for the other, and the agreement is not in force until both have."
        footer={
          <>
            <Button variant="ghost" onClick={() => setSending(null)}>
              Cancel
            </Button>
            <Button
              loading={send.isPending}
              disabled={signatoryName.trim().length < 2 || signatoryPhone.trim().length < 9}
              onClick={() => sending && send.mutate(sending.id)}
            >
              Send both links
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Who signs for the agency" required>
            <Input
              value={signatoryName}
              onChange={(event) => setSignatoryName(event.target.value)}
              placeholder="Agnes Kariuki"
            />
          </Field>
          <Field label="Their phone number" required hint="The signing code is sent here by SMS.">
            <Input
              type="tel"
              value={signatoryPhone}
              onChange={(event) => setSignatoryPhone(event.target.value)}
              placeholder="+254712345678"
            />
          </Field>
        </div>
      </Dialog>

      <Dialog
        open={terminating !== null}
        onClose={() => setTerminating(null)}
        title="Serve notice to terminate?"
        description="Management continues until the notice period ends — rent is still collected and the fee is still earned until then."
        footer={
          <>
            <Button variant="ghost" onClick={() => setTerminating(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={terminate.isPending}
              onClick={() => terminating && terminate.mutate(terminating.id)}
            >
              Serve notice
            </Button>
          </>
        }
      >
        <Field label="Reason" hint="Shown to the owner and kept on the audit trail.">
          <Textarea
            rows={3}
            value={terminationReason}
            onChange={(event) => setTerminationReason(event.target.value)}
            placeholder="The owner is selling the building."
          />
        </Field>
      </Dialog>
    </>
  )
}
