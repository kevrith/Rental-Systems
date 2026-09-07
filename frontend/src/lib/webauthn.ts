/**
 * Browser-side WebAuthn helpers (Sprint 25, US-108).
 *
 * The server hands back options with base64url-encoded byte fields (challenge,
 * user id, credential ids); `navigator.credentials.create/get` need real
 * `ArrayBuffer`s for those same fields. Modern browsers' `PublicKeyCredential`
 * also exposes `toJSON()`, which already produces exactly the shape the
 * server's `webauthn` library expects back — but it isn't universal yet, so a
 * manual fallback covers browsers without it.
 */

export function isWebauthnSupported(): boolean {
  return typeof window !== 'undefined' && 'PublicKeyCredential' in window
}

function base64urlToBuffer(base64url: string): ArrayBuffer {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/').padEnd(
    base64url.length + ((4 - (base64url.length % 4)) % 4),
    '=',
  )
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function credentialToJson(credential: PublicKeyCredential): any {
  const withToJson = credential as unknown as { toJSON?: () => unknown }
  if (typeof withToJson.toJSON === 'function') return withToJson.toJSON()

  const response = credential.response as AuthenticatorAttestationResponse &
    AuthenticatorAssertionResponse
  const base: Record<string, unknown> = {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    clientExtensionResults: credential.getClientExtensionResults(),
  }
  if (response.attestationObject) {
    base.response = {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
    }
  } else {
    base.response = {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    }
  }
  return base
}

export async function createPasskey(optionsJson: string): Promise<unknown> {
  const options = JSON.parse(optionsJson)
  const publicKey: CredentialCreationOptions['publicKey'] = {
    ...options,
    challenge: base64urlToBuffer(options.challenge),
    user: { ...options.user, id: base64urlToBuffer(options.user.id) },
    excludeCredentials: (options.excludeCredentials ?? []).map((cred: { id: string; type: string }) => ({
      ...cred,
      id: base64urlToBuffer(cred.id),
    })),
  }
  const credential = await navigator.credentials.create({ publicKey })
  if (!credential) throw new Error('No passkey was created')
  return credentialToJson(credential as PublicKeyCredential)
}

export async function getPasskeyAssertion(optionsJson: string): Promise<unknown> {
  const options = JSON.parse(optionsJson)
  const publicKey: CredentialRequestOptions['publicKey'] = {
    ...options,
    challenge: base64urlToBuffer(options.challenge),
    allowCredentials: (options.allowCredentials ?? []).map((cred: { id: string; type: string }) => ({
      ...cred,
      id: base64urlToBuffer(cred.id),
    })),
  }
  const credential = await navigator.credentials.get({ publicKey })
  if (!credential) throw new Error('No passkey was selected')
  return credentialToJson(credential as PublicKeyCredential)
}
