import { Link } from 'react-router-dom'

import { linkButtonClass } from '@/components/ui'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50 px-4 text-center">
      <p className="text-5xl font-semibold text-slate-300">404</p>
      <h1 className="text-lg font-semibold text-slate-900">Page not found</h1>
      <p className="max-w-sm text-sm text-slate-500">
        The page you were looking for doesn&apos;t exist, or you no longer have access to it.
      </p>
      <Link to="/dashboard" className={`${linkButtonClass()} mt-2`}>
        Go to dashboard
      </Link>
    </div>
  )
}
