/**
 * The RentFlow component kit.
 *
 * Hand-rolled rather than pulled from a library so the whole surface stays in
 * one readable file: every variant is a token lookup, and the touch-target and
 * focus rules the caretaker PWA needs are applied once, here.
 */
import { Loader2, X } from 'lucide-react'
import {
  cloneElement,
  createContext,
  forwardRef,
  isValidElement,
  useContext,
  useEffect,
  useId,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type LabelHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

import { cn } from '@/lib/cn'

// ---------------------------------------------------------------------- button

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'outline'
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon'

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600',
  secondary:
    'bg-slate-100 text-slate-800 hover:bg-slate-200 focus-visible:outline-slate-400 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700',
  ghost:
    'text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-slate-400 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100',
  danger: 'bg-danger-600 text-white hover:bg-danger-700 focus-visible:outline-danger-600',
  success: 'bg-money-600 text-white hover:bg-money-700 focus-visible:outline-money-600',
  outline:
    'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 focus-visible:outline-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800',
}

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-6 text-base gap-2',
  icon: 'h-10 w-10 justify-center',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = 'primary',
    size = 'md',
    loading,
    icon,
    children,
    disabled,
    // HTML defaults a bare <button> inside a form to type="submit", so a
    // Cancel or Close button in a dialog form would silently submit it. Every
    // real submit button in this app declares itself, so the safe default here
    // is the inert one.
    type = 'button',
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center rounded-lg font-medium transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-60',
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
})

/**
 * A link that looks like a button.
 *
 * Nesting an `<a>` inside a `<button>` is invalid HTML and breaks keyboard
 * navigation, so navigation actions use this instead of wrapping a Link.
 */
export function LinkButton({
  className,
  variant = 'primary',
  size = 'md',
  icon,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: ReactNode
}) {
  return (
    <a
      className={cn(
        'inline-flex items-center rounded-lg font-medium transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </a>
  )
}

export const linkButtonClass = (variant: ButtonVariant = 'primary', size: ButtonSize = 'md') =>
  cn(
    'inline-flex items-center rounded-lg font-medium transition-colors',
    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
    BUTTON_VARIANTS[variant],
    BUTTON_SIZES[size],
  )

// ------------------------------------------------------------------------ card

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-card border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900',
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800',
        className,
      )}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn('text-base font-semibold text-slate-900 dark:text-slate-100', className)} {...props} />
  )
}

export function CardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-slate-500 dark:text-slate-400', className)} {...props} />
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-5 py-4', className)} {...props} />
}

// ----------------------------------------------------------------------- badge

export type BadgeTone = 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'info'

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  brand: 'bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300',
  success: 'bg-money-50 text-money-700 dark:bg-money-700/25 dark:text-money-300',
  warn: 'bg-warn-50 text-warn-700 dark:bg-warn-700/25 dark:text-warn-300',
  danger: 'bg-danger-50 text-danger-700 dark:bg-danger-700/25 dark:text-danger-300',
  info: 'bg-sky-50 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
}

export function Badge({
  tone = 'neutral',
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
        BADGE_TONES[tone],
        className,
      )}
      {...props}
    />
  )
}

/** Status vocabularies shared across the app, so a colour always means one thing. */
export const UNIT_STATUS_TONE: Record<string, BadgeTone> = {
  vacant: 'warn',
  occupied: 'success',
  under_maintenance: 'danger',
  reserved: 'info',
  vacating: 'brand',
}

export const TENANCY_STATUS_TONE: Record<string, BadgeTone> = {
  active: 'success',
  expiring_soon: 'warn',
  expired: 'danger',
  notice_given: 'brand',
  vacated: 'neutral',
}

export const INVOICE_STATUS_TONE: Record<string, BadgeTone> = {
  pending: 'neutral',
  partially_paid: 'warn',
  paid: 'success',
  overdue: 'danger',
  cancelled: 'neutral',
}

export const PAYMENT_STATUS_TONE: Record<string, BadgeTone> = {
  pending: 'warn',
  confirmed: 'success',
  failed: 'danger',
  cancelled: 'neutral',
  reversed: 'danger',
}

export const MAINTENANCE_STATUS_TONE: Record<string, BadgeTone> = {
  submitted: 'warn',
  under_review: 'info',
  approved: 'info',
  rejected: 'danger',
  assigned: 'brand',
  in_progress: 'brand',
  completed: 'success',
  closed: 'neutral',
  cancelled: 'neutral',
}

export const PRIORITY_TONE: Record<string, BadgeTone> = {
  emergency: 'danger',
  urgent: 'warn',
  routine: 'neutral',
}

// ------------------------------------------------------------------ form fields

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn('block text-sm font-medium text-slate-700 dark:text-slate-300', className)}
      {...props}
    />
  )
}

const FIELD_BASE =
  'w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 ' +
  'focus:outline-none focus:ring-2 focus:ring-brand-500/30 disabled:bg-slate-50 disabled:text-slate-500 ' +
  'dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-800 dark:disabled:text-slate-500'

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }
>(function Input({ className, invalid, ...props }, ref) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        FIELD_BASE,
        invalid
          ? 'border-danger-500 focus:border-danger-500'
          : 'border-slate-300 focus:border-brand-500 dark:border-slate-600',
        className,
      )}
      {...props}
    />
  )
})

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }
>(function Textarea({ className, invalid, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        FIELD_BASE,
        'min-h-24 resize-y',
        invalid ? 'border-danger-500' : 'border-slate-300 focus:border-brand-500 dark:border-slate-600',
        className,
      )}
      {...props}
    />
  )
})

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }
>(function Select({ className, invalid, ...props }, ref) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        FIELD_BASE,
        'appearance-none bg-[length:1rem] bg-[right_0.6rem_center] bg-no-repeat pr-9',
        "bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='%2364748b'%3E%3Cpath fill-rule='evenodd' d='M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z' clip-rule='evenodd'/%3E%3C/svg%3E\")]",
        invalid ? 'border-danger-500' : 'border-slate-300 focus:border-brand-500 dark:border-slate-600',
        className,
      )}
      {...props}
    />
  )
})

