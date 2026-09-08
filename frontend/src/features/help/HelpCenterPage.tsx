import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Building2,
  ChevronRight,
  PlayCircle,
  Rocket,
  Search,
  ShieldCheck,
  Users,
  Wallet,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { publicHelpApi } from '@/api'
import type { HelpArticle } from '@/api/types'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Alert, Input, PageLoader, linkButtonClass } from '@/components/ui'
import { TutorialVideo } from '@/features/success/TutorialVideo'
import { Logo, MarketingFooter } from '@/features/marketing/MarketingChrome'
import { cn } from '@/lib/cn'
import { queryKeys } from '@/lib/query-client'

/**
 * The public help centre.
 *
 * Same knowledge base the in-app HelpPanel reads, without the login in front of
 * it. Two readers need it and neither has a session: someone deciding whether
 * to buy, and a caretaker or tenant who cannot get past the sign-in screen.
 *
 * The whole published set is fetched once and filtered in the browser rather
 * than round-tripping every keystroke. At the size a property-management
 * knowledge base actually reaches — tens of articles, not thousands — one
 * request buys instant search, ranking that puts title matches above passing
 * mentions in a body, and a page that keeps working when the connection drops
 * halfway through reading. If it ever outgrows that, `/help/articles` takes a
 * `q` and does the search server-side.
 */

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  'Getting started': Rocket,
  'Rent and payments': Wallet,
  'Arrears and reminders': BookOpen,
  'Field operations': Wrench,
  'Tenants and leases': Users,
  'Agency and owners': Building2,
  'Your account and data': ShieldCheck,
}

/** Declared at module scope rather than resolved into a local `Icon` binding
 *  inside each screen: a capitalized local assigned during render reads as a
 *  component being created per render, which is exactly what the React lint
 *  rule is there to catch even when the lookup is from a constant map. */
function CategoryIcon({ category, className }: { category: string; className?: string }) {
  const Icon: LucideIcon = CATEGORY_ICONS[category] ?? BookOpen
  return <Icon className={className} aria-hidden />
}

// ------------------------------------------------------------------- chrome

function HelpNav() {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <Link to="/" aria-label="RentFlow Kenya home">
          <Logo compact />
        </Link>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {/* Hidden by the wrapper, not by a `hidden` on the link itself:
              `linkButtonClass` sets `inline-flex`, and Tailwind orders that
              after `hidden`, so the utility would lose on the element. */}
          <div className="hidden sm:block">
            <Link to="/login" className={linkButtonClass('ghost', 'sm')}>
              Sign in
            </Link>
          </div>
          <Link to="/register" className={cn(linkButtonClass('primary', 'sm'), 'whitespace-nowrap')}>
            Start free trial
          </Link>
        </div>
      </div>
    </header>
  )
}

function HelpLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <HelpNav />
      <main className="mx-auto max-w-5xl px-4 py-10 sm:py-14">{children}</main>
      <MarketingFooter />
    </div>
  )
}

/** Every screen here can fail the same two ways, so they answer the same way. */
function HelpError({ children }: { children: React.ReactNode }) {
  return (
    <Alert tone="warn" title="We could not load this just now">
      {children}{' '}
      <Link to="/help" className="font-medium underline">
        Back to the help centre
      </Link>
      .
    </Alert>
  )
}

// -------------------------------------------------------------------- index

/**
 * Fold out the punctuation that splits a word people type as one — the hyphen
 * in "M-Pesa", the dot in "e.g.". The same rule `help_service` applies in
 * Postgres, kept in step here because this page filters in the browser and
 * would otherwise miss what the API would have found.
 *
 * Spaces survive. Collapsing those too would fold "rent day" into "rentday",
 * a substring of "diffe(rent day)".
 */
function fold(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9 ]/g, '')
}

/** Title matches rank above body matches: someone typing "arrears" wants the
 *  article about arrears, not the six that mention the word in passing. */
