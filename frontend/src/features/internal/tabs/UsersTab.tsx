import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, ToggleLeft, ToggleRight } from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { humanize, relative, shortDate } from '@/lib/format'
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

export function UsersTab() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [toggling, setToggling] = useState<string | null>(null)

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

  const rows = users.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Name, email or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
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
      ) : rows.length === 0 ? (
        <EmptyState title="No users found" description="Try a different search or filter." />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  <Th>User</Th>
                  <Th>Organization</Th>
                  <Th>Role</Th>
                  <Th>Last login</Th>
                  <Th>Joined</Th>
                  <Th>Status</Th>
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
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
