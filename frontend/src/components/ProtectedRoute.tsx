import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { PageLoader } from '@/components/ui'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

/**
 * Gate for every authenticated route.
 *
 * Holding a token is not the same as knowing who you are: the profile carries
 * the permission list that drives navigation and per-page guards, so it is
 * fetched before anything renders.
 */
export function ProtectedRoute({
  requirePermission,
  allowRoles,
  requirePlatformStaff = false,
  redirectTo = '/login',
}: {
  requirePermission?: string
  allowRoles?: string[]
  /** RentFlow's own team, not a tenant role — see `app.api.deps.require_platform_staff`. */
  requirePlatformStaff?: boolean
  redirectTo?: string
}) {
  const location = useLocation()
  const accessToken = useAuthStore((state) => state.accessToken)
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)

  const profile = useQuery({
    queryKey: queryKeys.me,
    queryFn: authApi.me,
    enabled: Boolean(accessToken),
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    if (profile.data) setUser(profile.data)
  }, [profile.data, setUser])

  if (!accessToken) {
    return <Navigate to={redirectTo} replace state={{ from: location.pathname }} />
  }

  // No cached profile and none loaded yet — wait rather than flashing a denial.
  if (!user && profile.isPending) {
    return <PageLoader />
  }

  if (profile.isError && !user) {
    return <Navigate to={redirectTo} replace />
  }

  const current = profile.data ?? user

  if (allowRoles && current && !allowRoles.includes(current.role)) {
    // Tenants get their own shell; staff should never land in it, and vice versa.
    return <Navigate to={current.role === 'tenant' ? '/portal' : '/dashboard'} replace />
  }

  if (requirePermission && current && !current.permissions?.includes(requirePermission)) {
    return <Navigate to="/dashboard" replace />
  }

  if (requirePlatformStaff && current && !current.is_platform_staff) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