function rank(articles: HelpArticle[], query: string): HelpArticle[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return articles

  const folded = fold(needle)
  // A query of pure punctuation folds to nothing, and every string contains
  // the empty string — fall back to the raw needle alone rather than matching
  // the whole knowledge base.
  const matches = (value: string) =>
    value.toLowerCase().includes(needle) || (folded !== '' && fold(value).includes(folded))

  const scored = articles
    .map((article) => {
      if (matches(article.title)) {
        // Guarded on `folded` for the same reason `matches` is: every string
        // starts with the empty one, which would score every hit as exact.
        const startsWith =
          article.title.toLowerCase().startsWith(needle) ||
          (folded !== '' && fold(article.title).startsWith(folded))
        return { article, score: startsWith ? 0 : 1 }
      }
      if (matches(article.category)) return { article, score: 2 }
      if (matches(article.body)) return { article, score: 3 }
      return null
    })
    .filter((hit): hit is { article: HelpArticle; score: number } => hit !== null)

  return scored.sort((a, b) => a.score - b.score).map((hit) => hit.article)
}

function ArticleRow({ article, showCategory = false }: { article: HelpArticle; showCategory?: boolean }) {
  return (
    <li>
      <Link
        to={`/help/${article.slug}`}
        className="group flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-slate-100 dark:hover:bg-slate-800"
      >
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm font-medium text-slate-900 dark:text-white">
            {article.has_video && (
              <PlayCircle className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
            )}
            {article.title}
          </span>
          {showCategory && (
            <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
              {article.category}
            </span>
          )}
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-slate-300 group-hover:text-slate-500 dark:text-slate-600" />
      </Link>
    </li>
  )
}

export function HelpCenterPage() {
  const [query, setQuery] = useState('')

  const articles = useQuery({
    queryKey: queryKeys.publicHelpSearch(),
    queryFn: () => publicHelpApi.search(),
    staleTime: 5 * 60_000,
  })

  const grouped = useMemo(() => {
    const rows = articles.data ?? []
    const byCategory = new Map<string, HelpArticle[]>()
    for (const article of rows) {
      const bucket = byCategory.get(article.category)
      if (bucket) bucket.push(article)
      else byCategory.set(article.category, [article])
    }
    // Insertion order, which is the server's `sort_order`: a category first
    // appears where its earliest article does, and its articles keep the order
    // they arrived in. Nothing about reading order is decided here.
    return [...byCategory.entries()]
  }, [articles.data])

  const results = useMemo(() => rank(articles.data ?? [], query), [articles.data, query])

  return (
    <HelpLayout>
      <div className="mx-auto max-w-2xl text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand-600 dark:text-brand-400">
          Help centre
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl dark:text-white">
          How RentFlow works
        </h1>
        <p className="mt-4 text-base leading-relaxed text-slate-600 dark:text-slate-300">
          Setting up a portfolio, collecting rent through M-Pesa, working arrears, and everything
          your caretaker does from a phone. No account needed to read any of it.
        </p>

        <div className="relative mt-8">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search the help centre"
            aria-label="Search the help centre"
            className="pl-9"
          />
        </div>
      </div>

      <div className="mt-12">
        {articles.isPending ? (
          <PageLoader />
        ) : articles.isError ? (
          <HelpError>Try again in a moment.</HelpError>
        ) : query.trim() ? (
          <SearchResults query={query} results={results} />
        ) : (
          <CategoryGrid grouped={grouped} />
        )}
      </div>

      <SupportPrompt />
    </HelpLayout>
  )
}

