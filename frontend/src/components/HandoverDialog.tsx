import { Check, Copy, MessageCircle, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'

import type { HandoverResult } from '@/api/types'
import { Alert, Button, Dialog, LinkButton } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { lifetimeLabel, smsUrl, whatsappUrl } from '@/lib/handover'

export interface HandoverAction {
  key: string
  title: string
  description?: string
  buttonLabel: string
  icon: ReactNode
  run: () => Promise<HandoverResult>
}

/**
 * Hands a landlord or caretaker a code or link to pass on themselves.
 *
 * Nothing is sent from RentFlow: the secret is shown once, with buttons that
 * open WhatsApp or the phone's SMS app with the recipient's number and the
 * message already filled in. Render it conditionally (`{target && <… />}`) so
 * the results are discarded when it closes — a code must not outlive the
 * window it was shown in.
 */
export function HandoverDialog({
  title,
  description,
  actions,
  onClose,
}: {
  title: string
  description?: string
  actions: HandoverAction[]
  onClose: () => void
}) {
  const [results, setResults] = useState<Record<string, HandoverResult>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(action: HandoverAction) {
    setBusy(action.key)
    setError(null)
    try {
      const result = await action.run()
      setResults((previous) => ({ ...previous, [action.key]: result }))
    } catch (runError) {
      setError(errorMessage(runError))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={title}
      description={description}
      footer={<Button onClick={onClose}>Done</Button>}
    >
      <div className="space-y-6">
        {error && <Alert tone="danger">{error}</Alert>}
        {actions.map((action) => {
          const result = results[action.key]
          return (
            <section key={action.key} className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">{action.title}</h3>
                {action.description && (
                  <p className="mt-0.5 text-sm text-slate-500">{action.description}</p>
                )}
              </div>
              {result ? (
                <HandoverPanel result={result} />
              ) : (
                <Button
                  variant="outline"
                  icon={action.icon}
                  loading={busy === action.key}
                  disabled={busy !== null}
                  onClick={() => void run(action)}
                >
                  {action.buttonLabel}
                </Button>
              )}
            </section>
          )
        })}
      </div>
    </Dialog>
  )
}

function HandoverPanel({ result }: { result: HandoverResult }) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(result.message)
      setCopied(true)
      setCopyError(false)
    } catch {
      setCopyError(true)
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
      {'code' in result && (
        <p
          className="text-center font-mono text-3xl font-semibold tracking-[0.3em] text-slate-900"
          aria-label={`Code ${result.code.split('').join(' ')}`}
        >
          {result.code}
        </p>
      )}
      <p className="rounded-md bg-white px-3 py-2 text-sm text-slate-700 [overflow-wrap:anywhere]">
        {result.message}
      </p>
      <div className="flex flex-wrap gap-2">
        <LinkButton
          href={whatsappUrl(result.phone_number, result.message)}
          target="_blank"
          rel="noreferrer"
          icon={<MessageCircle className="h-4 w-4" />}
        >
          Send on WhatsApp
        </LinkButton>
        <LinkButton
          variant="secondary"
          href={smsUrl(result.phone_number, result.message)}
          icon={<MessageSquare className="h-4 w-4" />}
        >
          Send by SMS
        </LinkButton>
        <Button
          variant="ghost"
          icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          onClick={() => void copy()}
        >
          {copied ? 'Copied' : 'Copy message'}
        </Button>
      </div>
      {copyError && (
        <p role="alert" className="text-xs text-danger-700">
          Could not copy. Select the message and copy it by hand.
        </p>
      )}
      <p className="text-xs text-slate-500">
        To {result.recipient_name}, {result.phone_number}.
        {result.expires_in_seconds != null && ` Works for ${lifetimeLabel(result.expires_in_seconds)}.`}{' '}
        {'code' in result && 'It works once and cannot be shown again, so send it before you close this window. '}
        Send by SMS opens the messages app on a phone; on a computer use WhatsApp or copy the message.
      </p>
    </div>
  )
}
