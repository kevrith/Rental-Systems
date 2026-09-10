import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns'

/** `25000` -> `KES 25,000.00`. Every money value in the UI goes through here. */
export function kes(value: number | string | null | undefined, options?: { compact?: boolean }): string {
  const amount = typeof value === 'string' ? Number.parseFloat(value) : (value ?? 0)
  if (!Number.isFinite(amount)) return 'KES 0.00'

  if (options?.compact && Math.abs(amount) >= 1_000_000) {
    return `KES ${(amount / 1_000_000).toFixed(1)}M`
  }
  if (options?.compact && Math.abs(amount) >= 10_000) {
    return `KES ${(amount / 1_000).toFixed(0)}K`
  }
  return `KES ${amount.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Number without the currency prefix, for chart axes and tight table cells. */
export function amount(value: number | string | null | undefined): string {
  const parsed = typeof value === 'string' ? Number.parseFloat(value) : (value ?? 0)
  if (!Number.isFinite(parsed)) return '0'
  return parsed.toLocaleString('en-KE', { maximumFractionDigits: 0 })
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  const date = value instanceof Date ? value : parseISO(value)
  return isValid(date) ? date : null
}

/** `2026-09-03` -> `3 Sep 2026`. */
export function shortDate(value: string | Date | null | undefined): string {
  const date = toDate(value)
  return date ? format(date, 'd MMM yyyy') : '—'
}

/** `2026-09-03T12:04:00Z` -> `3 Sep 2026, 15:04`. */
export function dateTime(value: string | Date | null | undefined): string {
  const date = toDate(value)
  return date ? format(date, "d MMM yyyy, HH:mm") : '—'
}

/** `2026-09-01` -> `2 days ago`. */
export function relative(value: string | Date | null | undefined): string {
  const date = toDate(value)
  if (!date) return '—'
  return `${formatDistanceToNowStrict(date)} ago`
}

/** Today as `yyyy-MM-dd`, for date input defaults. */
export function today(): string {
  return format(new Date(), 'yyyy-MM-dd')
}

/** `under_maintenance` -> `Under maintenance`. */
export function humanize(value: string | null | undefined): string {
  if (!value) return '—'
  const spaced = value.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/).slice(0, 2)
  return parts.map((part) => part.charAt(0).toUpperCase()).join('')
}

/** Turn any API error into a sentence worth showing a user. */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  // Axios wraps network failures — no response means the server was unreachable.
  const axiosError = error as { response?: { data?: { detail?: unknown } }; request?: unknown; message?: string }
  if (!axiosError.response && axiosError.request) {
    return 'Could not reach the server. Check your connection and try again.'
  }
  const detail = axiosError?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  // FastAPI validation errors come back as a list of {loc, msg}.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string }
    if (first?.msg) return first.msg
  }
  if (error instanceof Error && error.message && !error.message.includes('status code')) return error.message
  return fallback
}
