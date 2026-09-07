import { Building2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** Shared frame for every unauthenticated screen. */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle?: string
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-10">
      <div className="mb-6 flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Building2 className="h-5 w-5" />
        </span>
        <span className="text-lg font-semibold text-slate-900">RentFlow Kenya</span>
      </div>

      <main className="w-full max-w-md rounded-card border border-slate-200 bg-white p-7 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </main>

      {footer && <div className="mt-5 text-center text-sm text-slate-500">{footer}</div>}

      <div className="mt-4 flex gap-4 text-xs text-slate-500">
        <Link to="/legal/privacy" className="hover:text-slate-700">
          Privacy
        </Link>
        <Link to="/legal/terms" className="hover:text-slate-700">
          Terms
        </Link>
        <Link to="/legal/cookies" className="hover:text-slate-700">
          Cookies
        </Link>
      </div>
    </div>
  )
}
