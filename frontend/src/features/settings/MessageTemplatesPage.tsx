import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, RotateCcw, Save } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { messageTemplatesApi } from '@/api'
import type { MessageTemplate, MessageTemplateType, TemplateChannel } from '@/api/types'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Field,
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { errorMessage, relative } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/**
 * Rewriting the messages RentFlow sends on a landlord's behalf (Module 21).
 *
 * The message copy was hardcoded in whichever service raised it, which is fine
 * for most landlords and wrong for some — an upmarket Westlands agency and a
 * caretaker-run block in Kayole do not address their tenants the same way.
 *
 * The editor deliberately shows the preview and the SMS segment count next to
 * the box. A four-part SMS costs four times as much to send, and that should be
 * a decision made while typing rather than a surprise on next month's bill.
 */

const CHANNELS: { value: TemplateChannel; label: string; hint: string }[] = [
  { value: 'any', label: 'Every channel', hint: 'One wording, used wherever this message goes' },
  { value: 'whatsapp', label: 'WhatsApp only', hint: 'Overrides the every-channel wording' },
  { value: 'sms', label: 'SMS only', hint: 'Keep it short — SMS is billed per 160 characters' },
  { value: 'email', label: 'Email only', hint: 'Room for a fuller message' },
  { value: 'in_app', label: 'In-app only', hint: 'Shown in the notification bell' },
  { value: 'push', label: 'Push only', hint: 'Shown on the lock screen' },
]

function templateKey(type: string, channel: string): string {
  return `${type}::${channel}`
}

export function MessageTemplatesPage() {
  const queryClient = useQueryClient()
  const [notificationType, setNotificationType] = useState('')
  const [channel, setChannel] = useState<TemplateChannel>('any')
  const [body, setBody] = useState('')
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const types = useQuery({
    queryKey: queryKeys.messageTemplateTypes,
    queryFn: messageTemplatesApi.types,
    staleTime: 60 * 60_000,
  })
  const templates = useQuery({
    queryKey: queryKeys.messageTemplates,
    queryFn: messageTemplatesApi.list,
  })

  const typeList: MessageTemplateType[] = useMemo(() => types.data ?? [], [types.data])

  useEffect(() => {
    if (!notificationType && typeList.length > 0) {
      setNotificationType(typeList[0].notification_type)
    }
  }, [notificationType, typeList])

  const existing: MessageTemplate | undefined = useMemo(
    () =>
      (templates.data ?? []).find(
        (row) => templateKey(row.notification_type, row.channel) === templateKey(notificationType, channel),
      ),
    [templates.data, notificationType, channel],
  )

  // Load whatever is already saved for this type and channel, so switching the
  // selectors shows the current wording rather than a blank box.
  useEffect(() => {
    setBody(existing?.body ?? '')
    setNotice(null)
  }, [existing])

  const selectedType = typeList.find((row) => row.notification_type === notificationType)

  const preview = useQuery({
    queryKey: [...queryKeys.messageTemplates, 'preview', notificationType, body],
    queryFn: () => messageTemplatesApi.preview({ notification_type: notificationType, body }),
    // Only once there is something to preview, and only for a chosen type.
    enabled: Boolean(notificationType && body.trim()),
  })

  const save = useMutation({
    mutationFn: () =>
      messageTemplatesApi.save({ notification_type: notificationType, channel, body }),
    onSuccess: () => {
      setNotice({ tone: 'success', text: 'Saved. New messages of this type use your wording.' })
      void queryClient.invalidateQueries({ queryKey: queryKeys.messageTemplates })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  const revert = useMutation({
    mutationFn: (id: string) => messageTemplatesApi.remove(id),
    onSuccess: () => {
      setNotice({ tone: 'success', text: 'Reverted to the built-in wording.' })
      setBody('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.messageTemplates })
    },
    onError: (error) => setNotice({ tone: 'danger', text: errorMessage(error) }),
  })

  if (types.isPending || templates.isPending) return <PageLoader />

  const variables = selectedType?.available_variables ?? []
  const segments = preview.data?.sms_segments ?? 0

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Message wording</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-sm text-slate-600">
            RentFlow has default wording for every message it sends your tenants. Rewrite any of
            them here — the default is used until you do, and deleting yours puts it back.
          </p>

          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Message" required>
              <Select
                value={notificationType}
                onChange={(event) => setNotificationType(event.target.value)}
              >
                {typeList.map((row) => (
                  <option key={row.notification_type} value={row.notification_type}>
                    {row.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Channel"
              hint={CHANNELS.find((option) => option.value === channel)?.hint}
            >
              <Select
                value={channel}
                onChange={(event) => setChannel(event.target.value as TemplateChannel)}
              >
                {CHANNELS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field
            label="Your wording"
            required
            hint="Use the placeholders below. A placeholder RentFlow does not recognise is refused rather than sent as-is."
          >
            <Textarea
              rows={5}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Dear {{tenant_name}}, your rent of KES {{amount}} is due on {{due_date}}."
            />
          </Field>

          <div>
            <p className="mb-1.5 text-xs font-medium text-slate-500">
              Available placeholders — click to insert
            </p>
            <div className="flex flex-wrap gap-1.5">
              {variables.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setBody((current) => `${current}{{${name}}}`)}
                  className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-700 hover:border-brand-300 hover:bg-brand-50"
                >
                  {`{{${name}}}`}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              icon={<Save className="h-4 w-4" />}
              onClick={() => save.mutate()}
              loading={save.isPending}
              disabled={!body.trim()}
            >
              Save wording
            </Button>
            {existing && (
              <Button
                variant="ghost"
                icon={<RotateCcw className="h-4 w-4" />}
                onClick={() => revert.mutate(existing.id)}
                loading={revert.isPending}
              >
                Use the built-in wording
              </Button>
            )}
          </div>
        </CardBody>
      </Card>

      {preview.data?.body && (
        <Card>
          <CardHeader>
            <CardTitle>Preview</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800">
              {preview.data.body}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <Badge tone={segments > 1 ? 'warn' : 'neutral'}>
                {preview.data.character_count} characters
              </Badge>
              <Badge tone={segments > 1 ? 'warn' : 'neutral'}>
                {segments} SMS {segments === 1 ? 'message' : 'messages'}
              </Badge>
              {segments > 1 && (
                <span>An SMS over 160 characters is billed as more than one message.</span>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      {(templates.data ?? []).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Your custom wording</CardTitle>
          </CardHeader>
          <CardBody className="space-y-2">
            {(templates.data ?? []).map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => {
                  setNotificationType(row.notification_type)
                  setChannel(row.channel)
                }}
                className="flex w-full items-start gap-3 rounded-lg border border-slate-200 p-3 text-left hover:border-brand-300 hover:bg-brand-50"
              >
                <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">
                    {typeList.find((type) => type.notification_type === row.notification_type)
                      ?.label ?? row.notification_type}
                    <span className="ml-2 font-normal text-slate-500">
                      {CHANNELS.find((option) => option.value === row.channel)?.label}
                    </span>
                  </p>
                  <p className="truncate text-xs text-slate-500">{row.body}</p>
                  {row.last_used_at && (
                    <p className="mt-0.5 text-xs text-slate-400">
                      Last sent {relative(row.last_used_at)}
                    </p>
                  )}
                </div>
              </button>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  )
}