function SearchResults({ query, results }: { query: string; results: HelpArticle[] }) {
  if (results.length === 0) {
    return (
      <div className="rounded-card border border-slate-200 bg-white px-6 py-10 text-center dark:border-slate-800 dark:bg-slate-900">
        <BookOpen className="mx-auto h-8 w-8 text-slate-300 dark:text-slate-600" aria-hidden />
        <p className="mt-3 text-sm font-medium text-slate-900 dark:text-white">
          Nothing matches "{query}"
        </p>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Try a broader word, or browse the categories by clearing the search.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-card border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <p className="px-3 py-2 text-xs font-semibold uppercase tracking-widest text-slate-400">
        {results.length} {results.length === 1 ? 'article' : 'articles'}
      </p>
      <ul>
        {results.map((article) => (
          <ArticleRow key={article.id} article={article} showCategory />
        ))}
      </ul>
    </div>
  )
}

function CategoryGrid({ grouped }: { grouped: [string, HelpArticle[]][] }) {
  if (grouped.length === 0) {
    return (
      <div className="rounded-card border border-slate-200 bg-white px-6 py-10 text-center dark:border-slate-800 dark:bg-slate-900">
        <BookOpen className="mx-auto h-8 w-8 text-slate-300 dark:text-slate-600" aria-hidden />
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          The help centre is being written. Check back shortly.
        </p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      {grouped.map(([category, rows]) => (
        <section
          key={category}
          className="rounded-card border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
        >
          <h2 className="flex items-center gap-2.5 px-3 text-base font-semibold text-slate-900 dark:text-white">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-400">
              <CategoryIcon category={category} className="h-4 w-4" />
            </span>
            {category}
          </h2>
          <ul className="mt-3">
            {rows.map((article) => (
              <ArticleRow key={article.id} article={article} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function SupportPrompt({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'mt-12 rounded-card border border-slate-200 bg-white px-6 py-8 text-center dark:border-slate-800 dark:bg-slate-900',
        className,
      )}
    >
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
        Still stuck on something
      </h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        Signed-in users can reach support from the help icon in the top bar, and the same articles
        are searchable from inside the app without losing your place.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-3">
        <Link to="/login" className={linkButtonClass('outline', 'md')}>
          Sign in
        </Link>
        <Link to="/register" className={linkButtonClass('primary', 'md')}>
          Start free trial
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ article

export function HelpArticlePage() {
  const { slug } = useParams<{ slug: string }>()

  const article = useQuery({
    queryKey: queryKeys.publicHelpArticle(slug ?? ''),
    queryFn: () => publicHelpApi.article(slug as string),
    enabled: Boolean(slug),
    retry: false,
  })

  // Fetched alongside so the foot of an article can offer the rest of its
  // category. It is the same cached list the index uses, so on the common path
  // — index, then an article — this costs nothing.
  const all = useQuery({
    queryKey: queryKeys.publicHelpSearch(),
    queryFn: () => publicHelpApi.search(),
    staleTime: 5 * 60_000,
  })

  if (article.isPending) {
    return (
      <HelpLayout>
        <PageLoader />
      </HelpLayout>
    )
  }

  if (article.isError || !article.data) {
    return (
      <HelpLayout>
        <HelpError>That article does not exist, or is no longer published.</HelpError>
      </HelpLayout>
    )
  }

  const current = article.data
  const related = (all.data ?? []).filter(
    (row) => row.category === current.category && row.slug !== current.slug,
  )

  return (
    <HelpLayout>
      <article className="mx-auto max-w-3xl">
        <Link
          to="/help"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Help centre
        </Link>

        <p className="mt-6 flex items-center gap-2 text-sm font-medium text-brand-600 dark:text-brand-400">
          <CategoryIcon category={current.category} className="h-4 w-4" />
          {current.category}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 dark:text-white">
          {current.title}
        </h1>

        {current.video_url && (
          <TutorialVideo
            url={current.video_url}
            provider={current.video_provider}
            seconds={current.video_duration_seconds}
          />
        )}

        {/* Bodies are plain text by design — see the seed migration. Rendering
            them pre-wrapped keeps the author's paragraphing and numbered steps
            without letting stored content introduce markup. */}
        <div className="mt-8 whitespace-pre-wrap text-base leading-relaxed text-slate-700 dark:text-slate-300">
          {current.body}
        </div>

        {related.length > 0 && (
          <section className="mt-12 border-t border-slate-200 pt-8 dark:border-slate-800">
            <h2 className="px-3 text-sm font-semibold uppercase tracking-widest text-slate-400">
              More in {current.category}
            </h2>
            <ul className="mt-2">
              {related.map((row) => (
                <ArticleRow key={row.id} article={row} />
              ))}
            </ul>
          </section>
        )}
      </article>

      <SupportPrompt className="mx-auto max-w-3xl" />
    </HelpLayout>
  )
}
