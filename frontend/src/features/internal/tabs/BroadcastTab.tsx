import { useMutation } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import {
  Alert,
  Button,
  Card,
  CardBody,
  Field,
  Input,
  Select,
  Textarea,
} from '@/components/ui'
import { errorMessage } from '@/lib/format'

const PLAN_OPTIONS = ['', 'trial', 'free', 'starter', 'professional', 'business']
const CHANNEL_OPTIONS = ['email', 'sms', 'in_app']

export function BroadcastTab() {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [channels, setChannels] = useState<string[]>(['email'])
  const [planFilter, setPlanFilter] = useState('')
  const [sent, setSent] = useState<number | null>(null)

  const broadcast = useMutation({
    mutationFn: () =>
      internalApi.broadcast({
        title,
        body,
        channels,
        plan_filter: planFilter || null,
      }),
    onSuccess: (data) => {
      setSent(data.sent)
      setTitle('')
      setBody('')
      setChannels(['email'])
      setPlanFilter('')
    },
  })

  function toggleChannel(ch: string) {
    setChannels((prev) =>
      prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch],
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Sends to all active organization owners and agency admins. Every message is
            logged in the audit trail.
          </p>

          {sent !== null && (
            <Alert tone="success">
              Sent to {sent} recipient{sent !== 1 ? 's' : ''}.
            </Alert>
          )}

          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              setSent(null)
              broadcast.mutate()
            }}
          >
            <Field label="Subject / title">
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                minLength={3}
                maxLength={200}
                placeholder="Scheduled maintenance — Sunday 02:00–04:00 EAT"
              />
            </Field>

            <Field label="Message body">
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                required
                minLength={10}
                maxLength={2000}
                rows={6}
                placeholder="We will be performing scheduled maintenance…"
              />
            </Field>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Channels">
                <div className="flex flex-wrap gap-3 pt-1">
                  {CHANNEL_OPTIONS.map((ch) => (
                    <label key={ch} className="flex items-center gap-1.5 text-sm text-slate-700 dark:text-slate-300">
                      <input
                        type="checkbox"
                        checked={channels.includes(ch)}
                        onChange={() => toggleChannel(ch)}
                      />
                      {ch.replace('_', ' ')}
                    </label>
                  ))}
                </div>
              </Field>

              <Field label="Limit to plan" hint="Leave blank to send to all plans.">
                <Select value={planFilter} onChange={(e) => setPlanFilter(e.target.value)}>
                  {PLAN_OPTIONS.map((p) => (
                    <option key={p} value={p}>
                      {p === '' ? 'All plans' : p.charAt(0).toUpperCase() + p.slice(1)}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            {broadcast.isError && (
              <Alert tone="danger">{errorMessage(broadcast.error)}</Alert>
            )}

            <Button
              type="submit"
              icon={<Send className="h-4 w-4" />}
              loading={broadcast.isPending}
              disabled={channels.length === 0}
            >
              Send broadcast
            </Button>
          </form>
        </CardBody>
      </Card>
    </div>
  )
}
