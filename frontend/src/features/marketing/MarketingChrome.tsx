import { Link } from 'react-router-dom'

import { cn } from '@/lib/cn'

/**
 * Chrome shared by every public, logged-out page — the landing page and the
 * help centre today, whatever marketing pages come next.
 *
 * Split out of `LandingPage` the moment a second page needed the same footer:
 * a footer that exists twice drifts, and the one link people follow when they
 * are stuck is the one that would go stale.
 */

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn('flex items-center gap-2', className)}>
      <img src="/rent.png" alt="RentFlow" className="h-9 w-9 shrink-0 rounded-lg" />
      <span
        className={cn(
          'whitespace-nowrap text-lg font-semibold text-slate-900 dark:text-white',
          compact && 'hidden sm:inline',
        )}
      >
        RentFlow Kenya
      </span>
    </span>
  )
}

/** A `to` starting with `#` is an anchor on the landing page; the footer sends
 *  those to `/#...` so they still work from a page that is not the landing
 *  page, where a bare `#features` would scroll to nothing. */
const FOOTER_COLUMNS = [
  {
    heading: 'Product',
    links: [
      { label: 'Features', to: '#features' },
      { label: 'How it works', to: '#how' },
      { label: 'Pricing', to: '#pricing' },
      { label: 'FAQ', to: '#faq' },
    ],
  },
  {
    heading: 'Learn',
    links: [
      { label: 'Help centre', to: '/help' },
      { label: 'Getting started', to: '/help/add-your-first-property' },
      { label: 'Collecting rent', to: '/help/collect-rent-through-mpesa' },
      { label: 'API documentation', to: '/help/api-keys-and-webhooks' },
    ],
  },
  {
    heading: 'Account',
    links: [
      { label: 'Sign in', to: '/login' },
      { label: 'Start free trial', to: '/register' },
      { label: 'Tenant portal', to: '/portal/login' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy policy', to: '/legal/privacy' },
      { label: 'Terms of service', to: '/legal/terms' },
      { label: 'Cookie policy', to: '/legal/cookies' },
    ],
  },
]

const FOOTER_LINK_CLASS =
  'text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'

export function MarketingFooter({ onLanding = false }: { onLanding?: boolean }) {
  return (
    <footer className="border-t border-slate-200 bg-slate-50 px-4 py-12 dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto grid grid-cols-1 max-w-6xl gap-10 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <Logo />
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-slate-500 dark:text-slate-400">
            Property management software built by Kastra Enterprises for the way rent is collected in Kenya.
          </p>
        </div>

        {FOOTER_COLUMNS.map((column) => (
          <div key={column.heading}>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{column.heading}</h3>
            <ul className="mt-4 space-y-2.5">
              {column.links.map((link) => (
                <li key={link.label}>
                  {link.to.startsWith('#') ? (
                    onLanding ? (
                      <a href={link.to} className={FOOTER_LINK_CLASS}>
                        {link.label}
                      </a>
                    ) : (
                      <Link to={`/${link.to}`} className={FOOTER_LINK_CLASS}>
                        {link.label}
                      </Link>
                    )
                  ) : (
                    <Link to={link.to} className={FOOTER_LINK_CLASS}>
                      {link.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mx-auto mt-10 flex max-w-6xl flex-col gap-3 border-t border-slate-200 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800 dark:text-slate-400">
        <p>&copy; {new Date().getFullYear()} Kastra Enterprises. RentFlow Kenya.</p>
        <p>Prices shown in Kenyan shillings and exclude VAT where applicable.</p>
      </div>
    </footer>
  )
}
