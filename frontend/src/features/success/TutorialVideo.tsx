import { PlayCircle } from 'lucide-react'

/**
 * A tutorial video (Module 24), shown above the text rather than instead of it.
 *
 * The player is chosen from the stored provider, never parsed out of the URL:
 * the src of an iframe is not something to derive from customer-supplied text,
 * and the backend already restricts the provider to a known list. Anything it
 * does not recognise degrades to a plain link, which still works and cannot
 * embed anything.
 *
 * Lives in its own module because two screens render it — the in-app HelpPanel
 * and the public help centre — and the embed rules are the last thing that
 * should exist in two copies.
 */
export function TutorialVideo({
  url,
  provider,
  seconds,
}: {
  url: string
  provider: string | null
  seconds: number | null
}) {
  const embed = toEmbedUrl(url, provider)

  if (!embed) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-brand-600 hover:underline"
      >
        <PlayCircle className="h-4 w-4" />
        Watch the video
        {seconds ? ` (${Math.round(seconds / 60)} min)` : ''}
      </a>
    )
  }

  return (
    <div className="mt-3 aspect-video overflow-hidden rounded-lg bg-slate-900">
      <iframe
        src={embed}
        title="Tutorial video"
        className="h-full w-full"
        allow="accelerometer; clipboard-write; encrypted-media; picture-in-picture"
        allowFullScreen
      />
    </div>
  )
}

function toEmbedUrl(url: string, provider: string | null): string | null {
  if (!url.startsWith('https://')) return null
  try {
    const parsed = new URL(url)
    if (provider === 'youtube') {
      const id = parsed.searchParams.get('v') ?? parsed.pathname.split('/').pop()
      return id ? `https://www.youtube-nocookie.com/embed/${id}` : null
    }
    if (provider === 'vimeo') {
      const id = parsed.pathname.split('/').filter(Boolean).pop()
      return id ? `https://player.vimeo.com/video/${id}` : null
    }
  } catch {
    return null
  }
  return null
}
