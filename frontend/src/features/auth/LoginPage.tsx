import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle, Fingerprint, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { authApi, type TokenResponse } from '@/api/auth'
import { Alert, Button, Field, Input } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { GOOGLE_CLIENT_ID } from '@/lib/google-identity'
import { getPasskeyAssertion, isWebauthnSupported } from '@/lib/webauthn'
import { useAuthStore } from '@/store/auth-store'

import { AuthLayout } from './AuthLayout'
import { GoogleSignIn } from './GoogleSignIn'

const credentialsSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
  remember_device: z.boolean(),
})
type CredentialsValues = z.infer<typeof credentialsSchema>

const otpSchema = z.object({
  otp_code: z.string().regex(/^\d{4,8}$/, 'Enter the code from your SMS'),
})
type OtpValues = z.infer<typeof otpSchema>

export function LoginPage() {
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const [serverError, setServerError] = useState<string | null>(null)
  const [challenge, setChallenge] = useState<{
    token: string
    message: string
    webauthnOptions: string | null
  } | null>(null)
  const [rememberDevice, setRememberDevice] = useState(false)
  const [passkeyPending, setPasskeyPending] = useState(false)

  const credentialsForm = useForm<CredentialsValues>({
    resolver: zodResolver(credentialsSchema),
    defaultValues: { remember_device: false },
  })
  const otpForm = useForm<OtpValues>({ resolver: zodResolver(otpSchema) })

  /** Store tokens, load the profile, then land on the right home screen. */
  const finishLogin = async (tokens: TokenResponse) => {
    useAuthStore.getState().setTokens({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    })
    const user = await authApi.me()
    setSession({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      user,
    })
    navigate(user.role === 'tenant' ? '/portal' : '/dashboard', { replace: true })
  }

  const credentialsMutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: async (data) => {
      setServerError(null)
      // A trusted device skips the OTP and comes back with tokens directly.
      if (!data.otp_required && data.tokens) {
        await finishLogin(data.tokens)
        return
      }
      if (data.challenge_token) {
        setChallenge({
          token: data.challenge_token,
          message: data.message,
          webauthnOptions: data.webauthn_options,
        })
      }
    },
    onError: (error) => setServerError(errorMessage(error, 'Invalid email or password.')),
  })

  const otpMutation = useMutation({
    mutationFn: async (values: OtpValues) => {
      if (!challenge) throw new Error('No active login challenge')
      return authApi.verifyLoginOtp({
        challenge_token: challenge.token,
        otp_code: values.otp_code,
        remember_device: rememberDevice,
      })
    },
    onSuccess: finishLogin,
    onError: (error) => setServerError(errorMessage(error, 'Invalid or expired code.')),
  })

  // Matches the backend's own 30-second cooldown between resends (it enforces
  // this regardless — the countdown here just avoids sending a request that
  // is only going to come back 429).
  const [resendCooldown, setResendCooldown] = useState(0)
  useEffect(() => {
    if (resendCooldown <= 0) return
    const timer = setInterval(() => setResendCooldown((seconds) => Math.max(0, seconds - 1)), 1000)
    return () => clearInterval(timer)
  }, [resendCooldown])

  const resendMutation = useMutation({
    mutationFn: async () => {
      if (!challenge) throw new Error('No active login challenge')
      return authApi.resendLoginOtp(challenge.token)
    },
    onSuccess: () => {
      setServerError(null)
      setResendCooldown(30)
    },
    onError: (error) => setServerError(errorMessage(error, 'Could not resend the code.')),
  })

  const signInWithPasskey = async () => {
    if (!challenge?.webauthnOptions) return
    setServerError(null)
    setPasskeyPending(true)
    try {
      const assertion = await getPasskeyAssertion(challenge.webauthnOptions)
      const tokens = await authApi.verifyLoginWebauthn({
        challenge_token: challenge.token,
        credential: assertion,
        remember_device: rememberDevice,
      })
      await finishLogin(tokens)
    } catch (error) {
      setServerError(errorMessage(error, 'Passkey sign-in failed. Use your SMS code instead.'))
    } finally {
      setPasskeyPending(false)
    }
  }

  if (challenge) {
    return (
      <AuthLayout title="Enter your login code" subtitle={challenge.message}>
        <form
          className="space-y-4"
          onSubmit={otpForm.handleSubmit((values) => {
            setServerError(null)
            otpMutation.mutate(values)
          })}
        >
          <Field label="Verification code" error={otpForm.formState.errors.otp_code?.message}>
            <Input
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              maxLength={8}
              placeholder="123456"
              className="text-center text-lg tracking-[0.4em]"
              invalid={Boolean(otpForm.formState.errors.otp_code)}
              {...otpForm.register('otp_code')}
            />
          </Field>

          <label className="flex items-start gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={rememberDevice}
              onChange={(event) => setRememberDevice(event.target.checked)}
              className="mt-0.5 h-4 w-4 accent-brand-600"
            />
            <span>
              Remember this device for 30 days
              <span className="block text-xs text-slate-400">
                Skips the SMS code next time you log in from this browser.
              </span>
            </span>
          </label>

          {serverError && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              {serverError}
            </Alert>
          )}

          <Button type="submit" className="w-full justify-center" loading={otpMutation.isPending}>
            Verify and log in
          </Button>

          {challenge.webauthnOptions && isWebauthnSupported() && (
            <button
              type="button"
              onClick={() => void signInWithPasskey()}
              disabled={passkeyPending}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              <Fingerprint className="h-4 w-4" />
              {passkeyPending ? 'Waiting for your passkey…' : 'Use your passkey instead'}
            </button>
          )}

          <button
            type="button"
            onClick={() => resendMutation.mutate()}
            disabled={resendCooldown > 0 || resendMutation.isPending}
            className="w-full text-center text-sm text-brand-600 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
          >
            {resendCooldown > 0
              ? `Resend code in ${resendCooldown}s`
              : resendMutation.isPending
                ? 'Sending…'
                : 'Resend code'}
          </button>

          <button
            type="button"
            onClick={() => {
              setServerError(null)
              setChallenge(null)
            }}
            className="w-full text-center text-sm text-slate-500 hover:underline"
          >
            Use a different account
          </button>
        </form>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Log in to RentFlow"
      subtitle="Manage every rental. Empower every owner."
      footer={
        <>
          Don&apos;t have an account?{' '}
          <Link to="/register" className="font-medium text-brand-600 hover:underline">
            Start your free trial
          </Link>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={credentialsForm.handleSubmit((values) => {
          setServerError(null)
          setRememberDevice(values.remember_device)
          credentialsMutation.mutate(values)
        })}
      >
        <Field label="Email" error={credentialsForm.formState.errors.email?.message}>
          <Input
            type="email"
            autoComplete="email"
            placeholder="jane@example.com"
            invalid={Boolean(credentialsForm.formState.errors.email)}
            {...credentialsForm.register('email')}
          />
        </Field>

        <Field label="Password" error={credentialsForm.formState.errors.password?.message}>
          <Input
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            invalid={Boolean(credentialsForm.formState.errors.password)}
            {...credentialsForm.register('password')}
          />
        </Field>

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand-600"
              {...credentialsForm.register('remember_device')}
            />
            Remember this device
          </label>
          <Link to="/forgot-password" className="text-sm text-brand-600 hover:underline">
            Forgot password?
          </Link>
        </div>

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <Button type="submit" className="w-full justify-center" loading={credentialsMutation.isPending}>
          Log in
        </Button>

        <p className="flex items-center justify-center gap-1.5 text-xs text-slate-500">
          <ShieldCheck className="h-3.5 w-3.5" />
          Protected by two-factor authentication
        </p>
      </form>

      {GOOGLE_CLIENT_ID && (
        <>
          <div className="my-4 flex items-center gap-3 text-xs text-slate-400">
            <span className="h-px flex-1 bg-slate-200" />
            or
            <span className="h-px flex-1 bg-slate-200" />
          </div>
          <GoogleSignIn onSuccess={finishLogin} />
        </>
      )}

      {/*
        Tenants sign in perhaps twice a year, often on a borrowed phone, and
        most have no email address on file — so the reset flow above is not a
        route back in for them. The link sign-in is (Sprint 26).
      */}
      <p className="mt-4 text-center text-sm text-slate-500">
        Are you a tenant?{' '}
        <Link to="/portal/login" className="font-medium text-brand-600 hover:underline">
          Get a sign-in link
        </Link>
      </p>
    </AuthLayout>
  )
}
