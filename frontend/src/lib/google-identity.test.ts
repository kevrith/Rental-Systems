import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * None of this has a visual signal when it breaks: an unconfigured client id
 * must make the button not appear at all rather than render broken, a second
 * call must reuse the one script tag already in the page rather than inject a
 * duplicate, and Google's own callback has to be relayed into ours untouched
 * — a credential silently dropped here means every sign-in from an existing
 * account looks like a fresh registration instead.
 */
async function freshGoogleIdentity() {
  vi.resetModules()
  return import('@/lib/google-identity')
}

function scriptTags() {
  return document.head.querySelectorAll('script[src="https://accounts.google.com/gsi/client"]')
}

beforeEach(() => {
  document.head.innerHTML = ''
  delete window.google
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('GOOGLE_CLIENT_ID', () => {
  it('reads from VITE_GOOGLE_CLIENT_ID', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')

    const { GOOGLE_CLIENT_ID } = await freshGoogleIdentity()

    expect(GOOGLE_CLIENT_ID).toBe('test-client-id')
  })
})

describe('renderGoogleButton', () => {
  it('does nothing when no client id is configured, so the button never appears half-set-up', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '')
    const { renderGoogleButton } = await freshGoogleIdentity()

    await renderGoogleButton(document.createElement('div'), vi.fn())

    expect(scriptTags()).toHaveLength(0)
  })

  it('loads the GIS script once, then initializes and draws the button', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')
    const { renderGoogleButton } = await freshGoogleIdentity()
    const container = document.createElement('div')
    const initialize = vi.fn<
      (config: { client_id: string; callback: (r: { credential: string }) => void }) => void
    >()
    const renderButton = vi.fn<(parent: HTMLElement, options: Record<string, unknown>) => void>()

    const pending = renderGoogleButton(container, vi.fn())
    const script = scriptTags()[0]
    expect(script).toBeTruthy()

    // Simulate the browser having fetched and run the real GIS script: it
    // defines window.google, then the script element fires its load event.
    window.google = { accounts: { id: { initialize, renderButton } } }
    script.dispatchEvent(new Event('load'))
    await pending

    expect(initialize).toHaveBeenCalledWith(expect.objectContaining({ client_id: 'test-client-id' }))
    expect(renderButton).toHaveBeenCalledWith(container, expect.objectContaining({ type: 'standard' }))
  })

  it("relays Google's credential to the caller untouched", async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')
    const { renderGoogleButton } = await freshGoogleIdentity()
    const onCredential = vi.fn()
    let capturedCallback: ((response: { credential: string }) => void) | undefined
    const initialize = vi.fn<
      (config: { client_id: string; callback: (r: { credential: string }) => void }) => void
    >((config) => {
      capturedCallback = config.callback
    })
    window.google = { accounts: { id: { initialize, renderButton: vi.fn() } } }

    await renderGoogleButton(document.createElement('div'), onCredential)
    capturedCallback?.({ credential: 'signed-jwt' })

    expect(onCredential).toHaveBeenCalledWith('signed-jwt')
  })

  it('reuses GIS without injecting a script tag when it is already loaded', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')
    const { renderGoogleButton } = await freshGoogleIdentity()
    const initialize = vi.fn<
      (config: { client_id: string; callback: (r: { credential: string }) => void }) => void
    >()
    const renderButton = vi.fn<(parent: HTMLElement, options: Record<string, unknown>) => void>()
    window.google = { accounts: { id: { initialize, renderButton } } }

    await renderGoogleButton(document.createElement('div'), vi.fn())

    expect(scriptTags()).toHaveLength(0)
    expect(initialize).toHaveBeenCalled()
    expect(renderButton).toHaveBeenCalled()
  })

  it('reuses an already-injected script tag instead of adding a duplicate', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')
    const preexisting = document.createElement('script')
    preexisting.src = 'https://accounts.google.com/gsi/client'
    document.head.appendChild(preexisting)
    const { renderGoogleButton } = await freshGoogleIdentity()

    const pending = renderGoogleButton(document.createElement('div'), vi.fn())
    window.google = { accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } } }
    preexisting.dispatchEvent(new Event('load'))
    await pending

    expect(scriptTags()).toHaveLength(1)
  })

  it('rejects instead of hanging forever if the GIS script fails to load', async () => {
    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'test-client-id')
    const { renderGoogleButton } = await freshGoogleIdentity()

    const pending = renderGoogleButton(document.createElement('div'), vi.fn())
    scriptTags()[0].dispatchEvent(new Event('error'))

    await expect(pending).rejects.toThrow('Failed to load Google Identity Services')
  })
})
