import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, Copy, MessageCircle, Send, UserCog, UserPlus, X } from 'lucide-react'
import { useState } from 'react'

import { propertiesApi, teamApi } from '@/api'
import type { TeamMember } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { dateTime, errorMessage, humanize, initials, kes, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

const INVITABLE_ROLES = [
  { value: 'caretaker', label: 'Caretaker', hint: 'Records payments, readings and maintenance on assigned properties.' },
  { value: 'property_manager', label: 'Property manager', hint: 'Full day-to-day operations across the portfolio.' },
  { value: 'accountant', label: 'Accountant', hint: 'Read-only on operations, full access to money.' },
]

export function TeamPage() {
  const [inviteOpen, setInviteOpen] = useState(false)
  const [accessFor, setAccessFor] = useState<TeamMember | null>(null)
  const queryClient = useQueryClient()

  const canInvite = useAuthStore((state) => state.user?.permissions?.includes('user:invite'))
  const canManage = useAuthStore((state) => state.user?.permissions?.includes('user:manage'))

  const team = useQuery({ queryKey: queryKeys.team, queryFn: teamApi.list })
  const invitations = useQuery({ queryKey: queryKeys.invitations, queryFn: teamApi.invitations })
  const properties = useQuery({
    queryKey: queryKeys.properties({ forTeam: true }),
    queryFn: () => propertiesApi.list(),
  })

  const revoke = useMutation({
    mutationFn: (id: string) => teamApi.revokeInvitation(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.invitations }),
  })

  if (team.isPending) return <PageLoader />

  const propertyName = (id: string) =>
    properties.data?.find((property) => property.id === id)?.name ?? 'Unknown property'

  return (
    <div>
      <PageHeader
        title="Team"
        description="Who works in your account, and what they can reach."
        actions={
          canInvite && (
            <Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setInviteOpen(true)}>
              Invite someone
            </Button>
          )
        }
      />

      {invitations.data && invitations.data.length > 0 && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle>Pending invitations</CardTitle>
          </CardHeader>
          <ul className="divide-y divide-slate-100">
            {invitations.data.map((invitation) => (
              <PendingInvitationRow
                key={invitation.id}
                invitation={invitation}
                canInvite={!!canInvite}
                revoking={revoke.isPending}
                onRevoke={() => revoke.mutate(invitation.id)}
              />
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
        </CardHeader>
        {team.data?.length ? (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Role</Th>
                <Th>Properties</Th>
                <Th>Cash limit</Th>
                <Th>Last login</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {team.data.map((member) => (
                <tr key={member.id} className="hover:bg-slate-50">
                  <Td>
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                        {initials(member.full_name)}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">{member.full_name}</p>
                        <p className="truncate text-xs text-slate-400">{member.phone_number}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <Badge tone={member.role === 'caretaker' ? 'info' : 'brand'}>
                      {humanize(member.role)}
                    </Badge>
                  </Td>
                  <Td className="text-slate-600">
                    {member.role === 'caretaker' ? (
                      member.assigned_property_ids.length ? (
                        <span className="text-xs">
                          {member.assigned_property_ids.map(propertyName).join(', ')}
                        </span>
                      ) : (
                        <span className="text-xs text-warn-700">No properties assigned</span>
                      )
                    ) : (
                      <span className="text-xs text-slate-400">All properties</span>
                    )}
                  </Td>
                  <Td className="text-slate-600">
                    {member.cash_limit != null ? kes(member.cash_limit) : '—'}
                  </Td>
                  <Td className="text-slate-600">
                    {member.last_login_at ? relative(member.last_login_at) : 'Never'}
                  </Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      {!member.is_active && <Badge tone="danger">Disabled</Badge>}
                      {canManage && (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<UserCog className="h-3.5 w-3.5" />}
                          onClick={() => setAccessFor(member)}
                        >
                          Access
                        </Button>
                      )}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState title="Just you so far" description="Invite a caretaker to help you run things." />
        )}
      </Card>

      <InviteDialog open={inviteOpen} onClose={() => setInviteOpen(false)} />
      {accessFor && (
        <AccessDialog member={accessFor} onClose={() => setAccessFor(null)} />
      )}
    </div>
  )
}

function PendingInvitationRow({
  invitation,
  canInvite,
  revoking,
  onRevoke,
}: {
  invitation: import('@/api/types').Invitation
  canInvite: boolean
  revoking: boolean
  onRevoke: () => void
}) {
  const [copied, setCopied] = useState(false)
  const link = invitation.invite_link
  const waPhone = invitation.phone_number.replace('+', '')
  const waText = `Hi ${invitation.full_name}, here is your RentFlow setup link: ${link}`

  return (
    <li className="space-y-2 px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900">{invitation.full_name}</p>
          <p className="text-xs text-slate-500">
            {invitation.phone_number} · {humanize(invitation.role)} · expires{' '}
            {dateTime(invitation.expires_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="warn">
            <Clock className="h-3 w-3" />
            Pending
          </Badge>
          {canInvite && (
            <Button
              variant="ghost"
              size="sm"
              icon={<X className="h-3.5 w-3.5" />}
              loading={revoking}
              onClick={onRevoke}
            >
              Revoke
            </Button>
          )}
        </div>
      </div>
      {link && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-600">{link}</span>
          <Button
            variant="ghost"
            size="sm"
            icon={<Copy className="h-3.5 w-3.5" />}
            onClick={() => {
              void navigator.clipboard.writeText(link)
              setCopied(true)
              setTimeout(() => setCopied(false), 2000)
            }}
          >
            {copied ? 'Copied!' : 'Copy'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<MessageCircle className="h-3.5 w-3.5" />}
            onClick={() =>
              window.open(
                `https://wa.me/${waPhone}?text=${encodeURIComponent(waText)}`,
                '_blank',
              )
            }
          >
            WhatsApp
          </Button>
        </div>
      )}
    </li>
  )
}

function InviteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('caretaker')
  const [propertyIds, setPropertyIds] = useState<string[]>([])
  const [cashLimit, setCashLimit] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [inviteLink, setInviteLink] = useState<string | null>(null)
  const [invitePhone, setInvitePhone] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const properties = useQuery({
    queryKey: queryKeys.properties({ forInvite: true }),
    queryFn: () => propertiesApi.list(),
    enabled: open,
  })

  const invite = useMutation({
    mutationFn: () =>
      teamApi.invite({
        full_name: fullName,
        phone_number: phone,
        email: email || null,
        role,
        property_ids: role === 'caretaker' ? propertyIds : [],
        cash_limit: cashLimit ? Number(cashLimit) : null,
      }),
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.invitations })
      setInviteLink(data.invite_link ?? null)
      setInvitePhone(data.phone_number)
      setSent(true)
    },
    onError: (inviteError) => setError(errorMessage(inviteError)),
  })

  const close = () => {
    setSent(false)
    setInviteLink(null)
    setInvitePhone(null)
    setCopied(false)
    setFullName('')
    setPhone('')
    setEmail('')
    setPropertyIds([])
    setCashLimit('')
    setError(null)
    onClose()
  }

  const selectedRole = INVITABLE_ROLES.find((entry) => entry.value === role)

  return (
    <Dialog
      open={open}
      onClose={close}
      title={sent ? 'Invitation sent' : 'Invite someone to your team'}
      description={
        sent
          ? undefined
          : 'They get an SMS with a one-click link to set their own password.'
      }
      footer={
        sent ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              icon={<Send className="h-4 w-4" />}
              disabled={!fullName || !phone}
              loading={invite.isPending}
              onClick={() => {
                setError(null)
                invite.mutate()
              }}
            >
              Send invitation
            </Button>
          </>
        )
      }
    >
      {sent ? (
        <div className="space-y-3">
          <Alert tone="success">
            {fullName} has been sent a setup link by SMS. It expires in 7 days.
          </Alert>
          {inviteLink && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">Share the link manually if SMS didn't arrive:</p>
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-700">
                  {inviteLink}
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Copy className="h-3.5 w-3.5" />}
                  onClick={() => {
                    void navigator.clipboard.writeText(inviteLink)
                    setCopied(true)
                    setTimeout(() => setCopied(false), 2000)
                  }}
                >
                  {copied ? 'Copied!' : 'Copy link'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<MessageCircle className="h-3.5 w-3.5" />}
                  onClick={() =>
                    window.open(
                      `https://wa.me/${(invitePhone ?? '').replace('+', '')}?text=${encodeURIComponent(`Hi ${fullName}, here is your RentFlow setup link: ${inviteLink}`)}`,
                      '_blank',
                    )
                  }
                >
                  Send via WhatsApp
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <Field label="Full name" required>
            <Input
              placeholder="John Kamau"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </Field>

          <Field label="Phone number" required hint="The invitation link is sent here.">
            <Input
              type="tel"
              placeholder="0712 345 678"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </Field>

          <Field label="Email">
            <Input
              type="email"
              placeholder="john@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>

          <Field label="Role" hint={selectedRole?.hint}>
            <Select value={role} onChange={(event) => setRole(event.target.value)}>
              {INVITABLE_ROLES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
          </Field>

          {role === 'caretaker' && (
            <>
              <Field
                label="Assigned properties"
                hint="A caretaker sees only what you assign them here."
              >
                <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                  {properties.data?.length ? (
                    properties.data.map((property) => (
                      <label
                        key={property.id}
                        className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50"
                      >
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-brand-600"
                          checked={propertyIds.includes(property.id)}
                          onChange={(event) =>
                            setPropertyIds((current) =>
                              event.target.checked
                                ? [...current, property.id]
                                : current.filter((id) => id !== property.id),
                            )
                          }
                        />
                        {property.name}
                      </label>
                    ))
                  ) : (
                    <p className="px-2 py-1.5 text-sm text-slate-500">
                      Add a property first, then assign it.
                    </p>
                  )}
                </div>
              </Field>

              <Field
                label="Cash limit (KES)"
                hint="Payments above this trigger an alert to you. Leave blank for no limit."
              >
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="20000"
                  value={cashLimit}
                  onChange={(event) => setCashLimit(event.target.value)}
                />
              </Field>
            </>
          )}

          {error && <Alert tone="danger">{error}</Alert>}
        </div>
      )}
    </Dialog>
  )
}

function AccessDialog({ member, onClose }: { member: TeamMember; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [isActive, setIsActive] = useState(member.is_active)
  const [propertyIds, setPropertyIds] = useState<string[]>(member.assigned_property_ids)
  const [cashLimit, setCashLimit] = useState(member.cash_limit?.toString() ?? '')
  const [error, setError] = useState<string | null>(null)

  const properties = useQuery({
    queryKey: queryKeys.properties({ forAccess: true }),
    queryFn: () => propertiesApi.list(),
  })

  const update = useMutation({
    mutationFn: () =>
      teamApi.updateAccess(member.id, {
        is_active: isActive,
        property_ids: member.role === 'caretaker' ? propertyIds : undefined,
        cash_limit: cashLimit ? Number(cashLimit) : null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.team })
      onClose()
    },
    onError: (updateError) => setError(errorMessage(updateError)),
  })

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Access for ${member.full_name}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={update.isPending}
            onClick={() => {
              setError(null)
              update.mutate()
            }}
          >
            Save access
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 accent-brand-600"
            checked={isActive}
            onChange={(event) => setIsActive(event.target.checked)}
          />
          <span>
            Account active
            <span className="block text-xs text-slate-500">
              Disabling signs them out of every device immediately.
            </span>
          </span>
        </label>

        {member.role === 'caretaker' && (
          <>
            <Field label="Assigned properties">
              <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                {properties.data?.map((property) => (
                  <label
                    key={property.id}
                    className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand-600"
                      checked={propertyIds.includes(property.id)}
                      onChange={(event) =>
                        setPropertyIds((current) =>
                          event.target.checked
                            ? [...current, property.id]
                            : current.filter((id) => id !== property.id),
                        )
                      }
                    />
                    {property.name}
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Cash limit (KES)">
              <Input
                type="number"
                step="0.01"
                min="0"
                value={cashLimit}
                onChange={(event) => setCashLimit(event.target.value)}
              />
            </Field>
          </>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </div>
    </Dialog>
  )
}
