import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { authApi, type TokenResponse } from '@/api/auth'
import { Alert, Button, Field, Input } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { useAuthStore } from '@/store/auth-store'

import { AuthLayout } from './AuthLayout'

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
  const [challenge, setChallenge] = useState<{ token: string; message: string } | null>(null)
  const [rememberDevice, setRememberDevice] = useState(false)

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
        setChallenge({ token: data.challenge_token, message: data.message })
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

        <p className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <ShieldCheck className="h-3.5 w-3.5" />
          Protected by two-factor authentication
        </p>
      </form>
    </AuthLayout>
  )
}
