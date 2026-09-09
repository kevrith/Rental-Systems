import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Bell,
  Building2,
  CreditCard,
  Download,
  Fingerprint,
  Laptop,
  LogOut,
  Plug,
  Plus,
  MessageSquare,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Trash2,
  UserRound,
  Receipt,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { notificationsApi, organizationApi, securityApi } from '@/api'
import { authApi } from '@/api/auth'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  Field,
  Input,
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { dateTime, errorMessage, humanize, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { createPasskey, isWebauthnSupported } from '@/lib/webauthn'
import { useAuthStore } from '@/store/auth-store'

const SECURITY_POLICY_ROLES: { value: string; label: string }[] = [
  { value: 'owner', label: 'Owner' },
  { value: 'agency_admin', label: 'Agency admin' },
  { value: 'property_manager', label: 'Property manager' },
  { value: 'caretaker', label: 'Caretaker' },
  { value: 'accountant', label: 'Accountant' },
  { value: 'owner_portal_user', label: 'Owner portal' },
]

const TABS = [
  { to: '/settings/profile', label: 'Profile', icon: <UserRound className="h-4 w-4" /> },
  { to: '/settings/security', label: 'Security', icon: <ShieldCheck className="h-4 w-4" /> },
  { to: '/settings/sessions', label: 'Devices', icon: <Laptop className="h-4 w-4" /> },
  { to: '/settings/notifications', label: 'Notifications', icon: <Bell className="h-4 w-4" /> },
  { to: '/settings/organization', label: 'Organization', icon: <Building2 className="h-4 w-4" /> },
  { to: '/settings/mpesa', label: 'M-Pesa', icon: <Smartphone className="h-4 w-4" /> },
  { to: '/settings/billing', label: 'Billing', icon: <CreditCard className="h-4 w-4" /> },
  { to: '/settings/messages', label: 'Message wording', icon: <MessageSquare className="h-4 w-4" /> },
  { to: '/settings/etims', label: 'KRA eTIMS', icon: <Receipt className="h-4 w-4" /> },
  { to: '/settings/portals', label: 'Property portals', icon: <Plug className="h-4 w-4" /> },
  { to: '/settings/accounting', label: 'Accounting', icon: <Plug className="h-4 w-4" /> },
]

export function SettingsLayout() {
  return (
    <div>
      <PageHeader title="Settings" />
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                '-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium',
                isActive
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700',
              )
            }
          >
            {tab.icon}
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div className="max-w-2xl">
        <Outlet />
      </div>
    </div>
  )
}

// --------------------------------------------------------------------- profile

