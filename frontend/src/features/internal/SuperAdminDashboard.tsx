import {
  AlertOctagon,
  Building2,
  FileEdit,
  LayoutDashboard,
  ScrollText,
  ShieldAlert,
  Users,
} from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '@/components/PageHeader'
import { useAuthStore } from '@/store/auth-store'

import { AuditLogTab } from './tabs/AuditLogTab'
import { BreachRegisterTab } from './tabs/BreachRegisterTab'
import { ContentTab } from './tabs/ContentTab'
import { OrganizationsTab } from './tabs/OrganizationsTab'
import { OverviewTab } from './tabs/OverviewTab'
import { UsersTab } from './tabs/UsersTab'

type TabId = 'overview' | 'organizations' | 'users' | 'breaches' | 'audit' | 'content'

const NAV: {
  id: TabId
  label: string
  icon: React.ReactNode
  description: string
}[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: <LayoutDashboard className="h-4 w-4" />,
    description: 'Platform-wide stats',
  },
  {
    id: 'organizations',
    label: 'Organizations',
    icon: <Building2 className="h-4 w-4" />,
    description: 'All accounts, plans & health',
  },
  {
    id: 'users',
    label: 'Users',
    icon: <Users className="h-4 w-4" />,
    description: 'Cross-tenant user management',
  },
  {
    id: 'breaches',
    label: 'Breach register',
    icon: <AlertOctagon className="h-4 w-4" />,
    description: 'Kenya DPA incident log',
  },
  {
    id: 'audit',
    label: 'Audit log',
    icon: <ScrollText className="h-4 w-4" />,
    description: 'Chain integrity & export',
  },
  {
    id: 'content',
    label: 'Content',
    icon: <FileEdit className="h-4 w-4" />,
    description: 'Help articles & changelog',
  },
]

export function SuperAdminDashboard() {
  const [tab, setTab] = useState<TabId>('overview')
  const user = useAuthStore((s) => s.user)
  const active = NAV.find((n) => n.id === tab)!

  return (
    <div className="min-h-screen">
      <PageHeader
        title="Platform administration"
        description={`Signed in as ${user?.full_name ?? 'staff'} · cross-tenant access`}
        actions={
          <div className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-400">
            <ShieldAlert className="h-3.5 w-3.5" />
            Staff only — all actions are audited
          </div>
        }
      />

      <div className="flex gap-6">
        {/* Sidebar */}
        <aside className="hidden w-56 shrink-0 lg:block">
          <nav className="sticky top-6 space-y-0.5 rounded-xl border border-slate-200 bg-white p-2 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            {NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                  tab === item.id
                    ? 'bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300'
                    : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800'
                }`}
              >
                <span className="mt-0.5 shrink-0">{item.icon}</span>
                <span>
                  <span className="block text-sm font-medium">{item.label}</span>
                  <span className="block text-xs opacity-70">{item.description}</span>
                </span>
              </button>
            ))}
          </nav>
        </aside>

        {/* Mobile tab strip */}
        <div className="mb-4 flex gap-1 overflow-x-auto lg:hidden">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                tab === item.id
                  ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300'
                  : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400'
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <main className="min-w-0 flex-1">
          <div className="mb-4 flex items-center gap-2 border-b border-slate-200 pb-3 dark:border-slate-700">
            <span className="text-slate-500 dark:text-slate-400">{active.icon}</span>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">
              {active.label}
            </h2>
            <span className="text-xs text-slate-400">{active.description}</span>
          </div>

          {tab === 'overview' && <OverviewTab />}
          {tab === 'organizations' && <OrganizationsTab />}
          {tab === 'users' && <UsersTab />}
          {tab === 'breaches' && <BreachRegisterTab />}
          {tab === 'audit' && <AuditLogTab />}
          {tab === 'content' && <ContentTab />}
        </main>
      </div>
    </div>
  )
}
