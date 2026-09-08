import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  Banknote,
  BarChart3,
  Bell,
  Briefcase,
  Building2,
  Car,
  ClipboardCheck,
  ClipboardList,
  Code2,
  DoorOpen,
  CreditCard,
  Eye,
  FileBarChart,
  FileEdit,
  FileSignature,
  FileText,
  Gauge,
  Gift,
  HeartPulse,
  HelpCircle,
  Layers,
  LayoutDashboard,
  LogOut,
  Menu,
  Receipt,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  ThumbsUp,
  Timer,
  TrendingUp,
  UserRound,
  UserSquare2,
  Users,
  HardHat,
  Wrench,
  X,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { notificationsApi, organizationApi } from '@/api'
import { authApi } from '@/api/auth'
import { SyncIndicator } from '@/components/SyncIndicator'
import { Badge, Button } from '@/components/ui'
import { CommandPalette } from '@/components/CommandPalette'
import { InstallPrompt } from '@/components/InstallPrompt'
import { ThemeToggle } from '@/components/ThemeToggle'
import { ChangelogWidget } from '@/features/success/ChangelogWidget'
import { HelpPanel } from '@/features/success/HelpPanel'
import { MilestoneCelebration } from '@/features/success/MilestoneCelebration'
import { NpsPopup } from '@/features/success/NpsPopup'
import { OnboardingWizard } from '@/features/success/OnboardingWizard'
import { useInactivityLogout } from '@/hooks/use-inactivity-logout'
import { cn } from '@/lib/cn'
import { initials } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore, type AuthOrganization } from '@/store/auth-store'
import { useCommandPaletteStore } from '@/store/command-palette-store'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  permission?: string
  /** Only shown when the account is in this operating mode. */
  mode?: 'agency' | 'owner'
  /** Only shown to these roles. Omit for everyone who passes the other checks. */
  roles?: string[]
}

