import { apiClient } from '@/lib/api-client'
import type { AuthOrganization, AuthUser } from '@/store/auth-store'

import type { SessionRow } from './types'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in?: number | null
  inactivity_timeout_minutes?: number | null
}

export interface RegisterPayload {
  full_name: string
  organization_name: string
  email: string
  phone_number: string
  password: string
  account_type: 'owner' | 'agency'
}

export interface RegisterResponse {
  organization: AuthOrganization
  user: AuthUser
  tokens: TokenResponse
}

export interface LoginPayload {
  email: string
  password: string
  remember_device?: boolean
}

export interface LoginChallengeResponse {
  otp_required: boolean
  challenge_token: string | null
  expires_in: number | null
  message: string
  tokens: TokenResponse | null
  webauthn_options: string | null
}

export interface GoogleAuthResponse {
  status: 'signed_in' | 'needs_registration'
  tokens: TokenResponse | null
  email: string | null
  full_name: string | null
}

export interface GoogleRegisterPayload {
  credential: string
  organization_name: string
  phone_number: string
  account_type: 'owner' | 'agency'
}

export interface WebauthnCredentialRow {
  id: string
  device_name: string
  created_at: string
  last_used_at: string | null
}

export const authApi = {
  register: async (payload: RegisterPayload) =>
    (await apiClient.post<RegisterResponse>('/auth/register', payload)).data,

  login: async (payload: LoginPayload) =>
    (await apiClient.post<LoginChallengeResponse>('/auth/login', payload)).data,

  googleAuth: async (credential: string) =>
    (await apiClient.post<GoogleAuthResponse>('/auth/google', { credential })).data,

  googleRegister: async (payload: GoogleRegisterPayload) =>
    (await apiClient.post<RegisterResponse>('/auth/google/register', payload)).data,

  verifyLoginOtp: async (payload: {
    challenge_token: string
    otp_code: string
    remember_device?: boolean
  }) => (await apiClient.post<TokenResponse>('/auth/login/verify-otp', payload)).data,

  logout: async (refresh_token: string | null) =>
    (await apiClient.post<{ message: string }>('/auth/logout', { refresh_token })).data,

  me: async () => (await apiClient.get<AuthUser>('/auth/me')).data,

  updateProfile: async (payload: Record<string, unknown>) =>
    (await apiClient.patch<AuthUser>('/auth/me', payload)).data,

  verifyPhone: async (otp_code: string) =>
    (await apiClient.post<AuthUser>('/auth/verify-phone', { otp_code })).data,

  resendPhoneVerification: async () => {
    await apiClient.post('/auth/verify-phone/resend')
  },

  verifyEmail: async (token: string) =>
    (await apiClient.post<AuthUser>('/auth/verify-email', { token })).data,

  resendEmailVerification: async (email: string) =>
    (await apiClient.post<{ message: string }>('/auth/verify-email/resend', { email })).data,

  forgotPassword: async (email: string) =>
    (await apiClient.post<{ message: string }>('/auth/forgot-password', { email })).data,

  resetPassword: async (payload: { token: string; new_password: string }) =>
    (await apiClient.post<{ message: string }>('/auth/reset-password', payload)).data,

  changePassword: async (payload: { current_password: string; new_password: string }) =>
    (await apiClient.post<{ message: string }>('/auth/change-password', payload)).data,

  requestDeletion: async () =>
    (await apiClient.post<{ message: string }>('/auth/me/delete')).data,

  cancelDeletion: async () =>
    (await apiClient.post<{ message: string }>('/auth/me/delete/cancel')).data,

  sessions: async () => (await apiClient.get<SessionRow[]>('/auth/sessions')).data,

  revokeSession: async (id: string) =>
    (await apiClient.delete<{ message: string }>(`/auth/sessions/${id}`)).data,

  revokeOtherSessions: async () =>
    (await apiClient.post<{ message: string }>('/auth/sessions/revoke-others')).data,

  exportOwnData: async () =>
    (await apiClient.post<{ download_url: string | null }>('/auth/me/data-export')).data,

  verifyLoginWebauthn: async (payload: {
    challenge_token: string
    credential: unknown
    remember_device?: boolean
  }) => (await apiClient.post<TokenResponse>('/auth/login/verify-webauthn', payload)).data,

  webauthnRegisterOptions: async () =>
    (await apiClient.post<{ options: string }>('/auth/webauthn/register/options')).data,

  webauthnRegisterVerify: async (payload: { credential: unknown; device_name: string }) =>
    (await apiClient.post<WebauthnCredentialRow>('/auth/webauthn/register/verify', payload)).data,

  webauthnCredentials: async () =>
    (await apiClient.get<WebauthnCredentialRow[]>('/auth/webauthn/credentials')).data,

  webauthnDeleteCredential: async (id: string) =>
    (await apiClient.delete<{ message: string }>(`/auth/webauthn/credentials/${id}`)).data,
}
