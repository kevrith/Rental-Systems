import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle, Building2, User } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { authApi } from '@/api/auth'
import { Alert, Button, Field, Input } from '@/components/ui'
import { cn } from '@/lib/cn'
import { errorMessage } from '@/lib/format'
import { useAuthStore } from '@/store/auth-store'

import { AuthLayout } from './AuthLayout'

const schema = z.object({
  full_name: z.string().min(2, 'Enter your full name'),
  organization_name: z.string().min(2, 'Enter your organization name'),
  email: z.string().email('Enter a valid email address'),
  phone_number: z
    .string()
    .regex(/^(\+?254|0)?[17]\d{8}$/, 'Enter a Kenyan mobile number, e.g. 0712345678'),
  password: z.string().min(8, 'Use at least 8 characters').max(72, 'Password is too long'),
  account_type: z.enum(['owner', 'agency']),
})
type FormValues = z.infer<typeof schema>

export function RegisterPage() {
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { account_type: 'owner' },
  })

  const accountType = watch('account_type')

  const mutation = useMutation({
    mutationFn: authApi.register,
    onSuccess: async (data) => {
      setSession({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
        user: data.user,
        organization: data.organization,
      })
      // The register response predates the permission list, so fetch the full
      // profile before routing — navigation depends on it.
      try {
        setSession({
          accessToken: data.tokens.access_token,
          refreshToken: data.tokens.refresh_token,
          user: await authApi.me(),
          organization: data.organization,
        })
      } catch {
        // Non-fatal: the dashboard will refetch the profile itself.
      }
      navigate('/dashboard', { replace: true })
    },
    onError: (error) => setServerError(errorMessage(error, 'Registration failed. Please try again.')),
  })

  return (
    <AuthLayout
      title="Create your RentFlow account"
      subtitle="Start your 30-day free trial. No card required."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-brand-600 hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          mutation.mutate(values)
        })}
      >
        <Field label="I manage">
          <div className="grid grid-cols-2 gap-3">
            <AccountTypeOption
              icon={<User className="h-4 w-4" />}
              label="My own properties"
              selected={accountType === 'owner'}
              onSelect={() => setValue('account_type', 'owner')}
            />
            <AccountTypeOption
              icon={<Building2 className="h-4 w-4" />}
              label="Properties for others"
              selected={accountType === 'agency'}
              onSelect={() => setValue('account_type', 'agency')}
            />
          </div>
          <input type="hidden" {...register('account_type')} />
        </Field>

        <Field label="Full name" required error={errors.full_name?.message}>
          <Input
            autoComplete="name"
            placeholder="Jane Wanjiru"
            invalid={Boolean(errors.full_name)}
            {...register('full_name')}
          />
        </Field>

        <Field
          label={accountType === 'agency' ? 'Agency name' : 'Business or portfolio name'}
          required
          error={errors.organization_name?.message}
        >
          <Input
            autoComplete="organization"
            placeholder={accountType === 'agency' ? 'Acacia Property Management' : 'Wanjiru Rentals'}
            invalid={Boolean(errors.organization_name)}
            {...register('organization_name')}
          />
        </Field>

        <Field label="Email" required error={errors.email?.message}>
          <Input
            type="email"
            autoComplete="email"
            placeholder="jane@example.com"
            invalid={Boolean(errors.email)}
            {...register('email')}
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

        <Field
          label="Password"
          required
          error={errors.password?.message}
          hint="At least 8 characters."
        >
          <Input
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            invalid={Boolean(errors.password)}
            {...register('password')}
          />
        </Field>

        {serverError && (
          <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
            {serverError}
          </Alert>
        )}

        <Button type="submit" className="w-full justify-center" loading={mutation.isPending}>
          Start free trial
        </Button>
      </form>
    </AuthLayout>
  )
}

function AccountTypeOption({
  icon,
  label,
  selected,
  onSelect,
}: {
  icon: React.ReactNode
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'flex flex-col items-start gap-1.5 rounded-lg border p-3 text-left text-sm transition-colors',
        selected
          ? 'border-brand-600 bg-brand-50 text-brand-800'
          : 'border-slate-300 text-slate-600 hover:bg-slate-50',
      )}
    >
      <span className={cn(selected ? 'text-brand-600' : 'text-slate-400')}>{icon}</span>
      {label}
    </button>
  )
}
