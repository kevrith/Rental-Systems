import {
  ArrowRight,
  BarChart3,
  Building2,
  Camera,
  Check,
  ChevronDown,
  ClipboardList,
  Database,
  FileCheck2,
  Gauge,
  KeyRound,
  Lock,
  Menu,
  MessageSquare,
  Minus,
  Plug,
  Receipt,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Users,
  Wallet,
  Wrench,
  X,
} from 'lucide-react'
import { Fragment, useState, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { ThemeToggle } from '@/components/ThemeToggle'
import { linkButtonClass } from '@/components/ui'
import { cn } from '@/lib/cn'
import { amount } from '@/lib/format'
import { useAuthStore } from '@/store/auth-store'

import { Logo, MarketingFooter } from './MarketingChrome'
import { ADD_ONS, FEATURE_MATRIX, PLANS, type Plan } from './plans'

/**
 * The public front door.
 *
 * Everything here is deliberately static — no queries, no auth calls — so the
 * page paints on a cold 3G connection before anything else in the app has
 * loaded. It reuses the product's own tokens (brand blue, money green, the
 * `rounded-card` radius) rather than a separate marketing palette, so someone
 * arriving from this page recognises the product they signed up for.
 */

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#how', label: 'How it works' },
  { href: '#roles', label: 'Who it is for' },
  { href: '#pricing', label: 'Pricing' },
  { href: '#faq', label: 'FAQ' },
  // The only entry that leaves the page, so it routes rather than scrolls.
  { href: '/help', label: 'Help' },
]

/** An anchor scrolls, a path routes — an `<a href="/help">` would reload the
 *  whole app to reach a page that is already in the bundle. */
function NavLink({
  href,
  className,
  onClick,
  children,
}: {
  href: string
  className: string
  onClick?: () => void
  children: ReactNode
}) {
  if (href.startsWith('#')) {
    return (
      <a href={href} className={className} onClick={onClick}>
        {children}
      </a>
    )
  }
  return (
    <Link to={href} className={className} onClick={onClick}>
      {children}
    </Link>
  )
}

// ------------------------------------------------------------------- primitives

function Section({ id, className, children }: { id?: string; className?: string; children: ReactNode }) {
  return (
    // `scroll-mt` keeps anchored headings clear of the sticky header.
    <section id={id} className={cn('scroll-mt-20 px-4 py-20 sm:py-24', className)}>
      <div className="mx-auto max-w-6xl">{children}</div>
    </section>
  )
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-widest text-brand-600 dark:text-brand-400">
      {children}
    </p>
  )
}

function SectionHeading({
  eyebrow,
  title,
  lead,
  align = 'center',
}: {
  eyebrow: string
  title: string
  lead?: string
  align?: 'center' | 'left'
}) {
  return (
    <div className={cn('max-w-2xl', align === 'center' && 'mx-auto text-center')}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl dark:text-white">
        {title}
      </h2>
      {lead && <p className="mt-4 text-base leading-relaxed text-slate-600 dark:text-slate-400">{lead}</p>}
    </div>
  )
}

// -------------------------------------------------------------------- top nav

function MarketingNav() {
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-slate-950/85">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link to="/" aria-label="RentFlow Kenya home">
          <Logo />
        </Link>

        <nav className="ml-6 hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          {/* Hidden by the wrapper, not by a `hidden` on the links themselves:
              `linkButtonClass` sets `inline-flex`, and Tailwind orders that
              after `hidden`, so the utility would lose on the element. */}
          <div className="hidden items-center gap-2 sm:flex">
            <Link to="/login" className={linkButtonClass('ghost', 'md')}>
              Sign in
            </Link>
            <Link to="/register" className={linkButtonClass('primary', 'md')}>
              Start free trial
            </Link>
          </div>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden dark:text-slate-300 dark:hover:bg-slate-800"
            aria-expanded={open}
            aria-label={open ? 'Close menu' : 'Open menu'}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-slate-200 bg-white px-4 py-3 lg:hidden dark:border-slate-800 dark:bg-slate-950">
          <nav className="flex flex-col">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:hidden">
            <Link to="/login" className={cn(linkButtonClass('outline', 'md'), 'justify-center')}>
              Sign in
            </Link>
            <Link to="/register" className={cn(linkButtonClass('primary', 'md'), 'justify-center')}>
              Start free trial
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}