const NAV_SECTIONS: { heading: string; items: NavItem[] }[] = [
  {
    heading: 'Overview',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard className="h-4 w-4" /> },
      {
        to: '/finances',
        label: 'Finances',
        icon: <BarChart3 className="h-4 w-4" />,
        permission: 'financials:view',
      },
      {
        to: '/analytics',
        label: 'Analytics',
        icon: <TrendingUp className="h-4 w-4" />,
        permission: 'financials:view',
      },
      {
        to: '/reports',
        label: 'Reports',
        icon: <FileBarChart className="h-4 w-4" />,
        permission: 'report:view',
      },
    ],
  },
  {
    heading: 'Portfolio',
    items: [
      {
        to: '/properties',
        label: 'Properties',
        icon: <Building2 className="h-4 w-4" />,
        permission: 'property:view',
      },
      {
        to: '/units',
        label: 'Units',
        icon: <ClipboardList className="h-4 w-4" />,
        permission: 'unit:view',
      },
    ],
  },
  {
    heading: 'Tenancy',
    items: [
      {
        to: '/tenants',
        label: 'Tenants',
        icon: <Users className="h-4 w-4" />,
        permission: 'tenant:view',
      },
      {
        to: '/vacancies',
        label: 'Vacancies',
        icon: <DoorOpen className="h-4 w-4" />,
        permission: 'unit:view',
      },
      {
        to: '/applications',
        label: 'Applications',
        icon: <ClipboardList className="h-4 w-4" />,
        permission: 'application:view',
      },
      {
        to: '/tenancies',
        label: 'Tenancies',
        icon: <FileText className="h-4 w-4" />,
        permission: 'tenancy:view',
      },
      {
        to: '/lease-templates',
        label: 'Lease templates',
        icon: <FileSignature className="h-4 w-4" />,
        permission: 'lease_template:manage',
      },
    ],
  },
  {
    heading: 'Money',
    items: [
      {
        to: '/payments',
        label: 'Payments',
        icon: <CreditCard className="h-4 w-4" />,
        permission: 'payment:view',
      },
      {
        to: '/invoices',
        label: 'Invoices',
        icon: <Receipt className="h-4 w-4" />,
        permission: 'invoice:view',
      },
      {
        to: '/arrears',
        label: 'Arrears',
        icon: <AlertTriangle className="h-4 w-4" />,
        permission: 'arrears:view',
      },
      {
        to: '/security/fraud-alerts',
        label: 'Fraud alerts',
        icon: <ShieldAlert className="h-4 w-4" />,
        permission: 'fraud:view',
      },
      {
        to: '/approvals',
        label: 'Approvals',
        icon: <ClipboardCheck className="h-4 w-4" />,
        permission: 'approval:view',
      },
    ],
  },
  {
    heading: 'Operations',
    items: [
      {
        to: '/maintenance',
        label: 'Maintenance',
        icon: <Wrench className="h-4 w-4" />,
        permission: 'maintenance:view',
      },
      {
        to: '/fleet',
        label: 'Fleet',
        icon: <Car className="h-4 w-4" />,
        permission: 'property:view',
      },
      {
        to: '/vendors',
        label: 'Vendors',
        icon: <HardHat className="h-4 w-4" />,
        permission: 'vendor:view',
      },
      {
        to: '/compliance',
        label: 'Compliance',
        icon: <ShieldCheck className="h-4 w-4" />,
        permission: 'property:view',
      },
      {
        to: '/inspections',
        label: 'Inspections',
        icon: <ClipboardCheck className="h-4 w-4" />,
        permission: 'property:view',
      },
      {
        to: '/meter-readings',
        label: 'Meter readings',
        icon: <Gauge className="h-4 w-4" />,
        permission: 'meter_reading:view',
      },
      {
        to: '/visitor-log',
        label: 'Visitor log',
        icon: <UserRound className="h-4 w-4" />,
        permission: 'visitor_log:view',
      },
      {
        to: '/bulk',
        label: 'Bulk actions',
        icon: <Layers className="h-4 w-4" />,
        permission: 'tenancy:manage',
      },
    ],
  },
  {
    heading: 'Agency',
    items: [
      {
        to: '/agency',
        label: 'Portfolio',
        icon: <Briefcase className="h-4 w-4" />,
        mode: 'agency',
        permission: 'dashboard:view',
      },
      {
        to: '/agency/owners',
        label: 'Owner clients',
        icon: <UserSquare2 className="h-4 w-4" />,
        mode: 'agency',
        permission: 'financials:view',
      },
      {
        to: '/agency/disbursements',
        label: 'Disbursements',
        icon: <Banknote className="h-4 w-4" />,
        mode: 'agency',
        permission: 'financials:view',
      },
      {
        to: '/owner-portal',
        label: 'My portfolio',
        icon: <Eye className="h-4 w-4" />,
        roles: ['owner_portal_user'],
      },
    ],
  },
  {
    heading: 'Account',
    items: [
      {
        to: '/team',
        label: 'Team',
        icon: <Users className="h-4 w-4" />,
        permission: 'user:view',
      },
      {
        to: '/team/performance',
        label: 'Caretaker scores',
        icon: <Gauge className="h-4 w-4" />,
        permission: 'user:view',
      },
      {
        to: '/automation',
        label: 'Automation',
        icon: <Timer className="h-4 w-4" />,
        permission: 'org:manage',
      },
      {
        to: '/developer',
        label: 'Developer',
        icon: <Code2 className="h-4 w-4" />,
        permission: 'api_key:manage',
      },
      {
        to: '/referrals',
        label: 'Referrals',
        icon: <Gift className="h-4 w-4" />,
        permission: 'org:manage',
      },
      { to: '/feedback', label: 'Feature requests', icon: <ThumbsUp className="h-4 w-4" /> },
      { to: '/settings', label: 'Settings', icon: <Settings className="h-4 w-4" /> },
    ],
  },
]

