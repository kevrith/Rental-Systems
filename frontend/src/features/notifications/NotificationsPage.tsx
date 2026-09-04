import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, BellOff, BellRing, Check, MessageSquare, Send, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { notificationsApi, pushApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { dateTime, errorMessage, humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const CHANNEL_ICONS: Record<string, React.ReactNode> = {
  whatsapp: <MessageSquare className="h-3.5 w-3.5" />,
  sms: <Send className="h-3.5 w-3.5" />,
  push: <Smartphone className="h-3.5 w-3.5" />,
  in_app: <Bell className="h-3.5 w-3.5" />,
  email: <Send className="h-3.5 w-3.5" />,
}

const STATUS_TONE: Record<string, 'success' | 'warn' | 'danger' | 'neutral'> = {
  sent: 'success',
  delivered: 'success',
  queued: 'warn',
  failed: 'danger',
  skipped: 'neutral',
}

export function NotificationsPage() {
  const queryClient = useQueryClient()
  const [unreadOnly, setUnreadOnly] = useState(false)

  const notifications = useQuery({
    queryKey: queryKeys.notifications({ unreadOnly }),
    queryFn: () => notificationsApi.list({ unread_only: unreadOnly, limit: 100 }),
  })

  const markAllRead = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Notifications"
        description="Everything the system has sent you, and whether it arrived."
        actions={
          <Button
            variant="outline"
            icon={<Check className="h-4 w-4" />}
            loading={markAllRead.isPending}
            onClick={() => markAllRead.mutate()}
          >
            Mark all read
          </Button>
        }
      />

      <PushEnrollment />

      <div className="mb-4">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 accent-brand-600"
            checked={unreadOnly}
            onChange={(event) => setUnreadOnly(event.target.checked)}
          />
          Show unread only
        </label>
      </div>

      <Card>
        {notifications.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-14" />
            ))}
          </div>
        ) : notifications.data?.length ? (
          <ul className="divide-y divide-slate-100">
            {notifications.data.map((notification) => (
              <li
                key={notification.id}
                className={cn('px-5 py-3', !notification.read_at && 'bg-brand-50/40')}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{notification.title}</p>
                    <p className="mt-0.5 whitespace-pre-wrap text-sm text-slate-600">
                      {notification.body}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <span className="inline-flex items-center gap-1">
                        {CHANNEL_ICONS[notification.channel]}
                        {humanize(notification.channel)}
                      </span>
                      <span>·</span>
                      <span>{dateTime(notification.created_at)}</span>
                      {notification.link_path && (
                        <>
                          <span>·</span>
                          <Link to={notification.link_path} className="text-brand-600 hover:underline">
                            Open
                          </Link>
                        </>
                      )}
                    </div>
                    {notification.error && (
                      <p className="mt-1 text-xs text-danger-600">{notification.error}</p>
                    )}
                  </div>
                  <Badge tone={STATUS_TONE[notification.status] ?? 'neutral'}>
                    {humanize(notification.status)}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Bell className="h-6 w-6" />}
            title={unreadOnly ? 'Nothing unread' : 'No notifications yet'}
            description="Payment confirmations, reminders and alerts show up here."
          />
        )}
      </Card>
    </div>
  )
}

/** VAPID keys arrive base64url-encoded; PushManager wants raw bytes. */
function urlBase64ToUint8Array(base64: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const normalized = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(normalized)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) {
    bytes[index] = raw.charCodeAt(index)
  }
  return bytes.buffer
}

/** Web Push enrolment (US-030). */
function PushEnrollment() {
  const [permission, setPermission] = useState<NotificationPermission>('default')
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const vapid = useQuery({ queryKey: ['push', 'vapid'], queryFn: pushApi.vapidKey })

  useEffect(() => {
    if ('Notification' in window) setPermission(Notification.permission)
  }, [])

  const enable = useMutation({
    mutationFn: async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        throw new Error('This browser does not support push notifications.')
      }
      const granted = await Notification.requestPermission()
      setPermission(granted)
      if (granted !== 'granted') throw new Error('Notification permission was not granted.')

      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.data!.public_key!),
      })

      const json = subscription.toJSON() as { keys?: { p256dh?: string; auth?: string } }
      return pushApi.subscribe({
        endpoint: subscription.endpoint,
        p256dh_key: json.keys?.p256dh ?? '',
        auth_key: json.keys?.auth ?? '',
        user_agent: navigator.userAgent,
      })
    },
    onSuccess: (result) => setNotice({ tone: 'success', text: result.message }),
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  // No VAPID keys configured server-side means push is simply unavailable here.
  if (!vapid.data?.configured) return null
  if (permission === 'granted' && !notice) return null

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {permission === 'denied' ? (
            <BellOff className="h-4 w-4 text-slate-400" />
          ) : (
            <BellRing className="h-4 w-4 text-brand-600" />
          )}
          Push notifications
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        {permission === 'denied' ? (
          <Alert tone="warn">
            Notifications are blocked for this site. Enable them in your browser settings to get
            instant alerts.
          </Alert>
        ) : (
          <p className="text-sm text-slate-600">
            Get instant alerts on this device for payments, maintenance and lease events — even when
            RentFlow is closed.
          </p>
        )}

        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

        {permission !== 'denied' && (
          <Button loading={enable.isPending} onClick={() => enable.mutate()}>
            Enable on this device
          </Button>
        )}
      </CardBody>
    </Card>
  )
}
