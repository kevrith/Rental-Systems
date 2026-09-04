import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, Download, FileText, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { renewalsApi } from '@/api'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  Field,
  PageLoader,
  Textarea,
} from '@/components/ui'
import { errorMessage, kes, shortDate } from '@/lib/format'

/**
 * The tenant's renewal page (US-057).
 *
 * Reached from a WhatsApp link, on a phone, by someone with no account — the
 * token in the URL is the whole authentication. So the page has to work cold:
 * state the terms in full, show the agreement, and offer exactly two answers.
 */
export function RenewalPage() {
  const { token = '' } = useParams()
  const [declineOpen, setDeclineOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [outcome, setOutcome] = useState<{ accepted: boolean; message: string } | null>(null)

  const offer = useQuery({
    queryKey: ['renewal', token],
    queryFn: () => renewalsApi.read(token),
    enabled: Boolean(token),
    retry: false,
  })

  const accept = useMutation({
    mutationFn: () => renewalsApi.accept(token),
    onSuccess: (result) => setOutcome({ accepted: true, message: result.message }),
  })

  const decline = useMutation({
    mutationFn: () => renewalsApi.decline(token, reason.trim() || undefined),
    onSuccess: (result) => {
      setDeclineOpen(false)
      setOutcome({ accepted: false, message: result.message })
    },
  })

  if (offer.isPending) return <PageLoader />

  if (offer.isError) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Alert tone="danger" title="This link cannot be opened">
          {errorMessage(offer.error)} If you think this is a mistake, contact your landlord or
          agent — they can send you a new one.
        </Alert>
      </div>
    )
  }

  const data = offer.data
  const rentChanged = Number(data.proposed_rent) !== Number(data.current_rent)

  if (outcome) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <Card>
          <CardBody className="space-y-3 text-center">
            {outcome.accepted ? (
              <CheckCircle2 className="mx-auto h-10 w-10 text-money-600" />
            ) : (
              <XCircle className="mx-auto h-10 w-10 text-slate-400" />
            )}
            <h1 className="text-lg font-semibold text-slate-900">
              {outcome.accepted ? 'Renewal confirmed' : 'Renewal declined'}
            </h1>
            <p className="text-sm text-slate-600">{outcome.message}</p>
            {data.agreement_url && outcome.accepted && (
              <a
                href={data.agreement_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-brand-700 hover:underline"
              >
                <Download className="h-4 w-4" />
                Download your renewal agreement
              </a>
            )}
          </CardBody>
        </Card>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg space-y-4 p-4 sm:p-6">
      <div>
        <p className="text-sm text-slate-500">{data.landlord_name}</p>
        <h1 className="text-xl font-semibold text-slate-900">Your lease renewal</h1>
        <p className="mt-1 text-sm text-slate-600">
          {data.tenant_name}, unit {data.unit_number} at {data.property_name}.
        </p>
      </div>

      {(accept.isError || decline.isError) && (
        <Alert tone="danger">{errorMessage(accept.error ?? decline.error)}</Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">What is being offered</CardTitle>
        </CardHeader>
        <CardBody>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-600">Current lease ends</dt>
              <dd className="font-medium">{shortDate(data.current_end_date)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-600">New term</dt>
              <dd className="text-right font-medium">
                {shortDate(data.new_start_date)} to {shortDate(data.new_end_date)}
                <span className="block text-xs font-normal text-slate-400">
                  {data.term_months} months
                </span>
              </dd>
            </div>
            <div className="flex justify-between border-t border-slate-100 pt-3">
              <dt className="text-slate-600">Monthly rent</dt>
              <dd className="text-right">
                {rentChanged ? (
                  <>
                    <span className="text-slate-400 line-through">{kes(data.current_rent)}</span>
                    <span className="ml-2 text-base font-semibold text-slate-900">
                      {kes(data.proposed_rent)}
                    </span>
                    <span className="block text-xs text-warn-700">
                      +{Number(data.rent_increase_percent).toFixed(1)}% from{' '}
                      {shortDate(data.new_start_date)}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="text-base font-semibold text-slate-900">
                      {kes(data.proposed_rent)}
                    </span>
                    <span className="block text-xs text-money-700">No change</span>
                  </>
                )}
              </dd>
            </div>
          </dl>

          {data.agreement_url && (
            <a
              href={data.agreement_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex items-center gap-1.5 text-sm text-brand-700 hover:underline"
            >
              <FileText className="h-4 w-4" />
              Read the full renewal agreement
            </a>
          )}
        </CardBody>
      </Card>

      <Alert tone="info">
        Please answer by <strong>{shortDate(data.respond_by)}</strong>. Accepting keeps you in the
        unit with no break. Declining ends your tenancy on{' '}
        {shortDate(data.current_end_date)}, and your landlord will arrange the move-out inspection
        and your deposit.
      </Alert>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          className="flex-1"
          loading={accept.isPending}
          icon={<CheckCircle2 className="h-4 w-4" />}
          onClick={() => accept.mutate()}
        >
          Accept and renew
        </Button>
        <Button
          className="flex-1"
          variant="outline"
          icon={<XCircle className="h-4 w-4" />}
          onClick={() => setDeclineOpen(true)}
        >
          Decline
        </Button>
      </div>

      <Dialog
        open={declineOpen}
        onClose={() => setDeclineOpen(false)}
        title="Decline the renewal?"
        description={`Your tenancy would end on ${shortDate(data.current_end_date)} and you would need to move out by then.`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeclineOpen(false)}>
              Go back
            </Button>
            <Button variant="danger" loading={decline.isPending} onClick={() => decline.mutate()}>
              Yes, decline
            </Button>
          </>
        }
      >
        <Field label="Why? (optional)" hint="It helps your landlord, and is not binding on you.">
          <Textarea
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Moving closer to work"
          />
        </Field>
      </Dialog>
    </div>
  )
}
