import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronLeft, LifeBuoy, PlayCircle, Search, Send } from 'lucide-react'
import { useEffect, useState } from 'react'

import { customerSuccessApi } from '@/api'
import { Alert, Button, Dialog, EmptyState, Field, Input, Spinner, Textarea } from '@/components/ui'
import { errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

import { TutorialVideo } from './TutorialVideo'

/** Contextual help side panel (US-090). Built on the existing `Dialog` rather
 * than a new slide-in primitive — one fewer component to introduce for a
 * panel that only needs to show search results and article text. */
export function HelpPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [contactOpen, setContactOpen] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 250)
    return () => clearTimeout(timer)
  }, [query])

  const results = useQuery({
    queryKey: queryKeys.helpSearch(debouncedQuery),
    queryFn: () => customerSuccessApi.searchHelp(debouncedQuery || undefined),
    enabled: open && !selectedSlug,
  })

  const article = useQuery({
    queryKey: queryKeys.helpArticle(selectedSlug ?? ''),
    queryFn: () => customerSuccessApi.helpArticle(selectedSlug as string),
    enabled: open && Boolean(selectedSlug),
  })

  return (
    <Dialog
      open={open}
      onClose={() => {
        setSelectedSlug(null)
        setContactOpen(false)
        onClose()
      }}
      title="Help"
      size="md"
    >
      {contactOpen ? (
        <ContactSupportForm onDone={() => setContactOpen(false)} />
      ) : selectedSlug ? (
        <div>
          <button
            type="button"
            onClick={() => setSelectedSlug(null)}
            className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
          >
            <ChevronLeft className="h-4 w-4" />
            Back to search
          </button>
          {article.isPending ? (
            <Spinner />
          ) : article.data ? (
            <div>
              <h3 className="text-base font-semibold text-slate-900">{article.data.title}</h3>
              {article.data.video_url && (
                <TutorialVideo
                  url={article.data.video_url}
                  provider={article.data.video_provider}
                  seconds={article.data.video_duration_seconds}
                />
              )}
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{article.data.body}</p>
            </div>
          ) : (
            <Alert tone="danger">Could not load this article.</Alert>
          )}
        </div>
      ) : (
        <div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search help articles"
              className="pl-9"
            />
          </div>

          <div className="mt-3 max-h-80 space-y-1 overflow-y-auto">
            {results.isPending ? (
              <Spinner />
            ) : results.data && results.data.length > 0 ? (
              results.data.map((article) => (
                <button
                  key={article.id}
                  type="button"
                  onClick={() => setSelectedSlug(article.slug)}
                  className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <p className="flex items-center gap-1.5 font-medium text-slate-900">
                    {article.has_video && (
                      <PlayCircle className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
                    )}
                    {article.title}
                  </p>
                  <p className="text-xs text-slate-400">
                    {article.category}
                    {article.video_duration_seconds
                      ? ` · ${Math.round(article.video_duration_seconds / 60)} min video`
                      : ''}
                  </p>
                </button>
              ))
            ) : (
              <EmptyState
                icon={<LifeBuoy className="h-8 w-8" />}
                title="No articles found"
                description="Try a different search term, or contact support directly."
              />
            )}
          </div>

          <div className="mt-4 border-t border-slate-100 pt-3">
            <Button variant="secondary" size="sm" onClick={() => setContactOpen(true)}>
              Contact support
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}

function ContactSupportForm({ onDone }: { onDone: () => void }) {
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [sent, setSent] = useState(false)

  const submit = useMutation({
    mutationFn: () => customerSuccessApi.createSupportRequest({ subject, message }),
    onSuccess: () => setSent(true),
  })

  if (sent) {
    return (
      <div>
        <Alert tone="success">Thanks — we've received your message and will reply soon.</Alert>
        <Button className="mt-3" size="sm" onClick={onDone}>
          Back to help
        </Button>
      </div>
    )
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        submit.mutate()
      }}
    >
      <Field label="Subject">
        <Input
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
          required
          maxLength={255}
        />
      </Field>
      <Field label="Message">
        <Textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          required
          rows={5}
        />
      </Field>
      {submit.isError && <Alert tone="danger">{errorMessage(submit.error)}</Alert>}
      <div className="flex items-center justify-between">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Back
        </Button>
        <Button type="submit" size="sm" loading={submit.isPending}>
          <Send className="h-4 w-4" />
          Send
        </Button>
      </div>
    </form>
  )
}
