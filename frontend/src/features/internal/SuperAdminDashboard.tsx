import { useState } from 'react'
import {
  AlertOctagon,
  Building2,
  FileEdit,
  ScrollText,
  ShieldAlert,
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { useAuthStore } from '@/store/auth-store'

import { OrganizationsTab } from './tabs/OrganizationsTab'
import { BreachRegisterTab } from './tabs/BreachRegisterTab'
import { AuditLogTab } from './tabs/AuditLogTab'
import { ContentTab } from './tabs/ContentTab'

type TabId = 'organizations' | 'breaches' | 'audit' | 'content'

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'organizations', label: 'Organizations', icon: <Building2 className="h-4 w-4" /> },
  { id: 'breaches', label: 'Breach register', icon: <AlertOctagon className="h-4 w-4" /> },
  { id: 'audit', label: 'Audit log', icon: <ScrollText className="h-4 w-4" /> },
  { id: 'content', label: 'Content', icon: <FileEdit className="h-4 w-4" /> },
]

export function SuperAdminDashboard() {
  const [tab, setTab] = useState<TabId>('organizations')
  const user = useAuthStore((s) => s.user)

  return (
    <div>
      <PageHeader
        title="Platform administration"
        description={`Signed in as ${user?.full_name ?? 'staff'} · cross-tenant access`}
        actions={
          <div className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-400">
            <ShieldAlert className="h-3.5 w-3.5" />
            Staff only
          </div>
        }
      />

      <div className="mb-1 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-left text-sm font-medium transition-colors ${
              tab === t.id
                ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'organizations' && <OrganizationsTab />}
        {tab === 'breaches' && <BreachRegisterTab />}
        {tab === 'audit' && <AuditLogTab />}
        {tab === 'content' && <ContentTab />}
      </div>
    </div>
  )
}
