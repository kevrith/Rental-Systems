import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'

import { organizationApi } from '@/api'
import type { MpesaCollectionMode } from '@/api/types'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  Field,
  Input,
  PageLoader,
  Select,
} from '@/components/ui'
import { errorMessage, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** The three ways a Kenyan landlord actually collects rent today. None of them
 *  is a lesser version of the others — the app has to be useful in all three. */
const MODES: { id: MpesaCollectionMode; label: string; blurb: string }[] = [
  {
    id: 'automated',
    label: 'Paybill or till with API access',
    blurb:
      'You have a Safaricom Daraja app. Tenants get an M-Pesa prompt from the app, and payments confirm and receipt themselves.',
  },
  {
    id: 'paybill',
    label: 'Paybill or till, no API access',
    blurb:
      'Tenants are shown your paybill and account number. You record what comes in, or match it from a statement.',
  },
  {
    id: 'manual',
    label: 'My own M-Pesa number',
    blurb:
      'Tenants pay your number as they always have. You record the payment here and the receipt and balance follow automatically.',
  },
]

export function MpesaSettingsPage() {
  const queryClient = useQueryClient()
  const setup = useQuery({ queryKey: queryKeys.mpesaSetup, queryFn: organizationApi.mpesaSetup })

  const [mode, setMode] = useState<MpesaCollectionMode>('manual')
  const [shortcode, setShortcode] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [accountLabel, setAccountLabel] = useState('')
  const [environment, setEnvironment] = useState('sandbox')
  const [consumerKey, setConsumerKey] = useState('')
  const [consumerSecret, setConsumerSecret] = useState('')
  const [passkey, setPasskey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  useEffect(() => {
    if (!setup.data) return
    setMode(setup.data.mode)
    setShortcode(setup.data.shortcode ?? '')
    setPhoneNumber(setup.data.phone_number ?? '')
    setAccountLabel(setup.data.account_label ?? '')
    setEnvironment(setup.data.daraja_environment)
  }, [setup.data])

  const save = useMutation({
    mutationFn: () =>
      organizationApi.saveMpesaSetup({
        mode,
        shortcode: shortcode || null,
        phone_number: phoneNumber || null,
        account_label: accountLabel || null,
        daraja_environment: environment,
        // Blank means "leave what is stored alone", so editing the label does
        // not force you to re-type your Daraja secret.
        consumer_key: consumerKey || null,
        consumer_secret: consumerSecret || null,
        passkey: passkey || null,
      }),
    onSuccess: async () => {
      setConsumerKey('')
      setConsumerSecret('')
      setPasskey('')
      setSaved(true)
      setTestResult(null)
      await queryClient.invalidateQueries({ queryKey: ['organization'] })
    },
    onError: (saveError) => setError(errorMessage(saveError)),
  })

  const test = useMutation({
    mutationFn: organizationApi.testMpesaSetup,
    onSuccess: async (result) => {
      setTestResult({ ok: result.ok, message: result.message })
      await queryClient.invalidateQueries({ queryKey: queryKeys.mpesaSetup })
    },
    onError: (testError) => setTestResult({ ok: false, message: errorMessage(testError) }),
  })

  if (setup.isPending) return <PageLoader />

  return (
    <div className="space-y-5">
      <Alert tone="info" icon={<Smartphone className="h-4 w-4" />}>
        Rent goes straight to your own M-Pesa. RentFlow never holds your money — it records,
        receipts and reconciles what your tenants pay you.
      </Alert>

      {error && (
        <Alert tone="danger" icon={<AlertCircle className="h-4 w-4" />}>
          {error}
        </Alert>
      )}
      {saved && !save.isPending && (
        <Alert tone="success" icon={<CheckCircle2 className="h-4 w-4" />}>
          Saved.
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>How your tenants pay you</CardTitle>
          <CardDescription>Pick whichever matches what you already use.</CardDescription>
        </CardHeader>
        <CardBody className="space-y-3">
          {MODES.map((option) => (
            <label
              key={option.id}
              className={`flex cursor-pointer gap-3 rounded-card border p-3 ${
                mode === option.id
                  ? 'border-brand-400 bg-brand-50 dark:bg-brand-900/20'
                  : 'border-slate-200 dark:border-slate-700'
              }`}
            >
              <input
                type="radio"
                name="mpesa-mode"
                className="mt-1 h-4 w-4 accent-brand-600"
                checked={mode === option.id}
                onChange={() => {
                  setMode(option.id)
                  setSaved(false)
                }}
              />
              <span>
                <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">
                  {option.label}
                </span>
                <span className="block text-xs text-slate-500 dark:text-slate-400">
                  {option.blurb}
                </span>
              </span>
            </label>
          ))}
        </CardBody>
      </Card>

      {(mode === 'automated' || mode === 'paybill') && (
        <Card>
          <CardHeader>
            <CardTitle>Your paybill or till</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Shortcode" required hint="The paybill or till number tenants pay.">
              <Input value={shortcode} onChange={(e) => setShortcode(e.target.value)} placeholder="174379" />
            </Field>
            <Field
              label="Account number to quote"
              hint="What tenants type as the account. Their unit or tenant reference works well."
            >
              <Input
                value={accountLabel}
                onChange={(e) => setAccountLabel(e.target.value)}
                placeholder="Unit number"
              />
            </Field>
          </CardBody>
        </Card>
      )}

      {mode === 'manual' && (
        <Card>
          <CardHeader>
            <CardTitle>Your M-Pesa number</CardTitle>
            <CardDescription>Shown to tenants in their portal so they know where to send rent.</CardDescription>
          </CardHeader>
          <CardBody>
            <Field label="Phone number">
              <Input
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="0712345678"
              />
            </Field>
          </CardBody>
        </Card>
      )}

      {mode === 'automated' && (
        <Card>
          <CardHeader>
            <CardTitle>Daraja API credentials</CardTitle>
            <CardDescription>
              From your app on the Safaricom Developer Portal. Stored encrypted, and never shown
              again once saved.
            </CardDescription>
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Environment" required>
              <Select value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                <option value="sandbox">Sandbox (testing)</option>
                <option value="production">Production (real money)</option>
              </Select>
            </Field>
            <Field
              label="Consumer key"
              hint={setup.data?.has_api_credentials ? 'Leave blank to keep the saved one.' : undefined}
            >
              <Input
                value={consumerKey}
                onChange={(e) => setConsumerKey(e.target.value)}
                autoComplete="off"
                placeholder={setup.data?.has_api_credentials ? 'Saved' : ''}
              />
            </Field>
            <Field
              label="Consumer secret"
              hint={setup.data?.has_api_credentials ? 'Leave blank to keep the saved one.' : undefined}
            >
              <Input
                type="password"
                value={consumerSecret}
                onChange={(e) => setConsumerSecret(e.target.value)}
                autoComplete="new-password"
                placeholder={setup.data?.has_api_credentials ? 'Saved' : ''}
              />
            </Field>
            <Field
              label="Passkey"
              hint={setup.data?.has_api_credentials ? 'Leave blank to keep the saved one.' : undefined}
            >
              <Input
                type="password"
                value={passkey}
                onChange={(e) => setPasskey(e.target.value)}
                autoComplete="new-password"
                placeholder={setup.data?.has_api_credentials ? 'Saved' : ''}
              />
            </Field>
          </CardBody>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          loading={save.isPending}
          onClick={() => {
            setError(null)
            setSaved(false)
            save.mutate()
          }}
        >
          Save collection settings
        </Button>
        {mode === 'automated' && setup.data?.has_api_credentials && (
          <Button variant="secondary" loading={test.isPending} onClick={() => test.mutate()}>
            Test connection
          </Button>
        )}
      </div>

      {testResult && (
        <Alert
          tone={testResult.ok ? 'success' : 'danger'}
          icon={
            testResult.ok ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <AlertCircle className="h-4 w-4" />
            )
          }
        >
          {testResult.message}
          {testResult.ok && (
            <span className="mt-1 block text-xs">
              This checks your API key and secret. Your paybill and passkey are only exercised by a
              real payment.
            </span>
          )}
        </Alert>
      )}

      {mode === 'automated' && setup.data?.verified_at && !testResult && (
        <p className="flex items-center gap-1.5 text-sm text-money-700">
          <CheckCircle2 className="h-4 w-4" />
          Credentials last verified {shortDate(setup.data.verified_at)}.
        </p>
      )}
    </div>
  )
}
