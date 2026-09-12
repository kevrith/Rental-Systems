import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpDown, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, KeyRound, LogIn, LogOut, Search, ToggleLeft, ToggleRight } from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { errorMessage, humanize, relative, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const ROLE_TONE: Record<string, 'neutral' | 'info' | 'brand' | 'success' | 'warn' | 'danger'> = {
  system_admin: 'danger',
  owner: 'brand',
  agency_admin: 'brand',
  property_manager: 'info',
  caretaker: 'info',
  accountant: 'neutral',
  tenant: 'success',
  owner_portal_user: 'neutral',
}

const ROLES = [
  'owner',
  'agency_admin',
  'property_manager',
  'caretaker',
  'accountant',
  'tenant',
  'system_admin',
]

type SortKey = 'full_name' | 'organization_name' | 'role' | 'last_login_at' | 'created_at' | 'is_active'
type SortDir = 'asc' | 'desc'

export function UsersTab() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [toggling, setToggling] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [resetTarget, setResetTarget] = useState<string | null>(null)
  const [resetResult, setResetResult] = useState<{ reset_url: string; expires_at: string } | null>(null)
  const [impersonateResult, setImpersonateResult] = useState<{ access_token: string; target_user: { full_name: string; email: string; role: string } } | null>(null)
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 25

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ArrowUpDown className="ml-1 inline h-3 w-3 text-slate-400" />
    return sortDir === 'asc'
      ? <ChevronUp className="ml-1 inline h-3 w-3" />
      : <ChevronDown className="ml-1 inline h-3 w-3" />
  }

  const params = {
    search: search || undefined,
    role: roleFilter || undefined,
  }

  const users = useQuery({
    queryKey: queryKeys.internalUsers(params),
    queryFn: () => internalApi.allUsers(params),
  })

  const toggle = useMutation({
    mutationFn: (id: string) => internalApi.toggleUserActive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['internal', 'users'] })
      setToggling(null)
    },
  })

  const revokeSessions = useMutation({
    mutationFn: (id: string) => internalApi.revokeUserSessions(id),
  })

  const impersonate = useMutation({
    mutationFn: (id: string) => internalApi.impersonateUser(id),
    onSuccess: (data) => setImpersonateResult(data),
  })

  const resetPassword = useMutation({
    mutationFn: (id: string) => internalApi.resetUserPassword(id),
    onSuccess: (data) => setResetResult(data),
  })

  const allRows = [...(users.data ?? [])].sort((a, b) => {
    const av = a[sortKey] ?? ''
    const bv = b[sortKey] ?? ''
    const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true })
    return sortDir === 'asc' ? cmp : -cmp
  })
  const totalPages = Math.ceil(allRows.length / PAGE_SIZE)
  const rows = allRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Name, email or phone…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          />
        </div>
        <Select
          value={roleFilter}
          onChange={(e) => { setRoleFilter(e.target.value); setPage(0) }}
          className="w-44"
        >
          <option value="">All roles</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {humanize(r)}
            </option>
          ))}
        </Select>
      </div>

      {users.isPending ? (
        <PageLoader />
      ) : allRows.length === 0 ? (
        <EmptyState title="No users found" description="Try a different search or filter." />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  {(['full_name', 'organization_name', 'role', 'last_login_at', 'created_at', 'is_active'] as SortKey[]).map((col, i) => (
                    <Th key={col}>
                      <button
                        className="flex items-center gap-0.5 hover:text-slate-900 dark:hover:text-white"
                        onClick={() => handleSort(col)}
                      >
                        {['User', 'Organization', 'Role', 'Last login', 'Joined', 'Status'][i]}
                        <SortIcon col={col} />
                      </button>
                    </Th>
                  ))}
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <Td>
                      <p className="font-medium text-slate-900 dark:text-slate-100">
                        {user.full_name}
                      </p>
                      <p className="text-xs text-slate-400">{user.email}</p>
                      <p className="text-xs text-slate-400">{user.phone_number}</p>
                    </Td>
                    <Td>
                      <p className="text-sm text-slate-700 dark:text-slate-300">
                        {user.organization_name ?? '—'}
                      </p>
                      <p className="font-mono text-xs text-slate-400">
                        {user.organization_id.slice(0, 8)}…
                      </p>
                    </Td>
                    <Td>
                      <Badge tone={ROLE_TONE[user.role] ?? 'neutral'}>
                        {humanize(user.role)}
                      </Badge>
                    </Td>
                    <Td className="text-xs text-slate-500">
                      {user.last_login_at ? relative(user.last_login_at) : 'Never'}
                    </Td>
                    <Td className="text-xs text-slate-500">{shortDate(user.created_at)}</Td>
                    <Td>
                      {user.is_active ? (
                        <Badge tone="success">Active</Badge>
                      ) : (
                        <Badge tone="danger">Disabled</Badge>
                      )}
                    </Td>
                    <Td>
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={
                            user.is_active ? (
                              <ToggleRight className="h-4 w-4 text-success-600" />
                            ) : (
                              <ToggleLeft className="h-4 w-4 text-slate-400" />
                            )
                          }
                          loading={toggle.isPending && toggling === user.id}
                          onClick={() => {
                            setToggling(user.id)
                            toggle.mutate(user.id)
                          }}
                        >
                          {user.is_active ? 'Disable' : 'Enable'}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<KeyRound className="h-3.5 w-3.5" />}
                          loading={resetPassword.isPending && resetTarget === user.id}
                          onClick={() => {
                            setResetTarget(user.id)
                            resetPassword.mutate(user.id)
                          }}
                        >
                          Reset pwd
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<LogOut className="h-3.5 w-3.5 text-warn-500" />}
                          loading={revokeSessions.isPending}
                          onClick={() => revokeSessions.mutate(user.id)}
                          title="Revoke all sessions"
                        />
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<LogIn className="h-3.5 w-3.5 text-brand-500" />}
                          loading={impersonate.isPending}
                          onClick={() => {
                            if (confirm(`Sign in as ${user.full_name}? This will be logged in the audit trail.`)) {
                              impersonate.mutate(user.id)
                            }
                          }}
                          title="Sign in as this user"
                        />
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{allRows.length} users · page {page + 1} of {totalPages}</span>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}
              icon={<ChevronLeft className="h-3.5 w-3.5" />} />
            <Button size="sm" variant="ghost" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
              icon={<ChevronRight className="h-3.5 w-3.5" />} />
          </div>
        </div>
      )}

      {impersonateResult && (
        <Dialog open onClose={() => setImpersonateResult(null)} title="Impersonation session" size="sm">
          <div className="space-y-3">
            <div className="rounded-lg border border-warn-200 bg-warn-50 px-3 py-2 text-xs text-warn-700 dark:border-warn-800 dark:bg-warn-950 dark:text-warn-400">
              You are about to sign in as <strong>{impersonateResult.target_user.full_name}</strong> ({impersonateResult.target_user.role}).
              This session expires in 30 minutes and cannot be refreshed. The action is recorded in the audit log.
            </div>
            <p className="text-xs text-slate-500">Copy the token and use it as a Bearer token, or open the app in a private window and paste it into the browser console: <code>localStorage.setItem('access_token', '...')</code></p>
            <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700 dark:text-slate-300">
                {impersonateResult.access_token}
              </span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => navigator.clipboard.writeText(impersonateResult.access_token)}
              >
                Copy
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {resetResult && (
        <Dialog open onClose={() => setResetResult(null)} title="Password reset link" size="sm">
          <div className="space-y-3">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Share this link with the user. It expires at {shortDate(resetResult.expires_at)}.
            </p>
            <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700 dark:text-slate-300">
                {resetResult.reset_url}
              </span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => navigator.clipboard.writeText(resetResult.reset_url)}
              >
                Copy
              </Button>
            </div>
            {resetPassword.isError && (
              <Alert tone="danger">{errorMessage(resetPassword.error)}</Alert>
            )}
          </div>
        </Dialog>
      )}
    </div>
  )
}
