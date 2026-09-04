import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, MailCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

import { authApi } from '@/api/auth'
import { Alert, Button, Field, Input, Spinner } from '@/components/ui'
import { errorMessage } from '@/lib/format'

import { AuthLayout } from './AuthLayout'

// ------------------------------------------------------------- forgot password

const forgotSchema = z.object({ email: z.string().email('Enter a valid email address') })

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof forgotSchema>>({ resolver: zodResolver(forgotSchema) })

  const mutation = useMutation({
    mutationFn: (values: z.infer<typeof forgotSchema>) => authApi.forgotPassword(values.email),
    onSuccess: () => setSent(true),
    // The endpoint never reveals whether the account exists, so a failure here
    // is a network problem — show the same confirmation either way.
    onError: () => setSent(true),
  })

  if (sent) {
    return (
      <AuthLayout
        title="Check your messages"
        subtitle="If that account exists, a reset link is on its way by SMS and email."
      >
        <Alert tone="success" icon={<MailCheck className="h-4 w-4" />}>
          The link expires in 2 hours. If it doesn&apos;t arrive, check the number and try again.
        </Alert>
        <Link
          to="/login"
          className="mt-5 block text-center text-sm font-medium text-brand-600 hover:underline"
        >
          Back to log in
        </Link>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll send a link to the phone and email on your account."
      footer={
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Back to log in
        </Link>
      }
    >
      <form className="space-y-4" onSubmit={handleSubmit((values) => mutation.mutate(values))}>
        <Field label="Email" error={errors.email?.message}>
          <Input
            type="email"
            autoComplete="email"
            placeholder="jane@example.com"
            invalid={Boolean(errors.email)}
            {...register('email')}
          />
        </Field>
        <Button type="submit" className="w-full justify-center" loading={mutation.isPending}>
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  )
}

// -------------------------------------------------------------- reset password

const resetSchema = z
  .object({
    new_password: z.string().min(8, 'Use at least 8 characters').max(72, 'Password is too long'),
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') ?? ''
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) })

  const mutation = useMutation({
    mutationFn: (values: z.infer<typeof resetSchema>) =>
      authApi.resetPassword({ token, new_password: values.new_password }),
    onSuccess: () => navigate('/login?reset=1', { replace: true }),
    onError: (error) => setServerError(errorMessage(error, 'This link is invalid or has expired.')),
  })

  if (!token) {
    return (
      <AuthLayout title="Link not valid" subtitle="This password reset link is missing its token.">
        <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
          Request a new link from the login page.
        </Alert>
        <Link
          to="/forgot-password"
          className="mt-5 block text-center text-sm font-medium text-brand-600 hover:underline"
        >
          Request a new link
        </Link>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="You'll be signed out everywhere else.">
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
      >
        <Field label="New password" error={errors.new_password?.message}>
          <Input
            type="password"
            autoComplete="new-password"
            invalid={Boolean(errors.new_password)}
            {...register('new_password')}
          />
        </Field>
        <Field label="Confirm new password" error={errors.confirm_password?.message}>
          <Input
            type="password"
            autoComplete="new-password"
            invalid={Boolean(errors.confirm_password)}
            {...register('confirm_password')}
          />
        </Field>

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <Button type="submit" className="w-full justify-center" loading={mutation.isPending}>
          Set new password
        </Button>
      </form>
    </AuthLayout>
  )
}

// -------------------------------------------------------------- verify email

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [state, setState] = useState<'verifying' | 'done' | 'error'>('verifying')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setState('error')
      setMessage('This verification link is missing its token.')
      return
    }
    authApi
      .verifyEmail(token)
      .then(() => setState('done'))
      .catch((error) => {
        setState('error')
        setMessage(errorMessage(error, 'This link is invalid or has already been used.'))
      })
  }, [token])

  return (
    <AuthLayout
      title={
        state === 'verifying'
          ? 'Verifying your email'
          : state === 'done'
            ? 'Email verified'
            : 'Verification failed'
      }
      subtitle={state === 'done' ? 'Your account is fully set up.' : undefined}
      footer={
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Continue to log in
        </Link>
      }
    >
      {state === 'verifying' && (
        <div className="flex justify-center py-4">
          <Spinner className="h-6 w-6" />
        </div>
      )}
      {state === 'done' && (
        <Alert tone="success" icon={<CheckCircle2 className="h-4 w-4" />}>
          Thanks — your email address is confirmed.
        </Alert>
      )}
      {state === 'error' && (
        <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
          {message}
        </Alert>
      )}
    </AuthLayout>
  )
}
