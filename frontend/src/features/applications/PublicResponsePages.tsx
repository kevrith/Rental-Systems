import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { publicScreeningApi } from '@/api'
import { AuthLayout } from '@/features/auth/AuthLayout'
import { Alert, Button, Field, PageLoader, Textarea } from '@/components/ui'
import { errorMessage, kes } from '@/lib/format'

/** What a named guarantor sees when they open their WhatsApp link (US-065). */
export function GuaranteeResponsePage() {
  const { token } = useParams<{ token: string }>()
  const [done, setDone] = useState<string | null>(null)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const invite = useQuery({
    queryKey: ['guarantee', token],
    queryFn: () => publicScreeningApi.guarantee(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const respond = useMutation({
    mutationFn: (accepted: boolean) =>
      publicScreeningApi.respondToGuarantee(token!, {
        accepted,
        reason: accepted ? undefined : reason || undefined,
      }),
    onSuccess: (result) => setDone(result.message),
    onError: (respondError) => setError(errorMessage(respondError)),
  })

  if (invite.isPending) return <PageLoader />
  if (invite.isError) {
    return (
      <AuthLayout title="This link is not valid">
        <Alert tone="warn">
          The link may have expired or already been used. Ask the landlord to send a new one.
        </Alert>
      </AuthLayout>
    )
  }

  if (done) {
    return (
      <AuthLayout title="Thank you">
        <div className="flex flex-col items-center gap-3 text-center">
          <Check className="h-10 w-10 text-money-600" />
          <p className="text-sm text-slate-600">{done}</p>
        </div>
      </AuthLayout>
    )
  }

  const data = invite.data

  if (data.already_answered) {
    return (
      <AuthLayout title="Already answered">
        <Alert tone="info">
          You have already responded to this guarantee request. Thank you.
        </Alert>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title={`Hello ${data.guarantor_name}`}
      subtitle="You have been named as a guarantor. Please confirm or decline."
    >
      <div className="space-y-5">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
          <p className="text-slate-700">
            <span className="font-medium">{data.applicant_name}</span> has applied to rent unit{' '}
            <span className="font-medium">{data.unit_number}</span> at{' '}
            <span className="font-medium">{data.property_name}</span> for{' '}
            <span className="font-medium">{kes(data.monthly_rent)}</span> a month, and has listed
            you as their guarantor ({data.relationship_to_applicant}).
          </p>
        </div>

        <Alert tone="warn" icon={<ShieldCheck className="h-4 w-4" />}>
          Confirming means that if {data.applicant_name.split(' ')[0]} does not pay the rent, the
          landlord may look to you for it. Only confirm if you are willing to stand behind that.
        </Alert>

        {declining ? (
          <div className="space-y-3">
            <Field label="Anything you would like to add?" hint="Optional">
              <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
            </Field>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setDeclining(false)}>
                Back
              </Button>
              <Button
                variant="danger"
                className="flex-1 justify-center"
                loading={respond.isPending}
                onClick={() => {
                  setError(null)
                  respond.mutate(false)
                }}
              >
                Confirm I decline
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <Button
              className="w-full justify-center"
              size="lg"
              icon={<ThumbsUp className="h-4 w-4" />}
              loading={respond.isPending}
              onClick={() => {
                setError(null)
                respond.mutate(true)
              }}
            >
              Yes, I will guarantee this tenancy
            </Button>
            <Button
              variant="outline"
              className="w-full justify-center"
              icon={<ThumbsDown className="h-4 w-4" />}
              onClick={() => setDeclining(true)}
            >
              No, I decline
            </Button>
          </div>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </AuthLayout>
  )
}

/** What a previous landlord sees when asked for a reference (US-068). */
export function ReferenceResponsePage() {
  const { token } = useParams<{ token: string }>()
  const [done, setDone] = useState<string | null>(null)
  const [paidOnTime, setPaidOnTime] = useState<boolean | null>(null)
  const [wouldRentAgain, setWouldRentAgain] = useState<boolean | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const invite = useQuery({
    queryKey: ['reference', token],
    queryFn: () => publicScreeningApi.reference(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const respond = useMutation({
    mutationFn: () =>
      publicScreeningApi.respondToReference(token!, {
        paid_on_time: paidOnTime!,
        would_rent_again: wouldRentAgain!,
        note: note || undefined,
      }),
    onSuccess: (result) => setDone(result.message),
    onError: (respondError) => setError(errorMessage(respondError)),
  })

  if (invite.isPending) return <PageLoader />
  if (invite.isError) {
    return (
      <AuthLayout title="This link is not valid">
        <Alert tone="warn">The link may have expired or already been used.</Alert>
      </AuthLayout>
    )
  }

  if (done) {
    return (
      <AuthLayout title="Thank you">
        <div className="flex flex-col items-center gap-3 text-center">
          <Check className="h-10 w-10 text-money-600" />
          <p className="text-sm text-slate-600">{done}</p>
        </div>
      </AuthLayout>
    )
  }

  const data = invite.data

  if (data.already_answered) {
    return (
      <AuthLayout title="Already answered">
        <Alert tone="info">You have already answered this reference request. Thank you.</Alert>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title={`Hello ${data.landlord_name}`}
      subtitle={`Two quick questions about ${data.applicant_name}.`}
    >
      <div className="space-y-5">
        {data.property_reference && (
          <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            They gave their address as {data.property_reference}.
          </p>
        )}

        <YesNo
          question={`Did ${data.applicant_name.split(' ')[0]} pay rent on time?`}
          value={paidOnTime}
          onChange={setPaidOnTime}
        />
        <YesNo
          question="Would you rent to them again?"
          value={wouldRentAgain}
          onChange={setWouldRentAgain}
        />

        <Field label="Anything else the landlord should know?" hint="Optional">
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>

        {error && <Alert tone="danger">{error}</Alert>}

        <Button
          className="w-full justify-center"
          size="lg"
          disabled={paidOnTime === null || wouldRentAgain === null}
          loading={respond.isPending}
          onClick={() => {
            setError(null)
            respond.mutate()
          }}
        >
          Send my answer
        </Button>

        <p className="text-center text-xs text-slate-400">
          Your answer is shared only with the landlord who asked.
        </p>
      </div>
    </AuthLayout>
  )
}

function YesNo({
  question,
  value,
  onChange,
}: {
  question: string
  value: boolean | null
  onChange: (value: boolean) => void
}) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-slate-800">{question}</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onChange(true)}
          className={
            value === true
              ? 'flex-1 rounded-lg border-2 border-money-500 bg-money-50 px-4 py-3 text-sm font-medium text-money-700'
              : 'flex-1 rounded-lg border border-slate-300 px-4 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50'
          }
        >
          Yes
        </button>
        <button
          type="button"
          onClick={() => onChange(false)}
          className={
            value === false
              ? 'flex-1 rounded-lg border-2 border-danger-500 bg-danger-50 px-4 py-3 text-sm font-medium text-danger-700'
              : 'flex-1 rounded-lg border border-slate-300 px-4 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50'
          }
        >
          No
        </button>
      </div>
    </div>
  )
}