// ----------------------------------------------------------------------- hero

/** A stylised snapshot of the overview screen. Illustrative, not live data —
 *  hence the "Sample data" chip rather than numbers that look like a claim. */
function ProductPreview() {
  const bars = [62, 74, 69, 83, 78, 91]
  const feed = [
    { name: 'Wanjiru M.', unit: 'Kilimani Court B4', value: 45000, code: 'M-Pesa' },
    { name: 'Otieno K.', unit: 'Riverside Mews 12', value: 62000, code: 'M-Pesa' },
    { name: 'Achieng P.', unit: 'Ngong View A2', value: 38500, code: 'Bank' },
  ]

  return (
    <div className="rounded-card border border-slate-200 bg-white p-4 shadow-xl shadow-slate-900/5 sm:p-5 dark:border-slate-800 dark:bg-slate-900 dark:shadow-black/40">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900 dark:text-white">Overview</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">September, all properties</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
          Sample data
        </span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-money-100 bg-money-50 p-3 dark:border-money-700/40 dark:bg-money-700/10">
          <p className="text-[11px] font-medium text-money-700 dark:text-money-300">Collected</p>
          <p className="mt-1 text-base font-semibold text-slate-900 tabular-nums sm:text-lg dark:text-white">
            1.24M
          </p>
        </div>
        <div className="rounded-lg border border-warn-100 bg-warn-50 p-3 dark:border-warn-700/40 dark:bg-warn-700/10">
          <p className="text-[11px] font-medium text-warn-700 dark:text-warn-300">In arrears</p>
          <p className="mt-1 text-base font-semibold text-slate-900 tabular-nums sm:text-lg dark:text-white">
            186K
          </p>
        </div>
        <div className="rounded-lg border border-brand-100 bg-brand-50 p-3 dark:border-brand-700/40 dark:bg-brand-700/10">
          <p className="text-[11px] font-medium text-brand-700 dark:text-brand-300">Occupancy</p>
          <p className="mt-1 text-base font-semibold text-slate-900 tabular-nums sm:text-lg dark:text-white">
            94%
          </p>
        </div>
      </div>

      <div className="mt-5 flex h-24 items-end gap-2" aria-hidden>
        {bars.map((height, index) => (
          <div key={index} className="flex-1 rounded-t-md bg-brand-100 dark:bg-brand-900/60">
            <div
              className="w-full rounded-t-md bg-brand-600"
              style={{ height: `${height}%`, minHeight: '4px' }}
            />
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-slate-400 dark:text-slate-500">Collection rate, last six months</p>

      <div className="mt-5 space-y-2">
        {feed.map((row) => (
          <div
            key={row.name}
            className="flex items-center gap-3 rounded-lg border border-slate-100 px-3 py-2 dark:border-slate-800"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-money-50 text-money-600 dark:bg-money-700/15 dark:text-money-300">
              <Check className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-slate-900 dark:text-slate-100">{row.name}</p>
              <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">{row.unit}</p>
            </div>
            <div className="text-right">
              <p className="text-xs font-semibold text-slate-900 tabular-nums dark:text-white">
                {amount(row.value)}
              </p>
              <p className="text-[11px] text-slate-400 dark:text-slate-500">{row.code}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Hero() {
  return (
    <div className="relative overflow-hidden">
      {/* Brand wash behind the fold — the only decorative colour on the page. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[32rem] bg-linear-to-b from-brand-50 via-slate-50 to-slate-50 dark:from-brand-900/25 dark:via-slate-950 dark:to-slate-950"
        aria-hidden
      />

      <div className="relative mx-auto grid grid-cols-1 max-w-6xl items-center gap-12 px-4 py-16 sm:py-24 lg:grid-cols-2">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-medium text-brand-700 dark:border-brand-800 dark:bg-slate-900 dark:text-brand-300">
            <Sparkles className="h-3.5 w-3.5" />
            Built in Kenya, for Kenyan Landlords, agencies and tenants
          </span>

          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl dark:text-white">
            Rent collected, reconciled and receipted{' '}
            <span className="text-brand-600 dark:text-brand-400">before you open your laptop</span>.
          </h1>

          <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-600 dark:text-slate-300">
            RentFlow is property management built around how Kenya actually pays. M-Pesa first, WhatsApp for
            the reminders, eTIMS receipts that satisfy KRA, and a caretaker app that keeps working when the
            network does not.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link to="/register" className={linkButtonClass('primary', 'lg')}>
              Start your 30-day free trial
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a href="#pricing" className={linkButtonClass('outline', 'lg')}>
              See pricing
            </a>
          </div>

          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
            No card required. Full feature access. Cancel whenever you like.
          </p>

          <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-slate-200 pt-8 sm:grid-cols-4 dark:border-slate-800">
            {[
              { term: 'M-Pesa', detail: 'STK push and C2B, auto-matched' },
              { term: 'WhatsApp', detail: 'Reminders and receipts' },
              { term: 'Offline', detail: 'Caretaker PWA on any phone' },
              { term: 'eTIMS', detail: 'KRA-compliant receipts' },
            ].map((item) => (
              <div key={item.term}>
                <dt className="text-sm font-semibold text-slate-900 dark:text-white">{item.term}</dt>
                <dd className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                  {item.detail}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="lg:pl-6">
          <ProductPreview />
        </div>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------- features

const FEATURES = [
  {
    icon: Wallet,
    title: 'M-Pesa collection that reconciles itself',
    body: "STK push, paybill and till payments land against the right tenancy automatically. Part payments, overpayments and the ones paid from a relative's number all resolve without a spreadsheet.",
  },
  {
    icon: Receipt,
    title: 'Invoices and eTIMS receipts',
    body: 'Rent, service charge, water and penalties invoiced on your billing day, with a KRA-compliant electronic receipt issued the moment money clears.',
  },
  {
    icon: MessageSquare,
    title: 'Reminders on the channel they read',
    body: 'WhatsApp first, SMS as the fallback, email for the paper trail. Templates you control, escalating on their own as arrears age.',
  },
  {
    icon: Gauge,
    title: 'Arrears you can actually work',
    body: 'A ranked worklist instead of a report: who owes, how long, what was already sent, and the next step ready to fire.',
  },
  {
    icon: Wrench,
    title: 'Maintenance, vendors and approvals',
    body: 'Tenants raise a request from the portal, caretakers photograph the job, vendors are rated on cost and turnaround, and spend above your limit waits for approval.',
  },
  {
    icon: Camera,
    title: 'Inspections and meter readings',
    body: 'Move-in and move-out condition captured with photos on a phone, water and power readings billed straight onto the next invoice.',
  },
  {
    icon: Smartphone,
    title: 'A caretaker app built for a corridor',
    body: 'Installable, one-thumb, 44px targets, and offline-first. Readings, visitors and job updates queue on the handset and sync when signal returns.',
  },
  {
    icon: Users,
    title: 'Portals for tenants and owners',
    body: 'Tenants see their statement, pay and raise issues. Owners see their own properties, statements and disbursements, and nothing that is not theirs.',
  },
  {
    icon: BarChart3,
    title: 'Reporting that answers the question',
    body: 'Collection rate, arrears ageing, vacancy, maintenance cost per unit and owner statements, on a schedule, delivered to WhatsApp or email.',
  },
  {
    icon: ClipboardList,
    title: 'Screening before the keys',
    body: 'Applications, guarantor and previous-landlord checks collected over public links, scored and filed against the tenancy.',
  },
  {
    icon: Plug,
    title: 'An API when you outgrow the UI',
    body: 'Scoped API keys, outbound webhooks and a documented public API, so accounting systems and your own tooling stay in step.',
  },
  {
    icon: Database,
    title: 'Your data stays yours',
    body: 'Full export whenever you want it, in formats a human and a machine can both read. No hostage-taking on the way out.',
  },
]

function Features() {
  return (
    <Section id="features" className="bg-white dark:bg-slate-900">
      <SectionHeading
        eyebrow="The product"
        title="Every part of the month, in one place"
        lead="Most landlords run on three WhatsApp groups, one spreadsheet and a caretaker with a good memory. RentFlow replaces that with a system that closes the month on its own."
      />

      <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="rounded-card border border-slate-200 bg-slate-50 p-6 transition-colors hover:border-brand-200 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-brand-800"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300">
              <feature.icon className="h-5 w-5" />
            </span>
            <h3 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">{feature.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{feature.body}</p>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------- how it works

const STEPS = [
  {
    title: 'Bring your portfolio across',
    body: 'Import properties, units and tenants from a spreadsheet, or add your first block in a few minutes. Existing balances come with them, so nothing restarts at zero.',
  },
  {
    title: 'Connect M-Pesa and WhatsApp',
    body: 'Point your paybill or till at RentFlow and pick the reminder templates. Payments start matching themselves against tenancies from the first shilling.',
  },
  {
    title: 'Let the month run itself',
    body: 'Invoices go out on your billing day, reminders escalate on their own, receipts are issued on payment, and you open the app to a list of exceptions rather than a list of chores.',
  },
]

function HowItWorks() {
  return (
    <Section id="how">
      <SectionHeading
        eyebrow="Getting started"
        title="Live before the next rent day"
        lead="Nothing to install, no server to run, no consultant to book."
      />

      <ol className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
        {STEPS.map((step, index) => (
          <li
            key={step.title}
            className="rounded-card border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
              {index + 1}
            </span>
            <h3 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">{step.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{step.body}</p>
          </li>
        ))}
      </ol>
    </Section>
  )
}

// ---------------------------------------------------------------------- roles

const ROLES = [
  {
    icon: Building2,
    title: 'Landlords',
    body: 'One block or five. See what came in, what is late, and what needs a decision — without calling anyone to ask.',
  },
  {
    icon: Users,
    title: 'Agencies',
    body: 'Manage for owners with commission, disbursements and per-owner statements handled, and an audit trail behind every shilling.',
  },
  {
    icon: Wrench,
    title: 'Caretakers',
    body: "A phone app for the actual job: today's tasks, meter readings, visitor log and job photos, working offline in the corridor.",
  },
  {
    icon: Smartphone,
    title: 'Tenants',
    body: 'Statement, receipts, lease documents and maintenance requests in a portal, so the same three questions stop arriving by text.',
  },
  {
    icon: FileCheck2,
    title: 'Property owners',
    body: 'A read-only view of their own properties, statements and disbursements. Transparency without another phone call.',
  },
  {
    icon: KeyRound,
    title: 'Finance and admin',
    body: 'Bank reconciliation, approval chains, eTIMS receipts and exports that reconcile to the accounting system without re-keying.',
  },
]

function Roles() {
  return (
    <Section id="roles" className="bg-white dark:bg-slate-900">
      <SectionHeading
        eyebrow="Who it is for"
        title="One system, six very different days"
        lead="Everyone signs into the same account and lands somewhere built for the job they actually do."
      />

      <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {ROLES.map((role) => (
          <div key={role.title} className="flex gap-4">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-money-50 text-money-700 dark:bg-money-700/15 dark:text-money-300">
              <role.icon className="h-5 w-5" />
            </span>
            <div>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">{role.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{role.body}</p>
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}

// -------------------------------------------------------------------- pricing

type Billing = 'monthly' | 'annual'

function priceLabel(plan: Plan, billing: Billing) {
  if (plan.monthly === null || plan.annual === null) return null
  // The annual rate is twelve months for the price of ten, shown as the
  // effective monthly figure so the two columns compare like for like.
  return billing === 'annual' ? Math.round(plan.annual / 12) : plan.monthly
}

function PlanCard({ plan, billing }: { plan: Plan; billing: Billing }) {
  const price = priceLabel(plan, billing)

  return (
    <div
      className={cn(
        'flex flex-col rounded-card border p-6',
        plan.featured
          ? 'border-brand-600 bg-white shadow-lg shadow-brand-600/10 ring-1 ring-brand-600 dark:bg-slate-900'
          : 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{plan.name}</h3>
        {plan.featured && (
          <span className="rounded-full bg-brand-600 px-2.5 py-1 text-[11px] font-semibold text-white">
            Most popular
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{plan.bestFor}</p>

      <div className="mt-6 min-h-20">
        {price === null ? (
          <p className="text-3xl font-semibold text-slate-900 dark:text-white">Let us talk</p>
        ) : (
          <p className="flex items-baseline gap-1.5">
            <span className="text-sm font-medium text-slate-500 dark:text-slate-400">KES</span>
            <span className="text-4xl font-semibold tracking-tight text-slate-900 tabular-nums dark:text-white">
              {amount(price)}
            </span>
            <span className="text-sm text-slate-500 dark:text-slate-400">/ month</span>
          </p>
        )}
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {price === null
            ? 'Priced on portfolio size and integrations'
            : billing === 'annual'
              ? `Billed KES ${amount(plan.annual)} a year — two months free`
              : 'Billed monthly, no commitment'}
        </p>
      </div>

      <div className="mt-6 rounded-lg bg-slate-50 px-3 py-2.5 dark:bg-slate-800/60">
        <p className="text-sm font-medium text-slate-900 dark:text-white">{plan.unitsIncluded}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">Then {plan.extraUnit}</p>
      </div>

      <ul className="mt-6 flex-1 space-y-3">
        {plan.highlights.map((item) => (
          <li key={item} className="flex gap-2.5 text-sm text-slate-600 dark:text-slate-300">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-money-600 dark:text-money-400" aria-hidden />
            <span>{item}</span>
          </li>
        ))}
      </ul>

      <Link
        to={plan.id === 'enterprise' ? '/register?plan=enterprise' : `/register?plan=${plan.id}`}
        className={cn(
          linkButtonClass(plan.featured ? 'primary' : 'outline', 'md'),
          'mt-8 w-full justify-center',
        )}
      >
        {plan.id === 'enterprise' ? 'Talk to us' : 'Start free trial'}
      </Link>
    </div>
  )
}

function MatrixCell({ value }: { value: string | boolean }) {
  if (value === true) {
    return (
      <>
        <Check className="mx-auto h-4 w-4 text-money-600 dark:text-money-400" aria-hidden />
        <span className="sr-only">Included</span>
      </>
    )
  }
  if (value === false) {
    return (
      <>
        <Minus className="mx-auto h-4 w-4 text-slate-300 dark:text-slate-600" aria-hidden />
        <span className="sr-only">Not included</span>
      </>
    )
  }
  return <span className="text-slate-700 dark:text-slate-300">{value}</span>
}

function ComparisonTable() {
  return (
    <div className="mt-16">
      <h3 className="text-center text-lg font-semibold text-slate-900 dark:text-white">
        Compare the plans in full
      </h3>
      <p className="mt-2 text-center text-xs text-slate-500 sm:hidden dark:text-slate-400">
        Swipe the table sideways to see every plan.
      </p>

      {/* Wide table scrolls inside itself rather than pushing the page sideways. */}
      <div className="mt-6 overflow-x-auto rounded-card border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th className="px-4 py-3.5 text-left font-medium sm:px-5 text-slate-500 dark:text-slate-400">
                Feature
              </th>
              {PLANS.map((plan) => (
                <th
                  key={plan.id}
                  className={cn(
                    'px-4 py-3.5 text-center font-semibold sm:px-5',
                    plan.featured ? 'text-brand-700 dark:text-brand-300' : 'text-slate-900 dark:text-white',
                  )}
                >
                  {plan.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FEATURE_MATRIX.map((group) => (
              <Fragment key={group.group}>
                <tr className="bg-slate-50 dark:bg-slate-800/50">
                  <th
                    colSpan={PLANS.length + 1}
                    className="px-4 py-2 text-left text-xs font-semibold sm:px-5 uppercase tracking-wider text-slate-500 dark:text-slate-400"
                  >
                    {group.group}
                  </th>
                </tr>
                {group.rows.map((row) => (
                  <tr key={row.label} className="border-t border-slate-100 dark:border-slate-800/70">
                    <th
                      scope="row"
                      className="px-4 py-3 text-left font-normal sm:px-5 text-slate-600 dark:text-slate-400"
                    >
                      {row.label}
                    </th>
                    {row.values.map((value, index) => (
                      <td key={PLANS[index].id} className="px-4 py-3 text-center sm:px-5">
                        <MatrixCell value={value} />
                      </td>
                    ))}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-center text-sm text-slate-500 dark:text-slate-400">
        The help centre is open to everyone, on every plan and before you have an account.{' '}
        <Link to="/help" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
          Read it now
        </Link>
        .
      </p>
    </div>
  )
}

function AddOns() {
  return (
    <div className="mt-16">
      <h3 className="text-center text-lg font-semibold text-slate-900 dark:text-white">
        Add only what you need
      </h3>
      <p className="mx-auto mt-2 max-w-xl text-center text-sm text-slate-600 dark:text-slate-400">
        Every add-on is switched on and off from your settings, and billed with your subscription.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ADD_ONS.map((addOn) => (
          <div
            key={addOn.name}
            className="rounded-card border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex items-start justify-between gap-3">
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">{addOn.name}</h4>
              <span className="shrink-0 rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-700 dark:bg-brand-900/40 dark:text-brand-300">
                {addOn.price}
              </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
              {addOn.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

function Pricing() {
  const [billing, setBilling] = useState<Billing>('annual')

  return (
    <Section id="pricing">
      <SectionHeading
        eyebrow="Pricing"
        title="Priced per portfolio, not per headache"
        lead="Thirty days free on any plan, with everything switched on. Move up or down whenever your portfolio does."
      />

      <div className="mt-8 flex justify-center">
        <div
          role="radiogroup"
          aria-label="Billing period"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-800 dark:bg-slate-900"
        >
          {(['monthly', 'annual'] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={billing === option}
              onClick={() => setBilling(option)}
              className={cn(
                'rounded-md px-4 py-2 text-sm font-medium transition-colors',
                billing === option
                  ? 'bg-brand-600 text-white'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white',
              )}
            >
              {option === 'monthly' ? 'Monthly' : 'Annual'}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-3 text-center text-xs font-medium text-money-700 dark:text-money-400">
        Annual billing gives you two months free
      </p>

      <div className="mt-12 grid grid-cols-1 gap-6 lg:grid-cols-4">
        {PLANS.map((plan) => (
          <PlanCard key={plan.id} plan={plan} billing={billing} />
        ))}
      </div>

      <p className="mt-8 text-center text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        A 0.5% platform fee applies to rent collected through RentFlow, capped at KES 500 per transaction.
        Non-profit and faith-based organisations get 20% off, and each referral that converts earns you a free
        month.
      </p>

      <AddOns />
      <ComparisonTable />
    </Section>
  )
}

// ------------------------------------------------------------------- security

const SECURITY = [
  {
    icon: Lock,
    title: 'Encrypted per organisation',
    body: 'Tenant identity numbers and bank details are held under an envelope key unique to your account, not one shared across the platform.',
  },
  {
    icon: ShieldCheck,
    title: 'Kenya Data Protection Act 2019',
    body: 'Consent, retention, subject-access and deletion requests are built into the product rather than promised in a policy page.',
  },
  {
    icon: FileCheck2,
    title: 'Tamper-evident audit trail',
    body: 'Every financial action is hash-chained, so an altered record is detectable rather than merely discouraged.',
  },
  {
    icon: KeyRound,
    title: 'Access you control',
    body: 'Role-based permissions, two-factor authentication, passkeys, IP allowlisting and per-role session timeouts.',
  },
]

function Security() {
  return (
    <Section className="bg-white dark:bg-slate-900">
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:items-center">
        <SectionHeading
          align="left"
          eyebrow="Trust"
          title="Rent data is financial data"
          lead="You are handing over the money and the identity documents of everyone in your buildings. That deserves more than a padlock icon."
        />

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {SECURITY.map((item) => (
            <div key={item.title}>
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                <item.icon className="h-4.5 w-4.5" />
              </span>
              <h3 className="mt-3 text-sm font-semibold text-slate-900 dark:text-white">{item.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{item.body}</p>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}

// ------------------------------------------------------------------------ faq

const FAQS = [
  {
    q: 'What happens after the 30 days?',
    a: 'Nothing disappears. The account moves to read-only until you pick a plan, so your data sits waiting rather than being deleted. No card is taken to start the trial.',
  },
  {
    q: 'How does the M-Pesa side actually work?',
    a: "You point an existing paybill or till at RentFlow, or we help you register one. Payments arrive against the tenancy automatically, including the awkward ones — part payments, overpayments and rent sent from someone else's number.",
  },
  {
    q: 'How are units counted for billing?',
    a: 'By the number of active units in your account, not by tenants or logins. A vacant unit still counts, because it still occupies a listing, a vacancy report and an inspection schedule.',
  },
  {
    q: 'Can I move between plans?',
    a: 'Any time, in either direction. Moving up takes effect immediately and is prorated; moving down applies at your next billing date so nothing is cut off mid-month.',
  },
  {
    q: 'Does it work when the network is bad?',
    a: 'The caretaker app is offline-first. Readings, visitor entries and job updates are captured on the handset and sync themselves once signal returns, so a basement corridor does not stop the work.',
  },
  {
    q: 'Can I get my data out?',
    a: 'Yes, whenever you want, without asking. Exports cover properties, units, tenants, tenancies, payments and documents, in formats a spreadsheet and an accounting system can both read.',
  },
  {
    q: 'Do tenants have to install anything?',
    a: 'No. The tenant portal opens in any browser, and reminders and receipts arrive on WhatsApp or SMS. Tenants who want it can install the portal to their home screen.',
  },
  {
    q: 'We are an agency managing for other owners. Does that fit?',
    a: 'That is what agency mode is for: commission handling, owner disbursements, per-owner statements and a read-only owner portal, all scoped so each owner sees only their own properties.',
  },
]

function Faq() {
  return (
    <Section id="faq">
      <SectionHeading eyebrow="Questions" title="The things people ask first" />

      <div className="mx-auto mt-12 max-w-3xl divide-y divide-slate-200 rounded-card border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
        {FAQS.map((faq) => (
          // <details> rather than a hand-rolled accordion: keyboard, screen
          // reader and in-page find all work without any state of our own.
          <details key={faq.q} className="group px-5 py-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-medium text-slate-900 dark:text-white">
              {faq.q}
              <ChevronDown
                className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
                aria-hidden
              />
            </summary>
            <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{faq.a}</p>
          </details>
        ))}
      </div>
    </Section>
  )
}

// ------------------------------------------------------------------ final CTA

function FinalCta() {
  return (
    <Section className="bg-white dark:bg-slate-900">
      <div className="rounded-card bg-brand-600 px-6 py-14 text-center sm:px-12">
        <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Close next month without chasing anyone
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-brand-50">
          Set up your first property in an afternoon and let the invoices, reminders and receipts run
          themselves from there.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            to="/register"
            className="inline-flex h-12 items-center gap-2 rounded-lg bg-white px-6 text-base font-medium text-brand-700 transition-colors hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            Start your free trial
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/login"
            className="inline-flex h-12 items-center rounded-lg border border-brand-300/60 px-6 text-base font-medium text-white transition-colors hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            Sign in
          </Link>
        </div>
        <p className="mt-5 text-sm text-brand-100">30 days free. No card. Cancel any time.</p>
      </div>
    </Section>
  )
}

// ----------------------------------------------------------------------- page

export function LandingPage() {
  const accessToken = useAuthStore((state) => state.accessToken)

  // Someone already signed in has no use for the sales pitch — `/dashboard`
  // resolves them to the home screen their role actually uses.
  if (accessToken) return <Navigate to="/dashboard" replace />

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <MarketingNav />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Roles />
        <Pricing />
        <Security />
        <Faq />
        <FinalCta />
      </main>
      <MarketingFooter onLanding />
    </div>
  )
}