export function ProfileSettings() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)

  useEffect(() => {
    if (user) {
      setFullName(user.full_name)
      setPhone(user.phone_number)
    }
  }, [user])

  const save = useMutation({
    mutationFn: () =>
      authApi.updateProfile({
        full_name: fullName,
        phone_number: phone !== user?.phone_number ? phone : undefined,
      }),
    onSuccess: async (updated) => {
      useAuthStore.getState().setUser(updated)
      await queryClient.invalidateQueries({ queryKey: queryKeys.me })
      setNotice({
        tone: 'success',
        text: updated.is_phone_verified
          ? 'Profile updated.'
          : 'Profile updated. We sent a verification code to your new number.',
      })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const requestDeletion = useMutation({
    mutationFn: authApi.requestDeletion,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.me })
      setDeleteOpen(false)
      setNotice({ tone: 'success', text: result.message })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const cancelDeletion = useMutation({
    mutationFn: authApi.cancelDeletion,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.me })
      setNotice({ tone: 'success', text: result.message })
    },
  })

  const exportData = useMutation({
    mutationFn: authApi.exportOwnData,
    onSuccess: (result) => {
      if (result.download_url) window.open(result.download_url, '_blank', 'noopener')
      setNotice({ tone: 'success', text: 'Your data export is ready.' })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  if (!user) return <PageLoader />

  return (
    <div className="space-y-5">
      {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

      {user.deletion_requested_at && (
        <Alert
          tone="danger"
          icon={<AlertTriangle className="h-4 w-4" />}
          title="Deletion scheduled"
        >
          Your account is scheduled for deletion. It stays recoverable until then.
          <div className="mt-2">
            <Button size="sm" variant="secondary" onClick={() => cancelDeletion.mutate()}>
              Cancel deletion
            </Button>
          </div>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Your details</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <Field label="Full name">
            <Input value={fullName} onChange={(event) => setFullName(event.target.value)} />
          </Field>

          <Field
            label="Phone number"
            hint="Changing this needs a fresh SMS verification."
          >
            <div className="flex items-center gap-2">
              <Input value={phone} onChange={(event) => setPhone(event.target.value)} />
              {user.is_phone_verified ? (
                <Badge tone="success">Verified</Badge>
              ) : (
                <Badge tone="warn">Unverified</Badge>
              )}
            </div>
          </Field>

          <Field label="Email">
            <div className="flex items-center gap-2">
              <Input value={user.email} disabled readOnly />
              {user.is_email_verified ? (
                <Badge tone="success">Verified</Badge>
              ) : (
                <Badge tone="warn">Unverified</Badge>
              )}
            </div>
          </Field>

          <Field label="Role">
            <Input value={humanize(user.role)} disabled readOnly />
          </Field>

          <Button loading={save.isPending} onClick={() => save.mutate()}>
            Save changes
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your data</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="mb-3 text-sm text-slate-600">
            Download a copy of your profile, sessions and recent activity (Kenya Data Protection
            Act, US-106).
          </p>
          <Button
            variant="outline"
            icon={<Download className="h-4 w-4" />}
            loading={exportData.isPending}
            onClick={() => exportData.mutate()}
          >
            Download my data
          </Button>
        </CardBody>
      </Card>

      {!user.deletion_requested_at && (
        <Card>
          <CardHeader>
            <CardTitle className="text-danger-700">Danger zone</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="mb-3 text-sm text-slate-600">
              Deleting your account starts a 30-day grace period. You can cancel any time before it
              elapses.
            </p>
            <Button
              variant="ghost"
              className="text-danger-600"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => setDeleteOpen(true)}
            >
              Request account deletion
            </Button>
          </CardBody>
        </Card>
      )}

      <Dialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete your account?"
        description="This starts a 30-day grace period."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              Keep my account
            </Button>
            <Button
              variant="danger"
              loading={requestDeletion.isPending}
              onClick={() => requestDeletion.mutate()}
            >
              Request deletion
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          Nothing is destroyed today. Log in and cancel before the 30 days are up and everything
          continues as normal. After that, your personal details are removed — financial records are
          retained as the law requires.
        </p>
      </Dialog>
    </div>
  )
}

// -------------------------------------------------------------------- security

export function SecuritySettings() {
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const changePassword = useMutation({
    mutationFn: () => authApi.changePassword({ current_password: current, new_password: next }),
    onSuccess: (result) => {
      setCurrent('')
      setNext('')
      setConfirm('')
      setNotice({ tone: 'success', text: result.message })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const savePreferences = useMutation({
    mutationFn: (payload: Record<string, unknown>) => authApi.updateProfile(payload),
    onSuccess: async (updated) => {
      useAuthStore.getState().setUser(updated)
      await queryClient.invalidateQueries({ queryKey: queryKeys.me })
      setNotice({ tone: 'success', text: 'Security preferences saved.' })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const mismatch = confirm.length > 0 && next !== confirm

  return (
    <div className="space-y-5">
      {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <Field label="Current password" required>
            <Input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
            />
          </Field>
          <Field label="New password" required hint="At least 8 characters.">
            <Input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
          </Field>
          <Field
            label="Confirm new password"
            required
            error={mismatch ? 'Passwords do not match' : undefined}
          >
            <Input
              type="password"
              autoComplete="new-password"
              invalid={mismatch}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </Field>

          <Alert tone="info">
            Changing your password signs you out on every other device.
          </Alert>

          <Button
            disabled={!current || next.length < 8 || mismatch}
            loading={changePassword.isPending}
            onClick={() => changePassword.mutate()}
          >
            Change password
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Two-factor authentication</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-brand-600"
              checked={user?.always_require_2fa ?? false}
              onChange={(event) =>
                savePreferences.mutate({ always_require_2fa: event.target.checked })
              }
            />
            <span>
              Always ask for an SMS code
              <span className="block text-xs text-slate-500">
                Even on devices you have marked as trusted.
              </span>
            </span>
          </label>

          <Field
            label="Auto-logout after inactivity"
            hint="Your session ends after this long with no activity."
          >
            <Select
              value={String(user?.inactivity_timeout_minutes ?? 30)}
              onChange={(event) =>
                savePreferences.mutate({
                  inactivity_timeout_minutes: Number(event.target.value),
                })
              }
            >
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">1 hour</option>
              <option value="240">4 hours</option>
              <option value="480">8 hours</option>
            </Select>
          </Field>
        </CardBody>
      </Card>
    </div>
  )
}

// -------------------------------------------------------------------- sessions

export function SessionsSettings() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)

  const sessions = useQuery({ queryKey: queryKeys.sessions, queryFn: authApi.sessions })

  const revoke = useMutation({
    mutationFn: (id: string) => authApi.revokeSession(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions })
      setNotice('Session revoked.')
    },
  })

  const revokeOthers = useMutation({
    mutationFn: authApi.revokeOtherSessions,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sessions })
      setNotice(result.message)
    },
  })

  if (sessions.isPending) return <PageLoader />

  return (
    <div className="space-y-5">
      {notice && <Alert tone="success">{notice}</Alert>}

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Active sessions</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Every device currently signed in to your account.
            </p>
          </div>
          {(sessions.data?.length ?? 0) > 1 && (
            <Button
              variant="outline"
              size="sm"
              icon={<LogOut className="h-3.5 w-3.5" />}
              loading={revokeOthers.isPending}
              onClick={() => revokeOthers.mutate()}
            >
              Sign out everywhere else
            </Button>
          )}
        </CardHeader>

        <ul className="divide-y divide-slate-100">
          {sessions.data?.map((session) => (
            <li key={session.id} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <Laptop className="h-5 w-5 shrink-0 text-slate-400" />
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-medium text-slate-900">
                    {session.device_name}
                    {session.is_current && <Badge tone="success">This device</Badge>}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    {session.ip_address ?? 'Unknown IP'}
                    {session.location && ` · ${session.location}`} · active{' '}
                    {relative(session.last_active_at)}
                  </p>
                  <p className="text-xs text-slate-400">
                    Signed in {dateTime(session.created_at)}
                  </p>
                </div>
              </div>
              {!session.is_current && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-danger-600"
                  loading={revoke.isPending}
                  onClick={() => revoke.mutate(session.id)}
                >
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <PasskeysCard />
    </div>
  )
}

/** Passkey / biometric login management (Sprint 25, US-108). */
function PasskeysCard() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const passkeys = useQuery({ queryKey: queryKeys.passkeys, queryFn: authApi.webauthnCredentials })

  const remove = useMutation({
    mutationFn: (id: string) => authApi.webauthnDeleteCredential(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.passkeys })
    },
  })

  const addPasskey = async () => {
    setError(null)
    setAdding(true)
    try {
      const { options } = await authApi.webauthnRegisterOptions()
      const credential = await createPasskey(options)
      const deviceName =
        typeof window !== 'undefined' && /iphone|ipad/i.test(window.navigator.userAgent)
          ? 'iPhone/iPad passkey'
          : /android/i.test(window.navigator.userAgent)
            ? 'Android passkey'
            : 'This device'
      await authApi.webauthnRegisterVerify({ credential, device_name: deviceName })
      await queryClient.invalidateQueries({ queryKey: queryKeys.passkeys })
    } catch (registerError) {
      setError(errorMessage(registerError, 'Could not register this passkey.'))
    } finally {
      setAdding(false)
    }
  }

  if (!isWebauthnSupported()) return null

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Passkeys</CardTitle>
          <p className="mt-0.5 text-sm text-slate-500">
            Sign in with your fingerprint or face instead of an SMS code.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          icon={<Plus className="h-3.5 w-3.5" />}
          loading={adding}
          onClick={() => void addPasskey()}
        >
          Add a passkey
        </Button>
      </CardHeader>

      {error && (
        <div className="px-5 pb-3">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}

      {passkeys.data?.length ? (
        <ul className="divide-y divide-slate-100">
          {passkeys.data.map((passkey) => (
            <li key={passkey.id} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <Fingerprint className="h-5 w-5 shrink-0 text-slate-400" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{passkey.device_name}</p>
                  <p className="text-xs text-slate-500">
                    Added {dateTime(passkey.created_at)}
                    {passkey.last_used_at && ` · last used ${relative(passkey.last_used_at)}`}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-danger-600"
                loading={remove.isPending}
                onClick={() => remove.mutate(passkey.id)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-5 pb-5 text-sm text-slate-500">No passkeys registered yet.</p>
      )}
    </Card>
  )
}

// --------------------------------------------------------------- notifications

const NOTIFICATION_LABELS: Record<string, string> = {
  payment_confirmed: 'Payment confirmed',
  rent_reminder: 'Rent reminders',
  invoice_issued: 'New invoice issued',
  receipt_issued: 'Receipt issued',
  maintenance_update: 'Maintenance updates',
  maintenance_submitted: 'New maintenance requests',
  lease_expiry: 'Lease expiry alerts',
  trial_expiry: 'Trial expiry',
  unit_status_changed: 'Unit status changes',
  suspicious_login: 'New sign-in alerts',
  vacate_notice: 'Notices to vacate',
  caretaker_daily_summary: 'Daily caretaker summary',
  welcome: 'Welcome messages',
  account: 'Account and security',
}

const LOCKED_TYPES = ['payment_confirmed', 'receipt_issued', 'suspicious_login', 'account']

export function NotificationSettings() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)

  const preferences = useQuery({
    queryKey: queryKeys.preferences,
    queryFn: notificationsApi.preferences,
  })

  const save = useMutation({
    mutationFn: notificationsApi.setPreferences,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.preferences })
      setNotice('Preferences saved.')
    },
  })

  if (preferences.isPending) return <PageLoader />

  const types = Array.from(new Set(preferences.data?.map((p) => p.notification_type) ?? []))
  const channels = ['whatsapp', 'sms', 'push']

  const isEnabled = (type: string, channel: string) =>
    preferences.data?.find((p) => p.notification_type === type && p.channel === channel)?.enabled ??
    true

  const toggle = (type: string, channel: string, enabled: boolean) =>
    save.mutate([{ notification_type: type, channel, enabled }])

  return (
    <div className="space-y-5">
      {notice && <Alert tone="success">{notice}</Alert>}

      <Card>
        <CardHeader>
          <div>
            <CardTitle>What we send you</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">
              Money and security alerts cannot be switched off.
            </p>
          </div>
        </CardHeader>
        <CardBody className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="px-5 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Notification
                </th>
                {channels.map((channel) => (
                  <th
                    key={channel}
                    className="px-3 py-2.5 text-center text-xs font-semibold uppercase tracking-wide text-slate-500"
                  >
                    {channel === 'sms' ? 'SMS' : humanize(channel)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {types.map((type) => {
                const locked = LOCKED_TYPES.includes(type)
                return (
                  <tr key={type} className="border-b border-slate-50">
                    <td className="px-5 py-2.5 text-slate-700">
                      {NOTIFICATION_LABELS[type] ?? humanize(type)}
                      {locked && (
                        <span className="ml-2 text-xs text-slate-400">(always on)</span>
                      )}
                    </td>
                    {channels.map((channel) => (
                      <td key={channel} className="px-3 py-2.5 text-center">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-brand-600 disabled:opacity-40"
                          disabled={locked}
                          checked={locked || isEnabled(type, channel)}
                          onChange={(event) => toggle(type, channel, event.target.checked)}
                          aria-label={`${type} via ${channel}`}
                        />
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </CardBody>
      </Card>
    </div>
  )
}

// -------------------------------------------------------------- organization

export function OrganizationSettings() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const [roleTimeouts, setRoleTimeouts] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('org:manage'))
  const canManageSecurity = useAuthStore((state) =>
    state.user?.permissions?.includes('security:manage'),
  )

  const organization = useQuery({
    queryKey: queryKeys.organization,
    queryFn: organizationApi.me,
  })

  useEffect(() => {
    if (!organization.data) return
    const data = organization.data as Record<string, unknown>
    setForm({
      name: String(data.name ?? ''),
      legal_name: String(data.legal_name ?? ''),
      address: String(data.address ?? ''),
      contact_email: String(data.contact_email ?? ''),
      contact_phone: String(data.contact_phone ?? ''),
      kra_pin: String(data.kra_pin ?? ''),
      default_billing_day: String(data.default_billing_day ?? '1'),
      default_caretaker_cash_limit: String(data.default_caretaker_cash_limit ?? ''),
      report_delivery_channel: String(data.report_delivery_channel ?? 'both'),
      ip_whitelist: ((data.ip_whitelist as string[] | undefined) ?? []).join('\n'),
      fraud_max_cash_payments_per_window: String(data.fraud_max_cash_payments_per_window ?? '5'),
      fraud_cash_window_minutes: String(data.fraud_cash_window_minutes ?? '30'),
      fraud_unusual_amount_multiplier: String(data.fraud_unusual_amount_multiplier ?? '3.00'),
      bank_name: String(data.bank_name ?? ''),
      bank_account_name: String(data.bank_account_name ?? ''),
      bank_account_number: String(data.bank_account_number ?? ''),
      bank_branch: String(data.bank_branch ?? ''),
      cash_dual_approval_threshold: String(data.cash_dual_approval_threshold ?? ''),
      max_concurrent_sessions: String(data.max_concurrent_sessions ?? ''),
      bi_export_enabled: data.bi_export_enabled ? 'true' : '',
    })
    setRoleTimeouts(
      Object.fromEntries(
        Object.entries((data.role_session_timeouts as Record<string, number>) ?? {}).map(
          ([role, minutes]) => [role, String(minutes)],
        ),
      ),
    )
  }, [organization.data])

  const save = useMutation({
    mutationFn: () =>
      organizationApi.update({
        name: form.name,
        legal_name: form.legal_name || null,
        address: form.address || null,
        contact_email: form.contact_email || null,
        contact_phone: form.contact_phone || null,
        kra_pin: form.kra_pin || null,
        default_billing_day: Number(form.default_billing_day) || 1,
        default_caretaker_cash_limit: form.default_caretaker_cash_limit
          ? Number(form.default_caretaker_cash_limit)
          : null,
        report_delivery_channel: form.report_delivery_channel || 'both',
        ip_whitelist: (form.ip_whitelist ?? '')
          .split('\n')
          .map((entry) => entry.trim())
          .filter(Boolean),
        role_session_timeouts: Object.fromEntries(
          Object.entries(roleTimeouts).filter(([, value]) => value.trim() !== ''),
        ),
        fraud_max_cash_payments_per_window: Number(form.fraud_max_cash_payments_per_window) || 5,
        fraud_cash_window_minutes: Number(form.fraud_cash_window_minutes) || 30,
        fraud_unusual_amount_multiplier: Number(form.fraud_unusual_amount_multiplier) || 3,
        bank_name: form.bank_name || null,
        bank_account_name: form.bank_account_name || null,
        bank_account_number: form.bank_account_number || null,
        bank_branch: form.bank_branch || null,
        // Blank means off, not zero — a threshold of 0 would hold every
        // shilling of cash for a second signature.
        cash_dual_approval_threshold: form.cash_dual_approval_threshold
          ? Number(form.cash_dual_approval_threshold)
          : null,
        max_concurrent_sessions: form.max_concurrent_sessions
          ? Number(form.max_concurrent_sessions)
          : null,
        bi_export_enabled: form.bi_export_enabled === 'true',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.organization })
      setNotice({ tone: 'success', text: 'Organization settings saved.' })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  if (organization.isPending) return <PageLoader />

  const set = (key: string) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  return (
    <div className="space-y-5">
      {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Business details</CardTitle>
          <p className="text-xs text-slate-500">Shown on leases, invoices and receipts</p>
        </CardHeader>
        <CardBody className="space-y-4">
          <Field label="Display name">
            <Input value={form.name ?? ''} onChange={set('name')} disabled={!canManage} />
          </Field>
          <Field label="Registered legal name" hint="Used on the lease agreement.">
            <Input
              value={form.legal_name ?? ''}
              onChange={set('legal_name')}
              disabled={!canManage}
            />
          </Field>
          <Field label="Address">
            <Input value={form.address ?? ''} onChange={set('address')} disabled={!canManage} />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Contact email">
              <Input
                type="email"
                value={form.contact_email ?? ''}
                onChange={set('contact_email')}
                disabled={!canManage}
              />
            </Field>
            <Field label="Contact phone">
              <Input
                type="tel"
                value={form.contact_phone ?? ''}
                onChange={set('contact_phone')}
                disabled={!canManage}
              />
            </Field>
          </div>
          <Field label="KRA PIN" hint="Needed for eTIMS-compliant receipts.">
            <Input value={form.kra_pin ?? ''} onChange={set('kra_pin')} disabled={!canManage} />
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Defaults</CardTitle>
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Default billing day" hint="Used when creating a new tenancy.">
            <Input
              type="number"
              min="1"
              max="28"
              value={form.default_billing_day ?? '1'}
              onChange={set('default_billing_day')}
              disabled={!canManage}
            />
          </Field>
          <Field
            label="Default caretaker cash limit (KES)"
            hint="Cash payments above this alert you."
          >
            <Input
              type="number"
              step="0.01"
              min="0"
              value={form.default_caretaker_cash_limit ?? ''}
              onChange={set('default_caretaker_cash_limit')}
              disabled={!canManage}
            />
          </Field>
          <Field
            label="Monthly report delivery"
            hint="Where your automatic monthly summary is sent."
          >
            <Select
              value={form.report_delivery_channel ?? 'both'}
              onChange={(event) =>
                setForm((current) => ({ ...current, report_delivery_channel: event.target.value }))
              }
              disabled={!canManage}
            >
              <option value="whatsapp">WhatsApp only</option>
              <option value="email">Email only</option>
              <option value="both">WhatsApp and email</option>
            </Select>
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Bank transfer</CardTitle>
          <p className="text-xs text-slate-500">
            Shown to tenants as instructions for paying rent by bank transfer.
          </p>
        </CardHeader>
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Bank name">
            <Input value={form.bank_name ?? ''} onChange={set('bank_name')} disabled={!canManage} />
          </Field>
          <Field label="Account name">
            <Input
              value={form.bank_account_name ?? ''}
              onChange={set('bank_account_name')}
              disabled={!canManage}
            />
          </Field>
          <Field label="Account number">
            <Input
              value={form.bank_account_number ?? ''}
              onChange={set('bank_account_number')}
              disabled={!canManage}
            />
          </Field>
          <Field label="Branch">
            <Input value={form.bank_branch ?? ''} onChange={set('bank_branch')} disabled={!canManage} />
          </Field>
        </CardBody>
      </Card>

      {canManageSecurity && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Access control</CardTitle>
              <p className="text-xs text-slate-500">
                Enterprise security hardening — restrict sign-in by network and set per-role
                session policy.
              </p>
            </CardHeader>
            <CardBody className="space-y-4">
              <Field
                label="IP whitelist"
                hint="One IP address or CIDR range per line. Leave blank to allow sign-in from anywhere."
              >
                <Textarea
                  rows={4}
                  placeholder={'203.0.113.4\n41.90.64.0/20'}
                  value={form.ip_whitelist ?? ''}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, ip_whitelist: event.target.value }))
                  }
                  className="font-mono text-xs"
                />
              </Field>

              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">
                  Session timeout by role (minutes)
                </p>
                <p className="mb-3 text-xs text-slate-500">
                  Applies immediately to every user of that role. Leave blank to keep the default.
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {SECURITY_POLICY_ROLES.map((role) => (
                    <Field key={role.value} label={role.label}>
                      <Input
                        type="number"
                        min="5"
                        max="1440"
                        placeholder="Default"
                        value={roleTimeouts[role.value] ?? ''}
                        onChange={(event) =>
                          setRoleTimeouts((current) => ({
                            ...current,
                            [role.value]: event.target.value,
                          }))
                        }
                      />
                    </Field>
                  ))}
                </div>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Fraud detection thresholds</CardTitle>
              <p className="text-xs text-slate-500">
                What counts as suspicious enough to alert you (US-097).
              </p>
            </CardHeader>
            <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field
                label="Max cash payments per window"
                hint="More than this by one caretaker triggers an alert."
              >
                <Input
                  type="number"
                  min="1"
                  value={form.fraud_max_cash_payments_per_window ?? '5'}
                  onChange={set('fraud_max_cash_payments_per_window')}
                />
              </Field>
              <Field label="Window (minutes)">
                <Input
                  type="number"
                  min="1"
                  value={form.fraud_cash_window_minutes ?? '30'}
                  onChange={set('fraud_cash_window_minutes')}
                />
              </Field>
              <Field
                label="Unusual amount multiplier"
                hint="A payment above rent × this, or below rent ÷ this, is flagged."
              >
                <Input
                  type="number"
                  step="0.1"
                  min="1.1"
                  value={form.fraud_unusual_amount_multiplier ?? '3.00'}
                  onChange={set('fraud_unusual_amount_multiplier')}
                />
              </Field>
            </CardBody>
          </Card>
        </>
      )}

      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Cash controls and sessions</CardTitle>
            <p className="text-xs text-slate-500">
              Who has to sign off on money, and how many devices stay signed in.
            </p>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Hold cash above (KES)"
              hint="A cash payment above this is recorded but not banked until a second person approves it. Leave blank to switch this off."
            >
              <Input
                type="number"
                min="0"
                placeholder="Off"
                value={form.cash_dual_approval_threshold ?? ''}
                onChange={set('cash_dual_approval_threshold')}
              />
            </Field>
            <Field
              label="Maximum devices signed in"
              hint="A new login beyond this signs out the least recently used device. Blank uses the platform default."
            >
              <Input
                type="number"
                min="1"
                max="50"
                placeholder="Platform default"
                value={form.max_concurrent_sessions ?? ''}
                onChange={set('max_concurrent_sessions')}
              />
            </Field>
          </CardBody>
        </Card>
      )}

      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Warehouse export</CardTitle>
            <p className="text-xs text-slate-500">For a data team pulling into their own BI tooling.</p>
          </CardHeader>
          <CardBody>
            <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 accent-brand-600"
                checked={form.bi_export_enabled === 'true'}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    bi_export_enabled: event.target.checked ? 'true' : '',
                  }))
                }
              />
              <span>
                Weekly Parquet export
                <span className="block text-xs text-slate-500 dark:text-slate-400">
                  Every dataset (tenants, tenancies, payments, properties, units, invoices) dropped as
                  Parquet each week, for a data team to pull into their own warehouse. Off by default.
                </span>
              </span>
            </label>
          </CardBody>
        </Card>
      )}

      {canManage && <DemoDataCard />}

      {canManage && (
        <Button loading={save.isPending} onClick={() => save.mutate()}>
          Save organization settings
        </Button>
      )}

      {canManageSecurity && <SecurityAuditLogExport />}
    </div>
  )
}

// ----------------------------------------------------------- security audit log

function SecurityAuditLogExport() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [error, setError] = useState<string | null>(null)

  const runExport = useMutation({
    mutationFn: async (format: 'csv' | 'pdf') => {
      const blob = await securityApi.exportAuditLog({
        format,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `rentflow-audit-log.${format}`
      link.click()
      URL.revokeObjectURL(url)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Security audit log</CardTitle>
        <p className="text-xs text-slate-500">
          Every privileged action taken on this account, exportable for compliance.
        </p>
      </CardHeader>
      <CardBody className="space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="From">
            <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </Field>
          <Field label="To">
            <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </Field>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            icon={<Download className="h-4 w-4" />}
            loading={runExport.isPending}
            onClick={() => runExport.mutate('csv')}
          >
            Export CSV
          </Button>
          <Button
            variant="secondary"
            icon={<Download className="h-4 w-4" />}
            loading={runExport.isPending}
            onClick={() => runExport.mutate('pdf')}
          >
            Export PDF
          </Button>
        </div>
      </CardBody>
    </Card>
  )
}


// ----------------------------------------------------------------- demo data

/**
 * Sample data (Module 24). A landlord evaluating RentFlow on an empty account
 * sees empty screens, which tells them nothing about whether it would help.
 *
 * Removal deletes exactly the rows the seeding recorded, in reverse order —
 * nothing is matched by name — so a customer who has started entering their own
 * portfolio alongside the sample can still clear the sample cleanly.
 */
function DemoDataCard() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const status = useQuery({ queryKey: queryKeys.demoData, queryFn: organizationApi.demoData })

  const settled = async (text: string) => {
    setNotice({ tone: 'success', text })
    // Everything is affected: the portfolio, the money, the reports.
    await queryClient.invalidateQueries()
  }

  const load = useMutation({
    mutationFn: organizationApi.loadDemoData,
    onSuccess: (result) => settled(`Loaded ${result.row_count} sample records.`),
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })
  const remove = useMutation({
    mutationFn: organizationApi.removeDemoData,
    onSuccess: (result) => settled(result.message),
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const loaded = status.data?.loaded ?? false

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sample data</CardTitle>
        <p className="text-xs text-slate-500">
          A small demonstration portfolio, so every screen has something in it.
        </p>
      </CardHeader>
      <CardBody className="space-y-3">
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

        {loaded ? (
          <>
            <Alert tone="info" title="Sample data is loaded">
              {status.data?.row_count} example records — a block of flats, four tenants at
              different stages of paying, and about a year of history. Everything in it is
              fabricated. Remove it before you go live.
            </Alert>
            <Button
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => remove.mutate()}
              loading={remove.isPending}
            >
              Remove sample data
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-600">
              Adds one example property, six units, four tenants and their payment history. It
              sits alongside anything you have already entered, and removing it never touches
              your own records.
            </p>
            <Button
              variant="secondary"
              icon={<Sparkles className="h-4 w-4" />}
              onClick={() => load.mutate()}
              loading={load.isPending}
            >
              Load sample data
            </Button>
          </>
        )}
      </CardBody>
    </Card>
  )
}
