import { useMutation } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { authApi } from '@/api/auth'
import type { TokenResponse } from '@/api/auth'
import { Alert, Button, Field, Input } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { PIN_LENGTH, PIN_RULE_MESSAGE, isAcceptablePin } from '@/lib/pin'
import { useAuthStore } from '@/store/auth-store'

import { AuthLayout } from './AuthLayout'

const PHONE_KEY = 'rentflow-pin-phone'

// Remembering the number saves a caretaker typing it on every shift. Storage
// can be blocked (private mode), so every access is guarded.
function savedPhone(): string {
  try {
    return localStorage.getItem(PHONE_KEY) ?? ''
  } catch {
    return ''
  }
}

function rememberPhone(phone: string) {
  try {
    localStorage.setItem(PHONE_KEY, phone)
  } catch {
    // Not remembering the number is only an inconvenience.
  }
}

/**
 * Caretaker sign-in: phone number and a 6-digit PIN, from the phone they
 * registered. A new phone, or a forgotten PIN, starts with a one-time code the
 * landlord or another caretaker hands over — the second form on this page.
 */
export function PinLoginPage() {
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const [mode, setMode] = useState<'signin' | 'enroll'>('signin')
  const [phone, setPhone] = useState(savedPhone)
  const [pin, setPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)

  const open = async (tokens: TokenResponse) => {
    useAuthStore.getState().setTokens({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    })
    setSession({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      user: await authApi.me(),
    })
    rememberPhone(phone.trim())
    navigate('/dashboard', { replace: true })
  }

  const signIn = useMutation({
    mutationFn: () => authApi.pinLogin({ phone_number: phone.trim(), pin }),
    onSuccess: open,
    onError: (failure) => setError(pinFailureMessage(failure)),
  })

  const enroll = useMutation({
    mutationFn: () => authApi.pinEnroll({ phone_number: phone.trim(), code: code.trim(), pin }),
    onSuccess: open,
    onError: (failure) => setError(errorMessage(failure, 'That code did not work.')),
  })

  const switchMode = (next: 'signin' | 'enroll') => {
    setMode(next)
    setError(null)
    setPin('')
    setConfirmPin('')
    setCode('')
  }

  const enrolling = mode === 'enroll'
  const pinProblem =
    enrolling && pin.length === PIN_LENGTH && !isAcceptablePin(pin) ? PIN_RULE_MESSAGE : undefined
  const mismatch =
    enrolling && confirmPin.length === PIN_LENGTH && confirmPin !== pin
      ? 'The two PINs do not match'
      : undefined

  const ready = enrolling
    ? phone.trim().length >= 9 &&
      /^\d{4,8}$/.test(code.trim()) &&
      isAcceptablePin(pin) &&
      pin === confirmPin
    : phone.trim().length >= 9 && /^\d{6}$/.test(pin)

  return (
    <AuthLayout
      title={enrolling ? 'New phone or forgot your PIN?' : 'Caretaker sign-in'}
      subtitle={
        enrolling
          ? 'Ask your landlord or caretaker for a sign-in code. Enter it here and choose a new PIN. This phone becomes your phone and any other is signed out.'
          : 'Sign in with your phone number and PIN.'
      }
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          setError(null)
          if (enrolling) enroll.mutate()
          else signIn.mutate()
        }}
      >
        <Field label="Phone number" required>
          <Input
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="0712345678"
          />
        </Field>

        {enrolling && (
          <Field label="Sign-in code" required hint="The code your landlord sent you">
            <Input
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={8}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="text-center text-lg tracking-[0.4em]"
              placeholder="123456"
            />
          </Field>
        )}

        <Field
          label={enrolling ? 'Choose a new PIN' : 'PIN'}
          required
          error={pinProblem}
          hint={enrolling ? 'Six digits, and not an obvious one' : undefined}
        >
          <Input
            type="password"
            inputMode="numeric"
            autoComplete={enrolling ? 'new-password' : 'current-password'}
            maxLength={PIN_LENGTH}
            value={pin}
            onChange={(event) => setPin(event.target.value.replace(/\D/g, ''))}
            invalid={Boolean(pinProblem)}
            className="text-center text-lg tracking-[0.4em]"
            autoFocus={!enrolling && phone.trim().length >= 9}
          />
        </Field>

        {enrolling && (
          <Field label="Confirm the PIN" required error={mismatch}>
            <Input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              maxLength={PIN_LENGTH}
              value={confirmPin}
              onChange={(event) => setConfirmPin(event.target.value.replace(/\D/g, ''))}
              invalid={Boolean(mismatch)}
              className="text-center text-lg tracking-[0.4em]"
            />
          </Field>
        )}

        {error && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {error}
          </Alert>
        )}

        <Button
          type="submit"
          className="w-full justify-center"
          loading={signIn.isPending || enroll.isPending}
          disabled={!ready}
        >
          {enrolling ? 'Set my PIN and sign in' : 'Sign in'}
        </Button>
      </form>

      <div className="mt-5 space-y-2 text-center text-sm text-slate-500">
        <button
          type="button"
          onClick={() => switchMode(enrolling ? 'signin' : 'enroll')}
          className="font-medium text-brand-600 hover:underline"
        >
          {enrolling ? 'Back to PIN sign-in' : 'New phone or forgot your PIN?'}
        </button>
        <p>
          <Link to="/login" className="hover:underline">
            Sign in with email and password instead
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}

/** A locked phone comes back as a structured 403; everything else is a plain message. */
function pinFailureMessage(failure: unknown): string {
  const detail = (failure as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return errorMessage(failure, 'That did not work. Check your phone number and PIN.')
}
