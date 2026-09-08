/** Thin wrapper around Google Identity Services (GIS) — the script that draws
 * the "Sign in with Google" button and hands back a signed ID token. Loaded
 * lazily so pages that never show the button never pay for it. */

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
          }) => void
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void
        }
      }
    }
  }
}

const SCRIPT_SRC = 'https://accounts.google.com/gsi/client'

export const GOOGLE_CLIENT_ID: string | undefined = import.meta.env.VITE_GOOGLE_CLIENT_ID

let scriptPromise: Promise<void> | null = null

function loadScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve()
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('Failed to load Google Identity Services')))
      return
    }
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google Identity Services'))
    document.head.appendChild(script)
  })
  return scriptPromise
}

/** Loads GIS if needed, then draws the button into `container` and reports
 * the ID token from every successful sign-in via `onCredential`. */
export async function renderGoogleButton(
  container: HTMLElement,
  onCredential: (credential: string) => void,
): Promise<void> {
  if (!GOOGLE_CLIENT_ID) return
  await loadScript()
  window.google!.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: (response) => onCredential(response.credential),
  })
  window.google!.accounts.id.renderButton(container, {
    type: 'standard',
    theme: 'outline',
    size: 'large',
    text: 'continue_with',
    width: 320,
  })
}
