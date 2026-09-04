import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, FilePlus2, FileText, Plus, Save, Star } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { leaseTemplatesApi } from '@/api'
import type { LeaseTemplate } from '@/api/types'
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
  Field,
  Input,
  PageLoader,
  Tab,
  Tabs,
  Textarea,
} from '@/components/ui'
import { RichTextEditor } from '@/features/lease-templates/RichTextEditor'
import { errorMessage, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const BLANK = {
  id: '',
  name: '',
  body_html: '',
  letterhead_text: '',
  is_default: false,
  version: 0,
}

type Draft = typeof BLANK

function toDraft(template: LeaseTemplate): Draft {
  return {
    id: template.id,
    name: template.name,
    body_html: template.body_html,
    letterhead_text: template.letterhead_text ?? '',
    is_default: template.is_default,
    version: template.version,
  }
}

/**
 * Lease template editor (US-047).
 *
 * A template is a lease body with `{{placeholders}}` that get filled per tenancy.
 * The preview renders the body server-side with sample data through exactly the
 * same pipeline a real lease uses, so what the editor shows is what a tenant
 * will sign.
 */
export function LeaseTemplatesPage() {
  const queryClient = useQueryClient()

  const [draft, setDraft] = useState<Draft | null>(null)
  const [mode, setMode] = useState<'rich' | 'html'>('rich')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  // Set by the editor so the variable palette can splice at the caret.
  const insertRef = useRef<((text: string) => void) | null>(null)
  const registerInsert = useCallback((insert: (text: string) => void) => {
    insertRef.current = insert
  }, [])

  const templates = useQuery({
    queryKey: queryKeys.leaseTemplates,
    queryFn: leaseTemplatesApi.list,
  })
  const starter = useQuery({
    queryKey: ['lease-templates', 'starter'],
    queryFn: leaseTemplatesApi.starter,
  })

  // A blob URL is a live handle on memory; drop the old one whenever it changes.
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const save = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error('Nothing to save.')
      const body = {
        name: draft.name.trim(),
        body_html: draft.body_html,
        letterhead_text: draft.letterhead_text || null,
        is_default: draft.is_default,
      }
      return draft.id
        ? leaseTemplatesApi.update(draft.id, body)
        : leaseTemplatesApi.create(body)
    },
    onSuccess: async (template) => {
      setError(null)
      setNotice(`Saved "${template.name}" as version ${template.version}.`)
      setDraft(toDraft(template))
      await queryClient.invalidateQueries({ queryKey: queryKeys.leaseTemplates })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const preview = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('Nothing to preview.')
      const blob = await leaseTemplatesApi.preview({
        body_html: draft.body_html,
        letterhead_text: draft.letterhead_text || null,
      })
      return URL.createObjectURL(blob)
    },
    onSuccess: (url) => {
      setError(null)
      setPreviewUrl(url)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (templates.isPending || starter.isPending) return <PageLoader />

  const rows = templates.data ?? []
  const variables = starter.data?.variables ?? []

  const startNew = () => {
    setError(null)
    setNotice(null)
    setDraft({ ...BLANK, name: 'New lease template', body_html: starter.data?.body_html ?? '' })
  }

  return (
    <div>
      <PageHeader
        title="Lease templates"
        description="Write the lease once; every tenancy fills in its own names, dates and amounts."
        actions={
          <Button icon={<Plus className="h-4 w-4" />} onClick={startNew}>
            New template
          </Button>
        }
      />

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}
      {notice && (
        <Alert tone="success" className="mb-4">
          {notice}
        </Alert>
      )}

      <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
        <Card className="self-start">
          <CardHeader>
            <CardTitle className="text-base">Your templates</CardTitle>
          </CardHeader>
          <CardBody>
            {rows.length === 0 ? (
              <EmptyState
                icon={<FileText className="h-6 w-6" />}
                title="No templates yet"
                description="Start from the built-in Kenyan lease and edit it to your house style."
                action={
                  <Button
                    variant="secondary"
                    icon={<FilePlus2 className="h-4 w-4" />}
                    onClick={startNew}
                  >
                    Start from the standard lease
                  </Button>
                }
              />
            ) : (
              <ul className="space-y-1">
                {rows.map((template) => (
                  <li key={template.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setError(null)
                        setNotice(null)
                        setDraft(toDraft(template))
                      }}
                      className={
                        draft?.id === template.id
                          ? 'w-full rounded-md bg-brand-50 px-3 py-2 text-left text-sm text-brand-800'
                          : 'w-full rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50'
                      }
                    >
                      <span className="font-medium">{template.name}</span>
                      {template.is_default && (
                        <Badge tone="brand" className="ml-2">
                          <Star className="mr-1 inline h-3 w-3" />
                          Default
                        </Badge>
                      )}
                      <span className="mt-0.5 block text-xs text-slate-400">
                        v{template.version} · {shortDate(template.created_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        {draft === null ? (
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="Pick a template to edit"
            description="Or start a new one from the standard Kenyan lease."
          />
        ) : (
          <div className="space-y-4">
            <Card>
              <CardBody className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Template name" required>
                    <Input
                      value={draft.name}
                      onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                    />
                  </Field>
                  <Field
                    label="Letterhead note"
                    hint="Printed above the body — a licence number, say."
                  >
                    <Input
                      value={draft.letterhead_text}
                      onChange={(event) =>
                        setDraft({ ...draft, letterhead_text: event.target.value })
                      }
                    />
                  </Field>
                </div>

                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={draft.is_default}
                    onChange={(event) => setDraft({ ...draft, is_default: event.target.checked })}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                  Use this template for new tenancies
                </label>

                <div>
                  <Tabs
                    value={mode}
                    onChange={(value) => setMode(value as 'rich' | 'html')}
                    className="mb-3"
                  >
                    <Tab value="rich">Editor</Tab>
                    <Tab value="html">HTML</Tab>
                  </Tabs>

                  {mode === 'rich' ? (
                    <RichTextEditor
                      value={draft.body_html}
                      onChange={(html) => setDraft({ ...draft, body_html: html })}
                      onInsertPoint={registerInsert}
                    />
                  ) : (
                    <Textarea
                      rows={20}
                      spellCheck={false}
                      value={draft.body_html}
                      onChange={(event) => setDraft({ ...draft, body_html: event.target.value })}
                      className="font-mono text-xs"
                    />
                  )}
                </div>

                <div>
                  <p className="mb-1.5 text-sm font-medium text-slate-700">Placeholders</p>
                  <p className="mb-2 text-xs text-slate-500">
                    Click one to drop it in. Each is replaced with the real value when a lease is
                    generated, and the value is escaped — a tenant's own name can never inject
                    markup into their lease.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {variables.map((name) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => {
                          const token = `{{${name}}}`
                          if (mode === 'rich' && insertRef.current) insertRef.current(token)
                          else setDraft({ ...draft, body_html: draft.body_html + token })
                        }}
                        className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600 hover:border-brand-300 hover:text-brand-700"
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    loading={save.isPending}
                    disabled={draft.name.trim().length < 2 || draft.body_html.length < 10}
                    icon={<Save className="h-4 w-4" />}
                    onClick={() => save.mutate()}
                  >
                    {draft.id ? 'Save changes' : 'Create template'}
                  </Button>
                  <Button
                    variant="secondary"
                    loading={preview.isPending}
                    disabled={draft.body_html.length < 10}
                    icon={<Eye className="h-4 w-4" />}
                    onClick={() => preview.mutate()}
                  >
                    Preview with sample data
                  </Button>
                  {draft.id !== '' && (
                    <span className="text-xs text-slate-500">
                      Saving a body change makes this version {draft.version + 1}. Leases already
                      generated keep the wording they were made with.
                    </span>
                  )}
                </div>
              </CardBody>
            </Card>

            {previewUrl && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Preview</CardTitle>
                  <p className="text-sm text-slate-500">
                    Rendered by the same engine that produces real leases, filled with sample data.
                  </p>
                </CardHeader>
                <CardBody>
                  <iframe
                    title="Lease template preview"
                    src={previewUrl}
                    className="h-[36rem] w-full rounded-card border border-slate-200"
                  />
                </CardBody>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
