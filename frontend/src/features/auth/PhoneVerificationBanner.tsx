import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { authApi } from '@/api/auth'
import { Button, Input } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { useAuthStore } from '@/store/auth-store'

const schema = z.object({
  otp_code: z.string().regex(/^\d{4,8}$/, 'Enter the code from your SMS'),
})
type FormValues = z.infer<typeof schema>

/** Prompt shown until the owner confirms the number their codes and receipts go to. */
export function PhoneVerificationBanner() {
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const [resent, setResent] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const { register, handleSubmit, formState } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const verify = useMutation({
    mutationFn: (values: FormValues) => authApi.verifyPhone(values.otp_code),
    onSuccess: (updated) => {
      setServerError(null)
      setUser(updated)
    },
    onError: (error) => setServerError(errorMessage(error, 'Invalid or expired code.')),
  })

  const resend = useMutation({
    mutationFn: authApi.resendPhoneVerification,
    onSuccess: () => setResent(true),
  })

  if (!user || user.is_phone_verified) return null

  return (
    <div className="mb-6 rounded-card border border-warn-100 bg-warn-50 p-4">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-warn-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-warn-700">Verify your phone number</p>
          <p className="mt-0.5 text-sm text-warn-700/80">
            We sent a code to {user.phone_number}. Login codes, receipts and alerts all go to this
            number.
          </p>

          <form
            className="mt-3 flex flex-wrap items-start gap-2"
            onSubmit={handleSubmit((values) => {
              setServerError(null)
              verify.mutate(values)
            })}
          >
            <div>
              <Input
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                placeholder="123456"
                className="w-32"
                invalid={Boolean(formState.errors.otp_code)}
                {...register('otp_code')}
              />
              {formState.errors.otp_code && (
                <p className="mt-1 text-xs text-danger-600">{formState.errors.otp_code.message}</p>
              )}
            </div>

            <Button type="submit" size="md" loading={verify.isPending}>
              Verify
            </Button>

            <Button
              type="button"
              variant="ghost"
              onClick={() => resend.mutate()}
              loading={resend.isPending}
            >
              {resent ? 'Code resent' : 'Resend code'}
            </Button>
          </form>

          {serverError && <p className="mt-2 text-sm text-danger-700">{serverError}</p>}
        </div>
      </div>
    </div>
  )
}
