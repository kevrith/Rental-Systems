import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { authApi, type TokenResponse } from '@/api/auth'
import { Alert, Button, Field, Input, Select } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { GOOGLE_CLIENT_ID, renderGoogleButton } from '@/lib/google-identity'

const completeSchema = z.object({
  organization_name: z.string().min(2, 'Enter your organization name'),
  phone_number: z
    .string()
    .regex(/^(\+?254|0)?[17]\d{8}$/, 'Enter a Kenyan mobile number, e.g. 0712345678'),
  account_type: z.enum(['owner', 'agency']),
})
type CompleteValues = z.infer<typeof completeSchema>

/**
 * Drop-in "Sign in with Google" button, used on both the login and register
 * screens. An unrecognized Google account (no existing user matches it)
 * expands into a short follow-up form for the org/phone details Google can't
 * supply, then completes registration with the same credential — the button
 * itself doesn't care which page it's on.
 */
export function GoogleSignIn({ onSuccess }: { onSuccess: (tokens: TokenResponse) => void }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const credentialRef = useRef<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [pending, setPending] = useState<{ email: string; fullName: string } | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CompleteValues>({
    resolver: zodResolver(completeSchema),
    defaultValues: { account_type: 'owner' },
  })

  const authMutation = useMutation({
    mutationFn: authApi.googleAuth,
    onSuccess: (data) => {
      setServerError(null)
      if (data.status === 'signed_in' && data.tokens) {
        onSuccess(data.tokens)
        return
      }
      setPending({ email: data.email ?? '', fullName: data.full_name ?? '' })
    },
    onError: (error) => setServerError(errorMessage(error, 'Google sign-in failed. Please try again.')),
  })

  const registerMutation = useMutation({
    mutationFn: authApi.googleRegister,
    onSuccess: (data) => onSuccess(data.tokens),
    onError: (error) =>
      setServerError(errorMessage(error, "Couldn't finish setting up your account. Please try again.")),
  })

  useEffect(() => {
    if (!containerRef.current) return
    let cancelled = false
    void renderGoogleButton(containerRef.current, (credential) => {
      if (cancelled) return
      credentialRef.current = credential
      setServerError(null)
      authMutation.mutate(credential)
    })
    return () => {
      cancelled = true
    }
    // Google's callback is registered once against this container; re-running
    // it on every render would just re-initialize the same button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!GOOGLE_CLIENT_ID) return null

  if (pending) {
    return (
      <div className="w-full space-y-4 rounded-lg border border-slate-200 p-4 dark:border-slate-700">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Almost there{pending.fullName ? `, ${pending.fullName.split(' ')[0]}` : ''} — a couple more
          details to set up your account.
        </p>
        <form
          className="space-y-4"
          onSubmit={handleSubmit((values) => {
            if (!credentialRef.current) return
            setServerError(null)
            registerMutation.mutate({ credential: credentialRef.current, ...values })
          })}
        >
          <Field label="Business or portfolio name" required error={errors.organization_name?.message}>
            <Input
              autoComplete="organization"
              placeholder="Wanjiru Rentals"
              invalid={Boolean(errors.organization_name)}
              {...register('organization_name')}
            />
          </Field>

          <Field
            label="Phone number"
            required
            error={errors.phone_number?.message}
            hint="We send your login codes and receipts here."
          >
            <Input
              type="tel"
              autoComplete="tel"
              placeholder="0712 345 678"
              invalid={Boolean(errors.phone_number)}
              {...register('phone_number')}
            />
          </Field>

          <Field label="I manage" required>
            <Select {...register('account_type')}>
              <option value="owner">My own properties</option>
              <option value="agency">Properties for others</option>
            </Select>
          </Field>

          {serverError && (
            <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
              {serverError}
            </Alert>
          )}

          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={() => setPending(null)}>
              Cancel
            </Button>
            <Button type="submit" className="flex-1 justify-center" loading={registerMutation.isPending}>
              Finish setup
            </Button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <div className="w-full space-y-2">
      <div ref={containerRef} className="flex w-full justify-center" />
      {serverError && (
        <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
          {serverError}
        </Alert>
      )}
    </div>
  )
}