// RentFlow's own team, not a tenant role — shown only to `is_platform_staff`
// accounts, filtered separately from the permission/mode/role checks above.
const STAFF_ONLY_SECTION: { heading: string; items: NavItem[] } = {
  heading: 'RentFlow staff',
  items: [
    { to: '/internal/health', label: 'Customer health', icon: <HeartPulse className="h-4 w-4" /> },
    { to: '/internal/content', label: 'Content', icon: <FileEdit className="h-4 w-4" /> },
  ],
}

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const setOrganization = useAuthStore((state) => state.setOrganization)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  useInactivityLogout()

  const organization = useQuery({
    queryKey: queryKeys.organization,
    queryFn: organizationApi.me,
    staleTime: 5 * 60_000,
  })

  const unread = useQuery({
    queryKey: queryKeys.unreadCount,
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 60_000,
  })

  useEffect(() => {
    if (organization.data) setOrganization(organization.data as unknown as AuthOrganization)
  }, [organization.data, setOrganization])

  // A route change on mobile should close the drawer, not leave it covering the page.
  useEffect(() => setMobileNavOpen(false), [location.pathname])

  const handleLogout = async () => {
    const { refreshToken } = useAuthStore.getState()
    try {
      await authApi.logout(refreshToken)
    } catch {
      // Even if the server call fails, the local session must end.
    }
    useAuthStore.getState().logout()
    navigate('/login', { replace: true })
  }

  const org = organization.data as unknown as AuthOrganization | undefined

  // A read-only owner sees only their own portfolio and their own settings —
  // every operational screen belongs to the agency, not to them.
  const isPortalOwner = user?.role === 'owner_portal_user'

  const visibleSections = [...NAV_SECTIONS, ...(user?.is_platform_staff ? [STAFF_ONLY_SECTION] : [])]
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (item.permission && !user?.permissions?.includes(item.permission)) return false
        if (item.mode && org?.operating_mode !== item.mode) return false
        if (item.roles && !item.roles.includes(user?.role ?? '')) return false
        if (isPortalOwner && item.to !== '/owner-portal' && item.to !== '/settings') return false
        return true
      }),
    }))
    .filter((section) => section.items.length > 0)

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex dark:border-slate-800 dark:bg-slate-900">
        <Brand />
        <NavList sections={visibleSections} />
        <UserFooter onLogout={handleLogout} />
      </aside>

      {/* Mobile drawer */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40 dark:bg-black/60"
            onClick={() => setMobileNavOpen(false)}
            aria-hidden
          />
          <aside className="relative flex h-full w-72 flex-col bg-white shadow-xl dark:bg-slate-900">
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
              <Brand compact orgName={org?.name} />
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <NavList sections={visibleSections} />
            <UserFooter onLogout={handleLogout} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-1 border-b border-slate-200 bg-white px-2 py-3 sm:gap-3 sm:px-4 dark:border-slate-800 dark:bg-slate-900">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open navigation"
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 sm:p-2 lg:hidden dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <Menu className="h-5 w-5" />
          </button>

          <div className="hidden min-w-0 flex-1 sm:block">
            <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
              {org?.name ?? 'RentFlow'}
            </p>
            {org?.is_trial && (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {org.is_trial_expired
                  ? 'Trial ended'
                  : `Trial · ${org.trial_days_remaining ?? 0} day(s) left`}
              </p>
            )}
          </div>

          <div className="flex-1 sm:hidden" aria-hidden />

          <button
            type="button"
            onClick={() => useCommandPaletteStore.getState().setOpen(true)}
            className="hidden items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-400 hover:bg-slate-50 sm:flex dark:border-slate-700 dark:hover:bg-slate-800"
            aria-label="Search"
          >
            <Search className="h-3.5 w-3.5" />
            Search
            <kbd className="rounded border border-slate-200 px-1 text-[10px] dark:border-slate-700">⌘K</kbd>
          </button>
          <button
            type="button"
            onClick={() => useCommandPaletteStore.getState().setOpen(true)}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 sm:hidden dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Search"
          >
            <Search className="h-5 w-5" />
          </button>

          <SyncIndicator compact />

          <button
            type="button"
            onClick={() => setHelpOpen(true)}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 sm:p-2 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Help"
          >
            <HelpCircle className="h-5 w-5" />
          </button>

          <ThemeToggle />

          <ChangelogWidget />

          <Link
            to="/notifications"
            className="relative rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 sm:p-2 dark:text-slate-400 dark:hover:bg-slate-800"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
            {(unread.data?.unread ?? 0) > 0 && (
              <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger-600 px-1 text-[10px] font-semibold text-white">
                {unread.data!.unread > 9 ? '9+' : unread.data!.unread}
              </span>
            )}
          </Link>
        </header>

        <TrialBanner organization={org} />

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>

      <HelpPanel open={helpOpen} onClose={() => setHelpOpen(false)} />
      <OnboardingWizard />
      <NpsPopup />
      <MilestoneCelebration />
      <InstallPrompt />
      <CommandPalette />
    </div>
  )
}

