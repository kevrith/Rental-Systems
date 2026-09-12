import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { internalApi } from '@/api'
import type { ChangelogEntry, HelpArticle } from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  Dialog,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Tab,
  Tabs,
  Td,
  Textarea,
  Th,
} from '@/components/ui'
import { errorMessage, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** RentFlow staff's editor for the shared knowledge base and changelog
 * (US-090, US-092) — the internal counterpart to the read-only
 * `HelpPanel`/`ChangelogWidget` every organization sees. */
export function InternalContentPage() {
  const [tab, setTab] = useState<'help' | 'changelog'>('help')

  return (
    <div>
      <PageHeader title="Content" description="The knowledge base and changelog every customer sees." />
      <Tabs value={tab} onChange={(value) => setTab(value as 'help' | 'changelog')}>
        <Tab value="help">Help articles</Tab>
        <Tab value="changelog">Changelog</Tab>
      </Tabs>
      <div className="mt-4">{tab === 'help' ? <HelpArticlesTab /> : <ChangelogTab />}</div>
    </div>
  )
}

function HelpArticlesTab() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<HelpArticle | 'new' | null>(null)
  const articles = useQuery({
    queryKey: queryKeys.internalHelpArticles,
    queryFn: internalApi.helpArticles,
  })

  const deleteArticle = useMutation({
    mutationFn: (id: string) => internalApi.deleteHelpArticle(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.internalHelpArticles }),
  })

  if (articles.isPending) return <PageLoader />

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setEditing('new')}>
          <Plus className="h-4 w-4" />
          New article
        </Button>
      </div>
      {!articles.data?.length ? (
        <EmptyState title="No help articles yet" description="Create the first one for the help panel." />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  <Th className="w-16">Order</Th>
                  <Th>Title</Th>
                  <Th>Category</Th>
                  <Th>Status</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {articles.data.map((article) => (
                  <tr key={article.id}>
                    <Td className="tabular-nums text-slate-400">{article.sort_order}</Td>
                    <Td className="font-medium text-slate-900">{article.title}</Td>
                    <Td>{article.category}</Td>
                    <Td>
                      <Badge tone={article.is_published ? 'success' : 'neutral'}>
                        {article.is_published ? 'Published' : 'Draft'}
                      </Badge>
                    </Td>
                    <Td>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setEditing(article)}
                          className="text-slate-400 hover:text-slate-700"
                          aria-label="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm('Delete this article? This cannot be undone.')) {
                              deleteArticle.mutate(article.id)
                            }
                          }}
                          className="text-slate-400 hover:text-danger-600"
                          aria-label="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      {editing && <HelpArticleDialog article={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function HelpArticleDialog({ article, onClose }: { article: HelpArticle | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [slug, setSlug] = useState(article?.slug ?? '')
  const [title, setTitle] = useState(article?.title ?? '')
  const [category, setCategory] = useState(article?.category ?? '')
  const [body, setBody] = useState(article?.body ?? '')
  const [isPublished, setIsPublished] = useState(article?.is_published ?? true)
  // Blank means "leave it to the server": appended to the end on create, kept
  // as-is on edit. Sending 0 instead would move an edited article to the top.
  const [sortOrder, setSortOrder] = useState(article ? String(article.sort_order) : '')
  const [videoUrl, setVideoUrl] = useState(article?.video_url ?? '')
  const [videoProvider, setVideoProvider] = useState(article?.video_provider ?? 'youtube')
  const [videoSeconds, setVideoSeconds] = useState(
    article?.video_duration_seconds ? String(article.video_duration_seconds) : '',
  )

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        slug,
        title,
        category,
        body,
        is_published: isPublished,
        sort_order: sortOrder.trim() === '' ? null : Number(sortOrder),
        // An empty URL clears the video rather than saving an empty string.
        video_url: videoUrl.trim() || null,
        video_provider: videoUrl.trim() ? videoProvider : null,
        video_duration_seconds: videoUrl.trim() && videoSeconds ? Number(videoSeconds) : null,
      }
      return article ? internalApi.updateHelpArticle(article.id, payload) : internalApi.createHelpArticle(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalHelpArticles })
      onClose()
    },
  })

  return (
    <Dialog open onClose={onClose} title={article ? 'Edit article' : 'New article'} size="lg">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Title">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={255} />
          </Field>
          <Field label="Slug" hint="Used in the article's URL — letters, numbers and dashes.">
            <Input
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              required
              maxLength={120}
              pattern="[a-z0-9\-]+"
            />
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Category">
            <Input value={category} onChange={(event) => setCategory(event.target.value)} required maxLength={100} />
          </Field>
          <Field
            label="Reading order"
            hint="Position in the help centre, low to high. Categories are grouped by where their first article sits, so keep a category's articles together. Leave blank to append."
          >
            <Input
              type="number"
              min={0}
              step={10}
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
            />
          </Field>
        </div>
        <Field label="Body" hint="Required even for a video article — this is what search finds.">
          <Textarea value={body} onChange={(event) => setBody(event.target.value)} required rows={8} />
        </Field>
        <Field
          label="Tutorial video"
          hint="Optional. Must be https, and from a provider the app has a player for."
        >
          <Input
            type="url"
            value={videoUrl}
            onChange={(event) => setVideoUrl(event.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            maxLength={1024}
          />
        </Field>
        {videoUrl.trim() && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Provider">
              <Select
                value={videoProvider}
                onChange={(event) => setVideoProvider(event.target.value)}
              >
                <option value="youtube">YouTube</option>
                <option value="vimeo">Vimeo</option>
              </Select>
            </Field>
            <Field label="Length (seconds)">
              <Input
                type="number"
                min="1"
                value={videoSeconds}
                onChange={(event) => setVideoSeconds(event.target.value)}
                placeholder="95"
              />
            </Field>
          </div>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={isPublished}
            onChange={(event) => setIsPublished(event.target.checked)}
          />
          Published
        </label>
        {save.isError && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
        <Button type="submit" className="w-full" loading={save.isPending}>
          Save
        </Button>
      </form>
    </Dialog>
  )
}

function ChangelogTab() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<ChangelogEntry | 'new' | null>(null)
  const entries = useQuery({
    queryKey: queryKeys.internalChangelogEntries,
    queryFn: internalApi.changelogEntries,
  })

  const deleteEntry = useMutation({
    mutationFn: (id: string) => internalApi.deleteChangelogEntry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalChangelogEntries })
      queryClient.invalidateQueries({ queryKey: queryKeys.changelog })
    },
  })

  if (entries.isPending) return <PageLoader />

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setEditing('new')}>
          <Plus className="h-4 w-4" />
          New entry
        </Button>
      </div>
      {!entries.data?.length ? (
        <EmptyState title="No changelog entries yet" description="Announce your first update." />
      ) : (
        <div className="space-y-3">
          {entries.data.map((entry) => (
            <Card key={entry.id}>
              <CardBody className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{entry.title}</p>
                  <p className="text-xs text-slate-400">{shortDate(entry.published_at)}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{entry.body}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setEditing(entry)}
                    className="text-slate-400 hover:text-slate-700"
                    aria-label="Edit"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm('Delete this entry? This cannot be undone.')) {
                        deleteEntry.mutate(entry.id)
                      }
                    }}
                    className="text-slate-400 hover:text-danger-600"
                    aria-label="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <ChangelogDialog entry={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}

function ChangelogDialog({ entry, onClose }: { entry: ChangelogEntry | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(entry?.title ?? '')
  const [body, setBody] = useState(entry?.body ?? '')
  const [isPublished, setIsPublished] = useState(true)

  const save = useMutation({
    mutationFn: () => {
      const payload = { title, body, is_published: isPublished }
      return entry ? internalApi.updateChangelogEntry(entry.id, payload) : internalApi.createChangelogEntry(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.internalChangelogEntries })
      queryClient.invalidateQueries({ queryKey: queryKeys.changelog })
      onClose()
    },
  })

  return (
    <Dialog open onClose={onClose} title={entry ? 'Edit entry' : 'New changelog entry'} size="md">
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <Field label="Title">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={200} />
        </Field>
        <Field label="Body">
          <Textarea value={body} onChange={(event) => setBody(event.target.value)} required rows={5} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={isPublished}
            onChange={(event) => setIsPublished(event.target.checked)}
          />
          Published
        </label>
        {save.isError && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
        <Button type="submit" className="w-full" loading={save.isPending}>
          Save
        </Button>
      </form>
    </Dialog>
  )
}
