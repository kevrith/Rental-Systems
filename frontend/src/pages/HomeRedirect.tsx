import { Navigate } from 'react-router-dom'

import { PageLoader } from '@/components/ui'
import { useAuthStore } from '@/store/auth-store'

/**
 * Sends each role to the home screen that is actually useful to them.
 *
 * A caretaker's day is a task list, not a financial dashboard — routing both to
 * the same `/dashboard` would make one of them wrong for everybody.
 */
export function HomeRedirect() {
  const user = useAuthStore((state) => state.user)

  if (!user) return <PageLoader />

  if (user.role === 'tenant') return <Navigate to="/portal" replace />
  if (user.role === 'caretaker') return <Navigate to="/today" replace />
  // A portal owner is read-only on their own properties — the staff dashboard
  // aggregates the whole agency, which is not theirs to see.
  if (user.role === 'owner_portal_user') return <Navigate to="/owner-portal" replace />
  if (user.role === 'agency_admin') return <Navigate to="/agency" replace />
  return <Navigate to="/overview" replace />
}
