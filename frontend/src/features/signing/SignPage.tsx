import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, ExternalLink, FileText } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import { publicSigningApi } from '@/api'
import { SignaturePad } from '@/components/SignaturePad'
import { Alert, Button, Field, Input, PageLoader } from '@/components/ui'
import { AuthLayout } from '@/features/auth/AuthLayout'
import { useAuthConfig } from '@/features/auth/useAuthConfig'
import { errorMessage } from '@/lib/format'

const DOCUMENT_NAMES: Record<string, string> = {
  owner: 'property management agreement',
  agency: 'property management agreement',
  guarantor: 'deed of guarantee',
}

/**
 * Where someone lands from a signing link. No account: the link is the whole
 * authentication, and the one-time code proves it is really them holding the
 * phone the landlord sent it to.
 */
export function SignPage() {
  const { token } = useParams<{ token: string }>()
  const { otpDelivery } = useAuthConfig()
  const [code, setCode] = useState('')
  // undefined until the signer touches the pad, so the saved signature shows by default.
  const [drawn, setDrawn] = useState<string | null | undefined>(undefined)
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [codeNote, setCodeNote] = useState<string | null>(null)
  const [signedAt, setSignedAt] = useState<string | null>(null)

  const request = useQuery({
    queryKey: ['signing', token],
    queryFn: () => publicSigningApi.get(token!),
    enabled: Boolean(token),
    retry: false,
  })

  // The saved signature, if the signer has one, is a starting point they can redraw.
  const savedSignature = request.data?.saved_signature ?? null
  const signature = drawn === undefined ? savedSignature : drawn

  const documentQuery = useQuery({
    queryKey: ['signing-document', token],
    queryFn: () => publicSigningApi.document(token!),
    enabled: Boolean(token) && request.isSuccess,
    retry: false,
  })

  // An object URL holds the file in memory until it is revoked.
  const documentUrl = useMemo(
    () => (documentQuery.data ? URL.createObjectURL(documentQuery.data) : null),
    [documentQuery.data],
  )
  useEffect(() => {
    return () => {
      if (documentUrl) URL.revokeObjectURL(documentUrl)
    }
  }, [documentUrl])

  const requestCode = useMutation({
    mutationFn: () => publicSigningApi.requestCode(token!),
    onSuccess: (result) => {
      setError(null)
      setCodeNote(
        result.delivery === 'manual'
          ? result.message
          : 'We have texted you a code. It can take a minute to arrive.',
      )
    },
    onError: (codeError) => setError(errorMessage(codeError)),
  })

  const sign = useMutation({
    mutationFn: () =>
      publicSigningApi.sign(token!, { otp_code: code.trim(), signature_image: signature! }),
    onSuccess: (result) => setSignedAt(result.signed_at ?? new Date().toISOString()),
    onError: (signError) => setError(errorMessage(signError, 'That code did not work.')),
  })

  if (request.isPending) return <PageLoader />

  if (request.isError) {
    return (
      <AuthLayout title="This link is not valid">
        <Alert tone="warn">
          The link may have expired, already been used, or been replaced by a newer one. Ask your
          landlord or caretaker to send you a new one.
        </Alert>
      </AuthLayout>
    )
  }

  if (signedAt) {
    return (
      <AuthLayout title="Thank you, it is signed">
        <div className="flex flex-col items-center gap-3 text-center">
          <Check className="h-10 w-10 text-money-600" />
          <p className="text-sm text-slate-600">
            Your signature has been recorded. You can close this page. The landlord has been told.
          </p>
        </div>
      </AuthLayout>
    )
  }

  const data = request.data
  const documentName = DOCUMENT_NAMES[data.signer_role] ?? 'lease agreement'
  const codeLooksRight = /^\d{4,8}$/.test(code.trim())
  const ready = codeLooksRight && signature !== null && agreed

  return (
    <AuthLayout
      wide
      title={`Hello ${data.signer_name.split(' ')[0]}`}
      subtitle={`Please read your ${documentName}, then sign it below.`}
    >
      <div className="space-y-6">
        <section aria-labelledby="doc-heading" className="space-y-2">
          <h2 id="doc-heading" className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <FileText className="h-4 w-4" />
            The document
          </h2>
          {documentQuery.isPending && <p className="text-sm text-slate-500">Loading the document…</p>}
          {documentQuery.isError && (
            <Alert tone="warn">
              The document could not be loaded here. Ask your landlord or caretaker to send it to
              you, and do not sign what you have not read.
            </Alert>
          )}
          {documentUrl && (
            <>
              <iframe
                title={`Your ${documentName}`}
                src={documentUrl}
                className="h-96 w-full rounded-lg border border-slate-200"
              />
              <a
                href={documentUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-600 hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open it in its own tab (easier on a phone)
              </a>
            </>
          )}
        </section>

        <section aria-labelledby="code-heading" className="space-y-3">
          <h2 id="code-heading" className="text-sm font-semibold text-slate-900">
            Your signing code
          </h2>
          {otpDelivery === 'manual' ? (
            <p className="text-sm text-slate-600">
              Your landlord or caretaker sends you a code on WhatsApp or SMS. Enter it here. It
              works once.
            </p>
          ) : (
            <Button
              variant="outline"
              loading={requestCode.isPending}
              onClick={() => requestCode.mutate()}
            >
              Text me a code
            </Button>
          )}
          {codeNote && <Alert tone="info">{codeNote}</Alert>}
          <Field label="Code">
            <Input
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={8}
              placeholder="123456"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="text-center text-lg tracking-[0.4em]"
            />
          </Field>
        </section>

        <section aria-labelledby="sig-heading" className="space-y-2">
          <h2 id="sig-heading" className="text-sm font-semibold text-slate-900">
            Your signature
          </h2>
          <SignaturePad value={signature} onChange={setDrawn} height={160} />
          {savedSignature && (
            <p className="text-xs text-slate-500">
              We filled in the signature you saved before. Clear it to draw a new one.
            </p>
          )}
        </section>

        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={agreed}
            onChange={(event) => setAgreed(event.target.checked)}
            className="mt-0.5 h-4 w-4 accent-brand-600"
          />
          <span>I have read this {documentName} and I agree to sign it.</span>
        </label>

        {error && <Alert tone="danger">{error}</Alert>}

        <Button
          className="w-full justify-center"
          size="lg"
          disabled={!ready}
          loading={sign.isPending}
          onClick={() => {
            setError(null)
            sign.mutate()
          }}
        >
          Sign the document
        </Button>
      </div>
    </AuthLayout>
  )
}
