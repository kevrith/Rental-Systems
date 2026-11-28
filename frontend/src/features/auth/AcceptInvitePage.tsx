import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'

import { portalApi, teamApi } from '@/api'
import { authApi } from '@/api/auth'
import { Alert, Button, Field, Input, PageLoader } from '@/components/ui'
import { errorMessage, humanize } from '@/lib/format'
import { PIN_LENGTH, PIN_RULE_MESSAGE, isAcceptablePin } from '@/lib/pin'
import { useAuthStore } from '@/store/auth-store'

import { AuthLayout } from './AuthLayout'

const schema = z
  .object({
    password: z.string().min(8, 'Use at least 8 characters').max(72, 'Password is too long'),
    confirm_password: z.string(),
  })
  .refine((values) => values.password === values.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })
type FormValues = z.infer<typeof schema>

/** Staff invitation: caretakers, managers and accountants set their own password. */
export function AcceptInvitePage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const token = params.get('token') ?? ''
  const [serverError, setServerError] = useState<string | null>(null)

  const preview = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => teamApi.previewInvitation(token),
    enabled: Boolean(token),
    retry: false,
  })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      teamApi.acceptInvitation({ token, password: values.password }),
    onSuccess: async (data) => {
      useAuthStore.getState().setTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      })
      setSession({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
        user: await authApi.me(),
      })
      navigate('/dashboard', { replace: true })
    },
    onError: (error) => setServerError(errorMessage(error, 'This invitation is no longer valid.')),
  })

  if (!token) {
    return <InvalidInvite message="This invitation link is missing its token." />
  }
  if (preview.isPending) {
    return (
      <AuthLayout title="Checking your invitation">
        <PageLoader />
      </AuthLayout>
    )
  }
  if (preview.isError) {
    return <InvalidInvite message={errorMessage(preview.error, 'This invitation is no longer valid.')} />
  }

  const invitation = preview.data

  // Caretakers sign in with a PIN on this phone, not a password.
  if (invitation.role === 'caretaker') {
    return <CaretakerPinInvite token={token} invitation={invitation} />
  }

  return (
    <AuthLayout
      title={`Welcome, ${invitation.full_name.split(' ')[0]}`}
      subtitle={`${invitation.organization_name} invited you to join as ${humanize(invitation.role).toLowerCase()}. Choose a password to get started.`}
    >
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
      >
        <Field label="Your phone number">
          <Input value={invitation.phone_number} disabled readOnly />
        </Field>

        <Field label="Create a password" required error={errors.password?.message}>
          <Input
            type="password"
            autoComplete="new-password"
            autoFocus
            invalid={Boolean(errors.password)}
            {...register('password')}
          />
        </Field>

        <Field label="Confirm password" required error={errors.confirm_password?.message}>
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
          Join {invitation.organization_name}
        </Button>
      </form>
    </AuthLayout>
  )
}

const pinSchema = z
  .object({
    pin: z.string().refine(isAcceptablePin, PIN_RULE_MESSAGE),
    confirm_pin: z.string(),
  })
  .refine((values) => values.pin === values.confirm_pin, {
    message: 'The two PINs do not match',
    path: ['confirm_pin'],
  })
type PinValues = z.infer<typeof pinSchema>

/**
 * A caretaker joins by choosing a PIN. It only works from this phone, which is
 * registered the moment they join; a new phone later needs a code from the
 * landlord.
 */