export function Field({
  label,
  error,
  hint,
  required,
  children,
  className,
}: {
  label?: string
  error?: string
  hint?: string
  required?: boolean
  children: ReactNode
  className?: string
}) {
  // Generated once per Field instance and wired onto both the label
  // (`htmlFor`) and the control (`id`), so a screen reader announces the
  // label when the control receives focus — previously they were only
  // adjacent in the DOM, never programmatically associated, which is what
  // `getByLabel` (and a screen reader's own label lookup) both depend on.
  const generatedId = useId()
  const describedBy = error ? `${generatedId}-error` : hint ? `${generatedId}-hint` : undefined

  const control =
    label && isValidElement<{ id?: string; 'aria-describedby'?: string }>(children)
      ? cloneElement(children, {
          id: children.props.id ?? generatedId,
          'aria-describedby': describedBy,
        })
      : children

  return (
    <div className={cn('space-y-1.5', className)}>
      {label && (
        <Label htmlFor={generatedId}>
          {label}
          {required && <span className="ml-0.5 text-danger-600">*</span>}
        </Label>
      )}
      {control}
      {error ? (
        <p id={describedBy} className="text-sm text-danger-600 dark:text-danger-400">
          {error}
        </p>
      ) : hint ? (
        <p id={describedBy} className="text-xs text-slate-500 dark:text-slate-400">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------- alerts

type AlertTone = 'info' | 'success' | 'warn' | 'danger'

const ALERT_TONES: Record<AlertTone, string> = {
  info: 'border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-900/30 dark:text-sky-200',
  success:
    'border-money-100 bg-money-50 text-money-700 dark:border-money-700/40 dark:bg-money-700/20 dark:text-money-300',
  warn: 'border-warn-100 bg-warn-50 text-warn-700 dark:border-warn-700/40 dark:bg-warn-700/20 dark:text-warn-300',
  danger:
    'border-danger-100 bg-danger-50 text-danger-700 dark:border-danger-700/40 dark:bg-danger-700/20 dark:text-danger-300',
}

export function Alert({
  tone = 'info',
  title,
  children,
  className,
  icon,
}: {
  tone?: AlertTone
  title?: string
  children?: ReactNode
  className?: string
  icon?: ReactNode
}) {
  return (
    <div className={cn('flex gap-3 rounded-lg border px-4 py-3 text-sm', ALERT_TONES[tone], className)}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && 'mt-0.5')}>{children}</div>}
      </div>
    </div>
  )
}

// ----------------------------------------------------------------------- table

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto">
      <table className={cn('w-full border-collapse text-sm', className)} {...props} />
    </div>
  )
}

export function Th({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        'whitespace-nowrap border-b border-slate-200 px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400',
        className,
      )}
      {...props}
    />
  )
}

export function Td({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        'border-b border-slate-100 px-4 py-3 text-slate-700 dark:border-slate-800 dark:text-slate-300',
        className,
      )}
      {...props}
    />
  )
}

// ------------------------------------------------------------------ empty/skeleton

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center gap-3 px-6 py-14 text-center', className)}>
      {icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
          {icon}
        </div>
      )}
      <div>
        <p className="font-medium text-slate-900 dark:text-slate-100">{title}</p>
        {description && (
          <p className="mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">{description}</p>
        )}
      </div>
      {action}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-slate-200 dark:bg-slate-800', className)} />
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('h-5 w-5 animate-spin text-slate-400', className)} aria-label="Loading" />
}

export function PageLoader() {
  return (
    <div className="flex min-h-64 items-center justify-center">
      <Spinner className="h-6 w-6" />
    </div>
  )
}

// ---------------------------------------------------------------------- dialog

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // Stop the page behind the dialog scrolling under it on mobile.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4 dark:bg-black/60">
      <div aria-hidden className="absolute inset-0" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          'relative flex max-h-[92vh] w-full flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-card dark:bg-slate-900',
          widths[size],
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3 pb-safe dark:border-slate-800">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------------ tabs

const TabsContext = createContext<{ value: string; onChange: (value: string) => void } | null>(null)

export function Tabs({
  value,
  onChange,
  children,
  className,
}: {
  value: string
  onChange: (value: string) => void
  children: ReactNode
  className?: string
}) {
  return (
    <TabsContext.Provider value={{ value, onChange }}>
      <div
        className={cn(
          'flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-700',
          className,
        )}
        role="tablist"
      >
        {children}
      </div>
    </TabsContext.Provider>
  )
}

export function Tab({ value, children }: { value: string; children: ReactNode }) {
  const context = useContext(TabsContext)
  if (!context) throw new Error('<Tab> must be used inside <Tabs>')
  const active = context.value === value

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => context.onChange(value)}
      className={cn(
        '-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'border-brand-600 text-brand-700 dark:text-brand-400'
          : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-300',
      )}
    >
      {children}
    </button>
  )
}
