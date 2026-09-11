import { CreditCard, FileText, Home, LogOut, PenLine, Settings, Wrench } from 'lucide-react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { InstallPrompt } from '@/components/InstallPrompt'
import { useInactivityLogout } from '@/hooks/use-inactivity-logout'
import { cn } from '@/lib/cn'
import { useAuthStore } from '@/store/auth-store'

const TABS = [
  { to: '/portal', label: 'Home', icon: <Home className="h-5 w-5" />, end: true },
  { to: '/portal/payments', label: 'Payments', icon: <CreditCard className="h-5 w-5" /> },
  { to: '/portal/documents', label: 'Documents', icon: <FileText className="h-5 w-5" /> },
  { to: '/portal/maintenance', label: 'Requests', icon: <Wrench className="h-5 w-5" /> },
  { to: '/portal/signature', label: 'Signature', icon: <PenLine className="h-5 w-5" /> },
]

/**
 * The tenant portal shell (US-029).
 *
 * Phone-first with a bottom tab bar: a tenant opens this to do one of four
 * things, and every one of them is a thumb's reach away.
 */
export function PortalShell() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)

  useInactivityLogout()

  const logout = async () => {
    try {
      await authApi.logout(useAuthStore.getState().refreshToken)
    } catch {
      // The local session ends either way.
    }
    useAuthStore.getState().logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">
            {user?.full_name ?? 'My tenancy'}
          </p>
          <p className="text-xs text-slate-500">Tenant portal</p>
        </div>
        <div className="flex items-center gap-1">
          <Link
            to="/portal/privacy"
            aria-label="Privacy settings"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <Settings className="h-5 w-5" />
          </Link>
          <button
            type="button"
            onClick={logout}
            aria-label="Log out"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-danger-600"
          >
            <LogOut className="h-5 w-5" />
          </button>
        </div>
      </header>

      <main className="min-w-0 flex-1 px-4 py-5 pb-24">
        <Outlet />
      </main>

      <InstallPrompt />

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white pb-safe">
        <ul className="mx-auto flex max-w-lg">
          {TABS.map((tab) => (
            <li key={tab.to} className="flex-1">
              <NavLink
                to={tab.to}
                end={tab.end}
                data-touch-target
                className={({ isActive }) =>
                  cn(
                    'flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium transition-colors',
                    isActive ? 'text-brand-700' : 'text-slate-400 hover:text-slate-600',
                  )
                }
              >
                {tab.icon}
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )
}