function CaretakerPinInvite({
  token,
  invitation,
}: {
  token: string
  invitation: { full_name: string; organization_name: string; phone_number: string }
}) {
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PinValues>({ resolver: zodResolver(pinSchema) })

  const mutation = useMutation({
    mutationFn: (values: PinValues) => teamApi.acceptInvitation({ token, pin: values.pin }),
    onSuccess: async (data) => {
      useAuthStore.getState().setTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      })
      setSession({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
        user: await authApi.me(),
      })
      navigate('/dashboard', { replace: true })
    },
    onError: (error) => setServerError(errorMessage(error, 'This invitation is no longer valid.')),
  })

  return (
    <AuthLayout
      title={`Welcome, ${invitation.full_name.split(' ')[0]}`}
      subtitle={`${invitation.organization_name} invited you to join as a caretaker. Choose a PIN to get started.`}
    >
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
      >
        <Field label="Your phone number">
          <Input value={invitation.phone_number} disabled readOnly />
        </Field>

        <Field
          label="Choose a 6-digit PIN"
          required
          hint="You will sign in on this phone with your phone number and this PIN. Keep it to yourself."
          error={errors.pin?.message}
        >
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="new-password"
            maxLength={PIN_LENGTH}
            autoFocus
            invalid={Boolean(errors.pin)}
            className="text-center text-lg tracking-[0.4em]"
            {...register('pin')}
          />
        </Field>

        <Field label="Confirm the PIN" required error={errors.confirm_pin?.message}>
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="new-password"
            maxLength={PIN_LENGTH}
            invalid={Boolean(errors.confirm_pin)}
            className="text-center text-lg tracking-[0.4em]"
            {...register('confirm_pin')}
          />
        </Field>

        <p className="text-xs text-slate-500">
          If you get a new phone or forget the PIN, your landlord sends you a code and you choose a
          new one. The old phone is signed out.
        </p>

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <Button type="submit" className="w-full justify-center" loading={mutation.isPending}>
          Join {invitation.organization_name}
        </Button>
      </form>
    </AuthLayout>
  )
}

/** Tenant portal invitation — the tenant already exists, this adds a login. */
export function PortalSetupPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const token = params.get('token') ?? ''
  const tenantId = params.get('t') ?? ''
  const [serverError, setServerError] = useState<string | null>(null)

  const preview = useQuery({
    queryKey: ['portal-invite', token, tenantId],
    queryFn: () => portalApi.previewSetup(token, tenantId),
    enabled: Boolean(token && tenantId),
    retry: false,
  })

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      portalApi.setup(tenantId, { token, password: values.password }),
    onSuccess: async (data) => {
      useAuthStore.getState().setTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      })
      setSession({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
        user: await authApi.me(),
      })
      navigate('/portal', { replace: true })
    },
    onError: (error) => setServerError(errorMessage(error, 'This link is no longer valid.')),
  })

  if (!token || !tenantId) {
    return <InvalidInvite message="This portal link is incomplete." />
  }
  if (preview.isPending) {
    return (
      <AuthLayout title="Setting up your portal">
        <PageLoader />
      </AuthLayout>
    )
  }
  if (preview.isError) {
    return <InvalidInvite message={errorMessage(preview.error, 'This link is no longer valid.')} />
  }

  return (
    <AuthLayout
      title={`Hi ${preview.data.full_name.split(' ')[0]}`}
      subtitle={`Set a password to access your ${preview.data.organization_name} tenant portal — pay rent, download receipts and raise requests.`}
    >
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
      >
        <Field label="Your phone number">
          <Input value={preview.data.phone_number} disabled readOnly />
        </Field>

        <Field label="Create a password" required error={errors.password?.message}>
          <Input
            type="password"
            autoComplete="new-password"
            autoFocus
            invalid={Boolean(errors.password)}
            {...register('password')}
          />
        </Field>

        <Field label="Confirm password" required error={errors.confirm_password?.message}>
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
          Open my portal
        </Button>
      </form>
    </AuthLayout>
  )
}

function InvalidInvite({ message }: { message: string }) {
  return (
    <AuthLayout title="Invitation not valid">
      <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
        {message}
      </Alert>
      <Link
        to="/login"
        className="mt-5 block text-center text-sm font-medium text-brand-600 hover:underline"
      >
        Go to log in
      </Link>
    </AuthLayout>
  )
}
