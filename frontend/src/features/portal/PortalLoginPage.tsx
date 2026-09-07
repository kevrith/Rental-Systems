import { useMutation } from '@tanstack/react-query'
import { AlertCircle, MailCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { portalApi } from '@/api'
import { authApi } from '@/api/auth'
import { Alert, Button, Field, Input, PageLoader } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { useAuthStore } from '@/store/auth-store'

import { AuthLayout } from '@/features/auth/AuthLayout'

/**
 * Tenant sign-in by one-tap link (masterplan, Security § Authentication Layers).
 *
 * A tenant signs in perhaps twice a year, often on a borrowed or shared phone.
 * A password they set once eleven months ago is not a thing they have, and
 * "forgot password" is a worse flow for them than for staff — most have no
 * email address on file, only a phone.
 *
 * The page does double duty: with `?token=&t=` in the URL it consumes the link
 * and signs them in; without, it asks for a phone number. The request response
 * never varies, whether or not that number is a tenant, so this page cannot be
 * used to discover which numbers belong to a landlord's tenants.
 */
export function PortalLoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)

  const token = params.get('token') ?? ''
  const tenantId = params.get('t') ?? ''
  const arrivingByLink = Boolean(token && tenantId)

  const [phone, setPhone] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const request = useMutation({
    mutationFn: () => portalApi.requestMagicLink(phone.trim()),
    onSuccess: (result) => {
      setError(null)
      setSent(result.message)
    },
    onError: (mutationError) => setError(errorMessage(mutationError)),
  })

  const verify = useMutation({
    mutationFn: () => portalApi.verifyMagicLink({ token, tenant_id: tenantId }),
    onSuccess: async (data) => {
      setSession({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
        user: await authApi.me(),
      })
      navigate('/portal', { replace: true })
    },
    onError: (mutationError) =>
      setError(
        errorMessage(mutationError, 'That sign-in link has expired or has already been used.'),
      ),
  })

  // Consume the link on arrival. `mutate` is stable, and the guard means this
  // runs exactly once per set of link parameters.
  const startVerify = verify.mutate
  useEffect(() => {
    if (arrivingByLink) startVerify()
  }, [arrivingByLink, startVerify])

  if (arrivingByLink && verify.isPending) {
    return (
      <AuthLayout title="Signing you in">
        <PageLoader />
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Tenant sign-in"
      subtitle="Enter the phone number your landlord has for you and we will send a link that signs you straight in."
    >
      {error && (
        <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />} className="mb-4">
          {error}
        </Alert>
      )}

      {sent ? (
        <Alert tone="success" icon={<MailCheck className="h-4 w-4" />}>
          {sent}
        </Alert>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            request.mutate()
          }}
        >
          <Field label="Phone number" required hint="The number on your tenancy, e.g. 0712345678">
            <Input
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="+254712345678"
            />
          </Field>
          <Button
            type="submit"
            className="w-full"
            loading={request.isPending}
            disabled={phone.trim().length < 9}
          >
            Send me a sign-in link
          </Button>
        </form>
      )}

      <p className="mt-5 text-center text-sm text-slate-500">
        Know your password?{' '}
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Sign in with it instead
        </Link>
      </p>
    </AuthLayout>
  )
}
