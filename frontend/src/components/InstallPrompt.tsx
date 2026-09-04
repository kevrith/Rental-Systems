import { Download, Share, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui'

/** Chrome's install event, which TypeScript's DOM lib does not model. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const DISMISSED_KEY = 'rentflow-install-dismissed'
const DISMISS_DAYS = 14

function recentlyDismissed(): boolean {
  try {
    const stored = localStorage.getItem(DISMISSED_KEY)
    if (!stored) return false
    return Date.now() - Number(stored) < DISMISS_DAYS * 24 * 60 * 60 * 1000
  } catch {
    return false
  }
}

function isStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS Safari reports installed apps here rather than through display-mode.
    (window.navigator as { standalone?: boolean }).standalone === true
  )
}

function isIos(): boolean {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
}

/**
 * Custom install prompt (US-024).
 *
 * Chrome's own banner is easy to miss and cannot be timed. This asks in our own
 * words, at a moment the user is already in the app, and stays quiet for two
 * weeks if dismissed.
 *
 * iOS Safari fires no install event at all, so there it shows the manual
 * "Add to Home Screen" instructions instead — the only route available.
 */
export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [showIosHelp, setShowIosHelp] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (isStandalone() || recentlyDismissed()) return

    const onBeforeInstall = (event: Event) => {
      // Suppress the browser's own banner so ours is the only ask.
      event.preventDefault()
      setDeferred(event as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)

    // iOS never fires that event; offer the manual route after a short delay so
    // the prompt doesn't collide with the first paint.
    let timer: number | undefined
    if (isIos()) {
      timer = window.setTimeout(() => setShowIosHelp(true), 4000)
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      if (timer) window.clearTimeout(timer)
    }
  }, [])

  const dismiss = () => {
    setDismissed(true)
    try {
      localStorage.setItem(DISMISSED_KEY, String(Date.now()))
    } catch {
      // A blocked storage write just means we ask again next session.
    }
  }

  const install = async () => {
    if (!deferred) return
    await deferred.prompt()
    const choice = await deferred.userChoice
    setDeferred(null)
    if (choice.outcome === 'dismissed') dismiss()
  }

  if (dismissed || (!deferred && !showIosHelp)) return null

  return (
    <div className="fixed inset-x-3 bottom-3 z-40 mx-auto max-w-md rounded-card border border-slate-200 bg-white p-4 shadow-lg sm:inset-x-auto sm:right-4 pb-safe">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Download className="h-5 w-5" />
        </span>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">Install RentFlow</p>
          {deferred ? (
            <p className="mt-0.5 text-sm text-slate-500">
              Add it to your home screen to open it instantly and keep working offline.
            </p>
          ) : (
            <p className="mt-0.5 text-sm text-slate-500">
              Tap{' '}
              <Share className="mx-0.5 inline h-3.5 w-3.5 align-text-bottom" />{' '}
              <span className="font-medium">Share</span>, then{' '}
              <span className="font-medium">Add to Home Screen</span>.
            </p>
          )}

          {deferred && (
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => void install()}>
                Install
              </Button>
              <Button size="sm" variant="ghost" onClick={dismiss}>
                Not now
              </Button>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="rounded p-1 text-slate-400 hover:bg-slate-100"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