function Brand({ compact = false, orgName }: { compact?: boolean; orgName?: string }) {
  return (
    <div
      className={cn(
        'flex min-w-0 items-center gap-2',
        !compact && 'border-b border-slate-100 px-5 py-4 dark:border-slate-800',
      )}
    >
      <img src="/rent.png" alt="RentFlow" className="h-8 w-8 shrink-0 rounded-lg" />
      <span className="min-w-0">
        <span className="block font-semibold text-slate-900 dark:text-slate-100">RentFlow</span>
        {orgName && (
          <span className="block truncate text-xs text-slate-500 dark:text-slate-400">{orgName}</span>
        )}
      </span>
    </div>
  )
}

function NavList({ sections }: { sections: { heading: string; items: NavItem[] }[] }) {
  return (
    <nav className="flex-1 overflow-y-auto px-3 py-4">
      {sections.map((section) => (
        <div key={section.heading} className="mb-5">
          <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {section.heading}
          </p>
          <ul className="space-y-0.5">
            {section.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                      isActive
                        ? 'bg-brand-50 font-medium text-brand-700 dark:bg-brand-900/30 dark:text-brand-300'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
                    )
                  }
                >
                  {item.icon}
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function UserFooter({ onLogout }: { onLogout: () => void }) {
  const user = useAuthStore((state) => state.user)

  return (
    <div className="border-t border-slate-100 p-3 dark:border-slate-800">
      <Link
        to="/settings/profile"
        className="flex items-center gap-2.5 rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
          {initials(user?.full_name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-slate-900 dark:text-slate-100">
            {user?.full_name}
          </span>
          <span className="block truncate text-xs capitalize text-slate-500 dark:text-slate-400">
            {user?.role?.replace(/_/g, ' ')}
          </span>
        </span>
      </Link>
      <button
        type="button"
        onClick={onLogout}
        className="mt-1 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-danger-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-danger-400"
      >
        <LogOut className="h-4 w-4" />
        Log out
      </button>
    </div>
  )
}

/** Trial countdown and the read-only notice once it lapses (US-006). */
function TrialBanner({ organization }: { organization?: AuthOrganization }) {
  if (!organization?.is_trial) return null

  if (organization.is_trial_expired) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-danger-100 bg-danger-50 px-4 py-2.5 sm:px-6">
        <p className="text-sm text-danger-700">
          <span className="font-medium">Your free trial has ended.</span> Your data is safe and fully
          visible, but you cannot add or change anything until you upgrade.
        </p>
        <Button size="sm" variant="danger" onClick={() => undefined}>
          Upgrade plan
        </Button>
      </div>
    )
  }

  const days = organization.trial_days_remaining ?? 0
  if (days > 7) return null

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-warn-100 bg-warn-50 px-4 py-2.5 sm:px-6">
      <p className="text-sm text-warn-700">
        <Badge tone="warn" className="mr-2">
          {days} day{days === 1 ? '' : 's'} left
        </Badge>
        Your free trial ends soon. Upgrade to keep adding properties, tenants and payments.
      </p>
      <Button size="sm" variant="secondary" onClick={() => undefined}>
        See plans
      </Button>
    </div>
  )
}
