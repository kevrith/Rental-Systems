import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

import { deviceId } from '@/lib/device'
import { useAuthStore } from '@/store/auth-store'

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

export const apiClient = axios.create({ baseURL: API_BASE_URL })

/** A bare client for the refresh call itself — using `apiClient` would recurse. */
const refreshClient = axios.create({ baseURL: API_BASE_URL })

apiClient.interceptors.request.use((config) => {
  const { accessToken } = useAuthStore.getState()
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  // The backend uses this to recognise trusted devices and label sessions.
  config.headers['X-Device-Id'] = deviceId()
  return config
})

/**
 * Refresh-on-401.
 *
 * Refresh tokens rotate on every use, so two concurrent 401s must not both call
 * `/auth/refresh` — the second would present an already-rotated token and the
 * server would treat it as theft and revoke every session. `pending` collapses
 * concurrent refreshes into one in-flight promise that all waiters share.
 */
let pending: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const { refreshToken } = useAuthStore.getState()
  if (!refreshToken) throw new Error('No refresh token')

  const { data } = await refreshClient.post<{ access_token: string; refresh_token: string }>(
    '/auth/refresh',
    { refresh_token: refreshToken },
    { headers: { 'X-Device-Id': deviceId() } },
  )

  useAuthStore.getState().setTokens({
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  })
  return data.access_token
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status

    // Only a 401 is recoverable. A 403 means the role or tenant is wrong, and
    // no amount of refreshing will change that.
    if (status !== 401 || !config || config._retried) {
      return Promise.reject(error)
    }

    // The refresh endpoint failing means the session is genuinely over.
    if (config.url?.includes('/auth/refresh')) {
      useAuthStore.getState().logout()
      return Promise.reject(error)
    }

    config._retried = true

    try {
      pending = pending ?? refreshAccessToken().finally(() => {
        pending = null
      })
      const token = await pending
      config.headers.Authorization = `Bearer ${token}`
      return apiClient(config)
    } catch (refreshError) {
      useAuthStore.getState().logout()
      return Promise.reject(refreshError)
    }
  },
)

/** Attach GPS to a mutating request when the caller has coordinates. */
export function geoHeaders(
  position: { latitude: number; longitude: number } | null,
): Record<string, string> {
  if (!position) return {}
  return { 'X-Geo-Position': `${position.latitude},${position.longitude}` }
}
