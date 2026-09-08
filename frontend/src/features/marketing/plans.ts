/**
 * The published price list (masterplan, section 10 "Pricing Strategy").
 *
 * These are marketing numbers, deliberately hard-coded rather than fetched:
 * there is no billing engine yet, and `SubscriptionPlan` on the backend only
 * records which plan an organisation sits on. When billing lands this file is
 * the seed for it, and the ids below already match the backend enum values.
 */

export type PlanId = 'starter' | 'professional' | 'business' | 'enterprise'

export interface Plan {
  id: PlanId
  name: string
  bestFor: string
  /** KES per month on monthly billing. `null` means "quoted, not listed". */
  monthly: number | null
  /** KES per year on annual billing — two months free against the monthly rate. */
  annual: number | null
  unitsIncluded: string
  /** What each unit past the included ceiling costs, per month. */
  extraUnit: string
  highlights: string[]
  /** The plan the pricing table leads with. */
  featured?: boolean
}

export const PLANS: Plan[] = [
  {
    id: 'starter',
    name: 'Starter',
    bestFor: 'Individual landlords with one block',
    monthly: 2000,
    annual: 20000,
    unitsIncluded: 'Up to 10 units',
    extraUnit: 'KES 150 / unit / month',
    highlights: [
      '1 property, 3 staff logins, 1 caretaker',
      'M-Pesa collection and auto-reconciliation',
      'WhatsApp and SMS rent reminders',
      'Tenant portal and caretaker PWA',
      '5GB document vault',
    ],
  },
  {
    id: 'professional',
    name: 'Professional',
    bestFor: 'Small agencies managing for owners',
    monthly: 8000,
    annual: 80000,
    unitsIncluded: 'Up to 50 units',
    extraUnit: 'KES 120 / unit / month',
    highlights: [
      'Up to 10 properties, 10 staff, 5 caretakers',
      'Agency mode with owner statements',
      '5 owner portal invites',
      'eTIMS receipts included',
      '20GB document vault, email support',
    ],
    featured: true,
  },
  {
    id: 'business',
    name: 'Business',
    bestFor: 'Medium agencies and multi-site portfolios',
    monthly: 20000,
    annual: 200000,
    unitsIncluded: 'Up to 200 units',
    extraUnit: 'KES 100 / unit / month',
    highlights: [
      'Unlimited properties, 30 staff, 20 caretakers',
      '20 owner portal invites',
      'Public API and outbound webhooks',
      'Custom report builder and scheduled delivery',
      '100GB vault, email and WhatsApp support',
    ],
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    bestFor: 'Large corporates, REITs and institutions',
    monthly: null,
    annual: null,
    unitsIncluded: 'Unlimited units',
    extraUnit: 'Negotiated',
    highlights: [
      'Unlimited staff, caretakers and owner invites',
      'White-label branding on portals and documents',
      'IP allowlisting and per-role session policy',
      'Bespoke API rate limits and Parquet data drops',
      'Named account manager and custom onboarding',
    ],
  },
]

export interface FeatureRow {
  label: string
  /** One value per plan, in `PLANS` order. `true`/`false` render as a tick or dash. */
  values: (string | boolean)[]
}

/** Plan differentiation, straight from the masterplan's comparison table. */
export const FEATURE_MATRIX: { group: string; rows: FeatureRow[] }[] = [
  {
    group: 'Portfolio',
    rows: [
      { label: 'Units included', values: ['10', '50', '200', 'Unlimited'] },
      { label: 'Properties', values: ['1', 'Up to 10', 'Unlimited', 'Unlimited'] },
      { label: 'Staff logins', values: ['3', '10', '30', 'Custom'] },
      { label: 'Caretaker accounts', values: ['1', '5', '20', 'Custom'] },
      { label: 'Agency and owner mode', values: ['Owner only', 'Both', 'Both', 'Both'] },
      { label: 'Owner portal invites', values: [false, '5', '20', 'Unlimited'] },
    ],
  },
  {
    group: 'Money',
    rows: [
      { label: 'M-Pesa collection and reconciliation', values: [true, true, true, true] },
      { label: 'Bank statement reconciliation', values: [true, true, true, true] },
      { label: 'Arrears escalation ladder', values: [true, true, true, true] },
      { label: 'eTIMS receipts', values: ['Add-on', true, true, true] },
      { label: 'Owner disbursements and statements', values: [false, true, true, true] },
    ],
  },
  {
    group: 'Operations',
    rows: [
      { label: 'Caretaker PWA, works offline', values: [true, true, true, true] },
      { label: 'Maintenance, vendors and inspections', values: [true, true, true, true] },
      { label: 'Tenant screening and applications', values: [true, true, true, true] },
      { label: 'Vacancy listings and marketing', values: ['Add-on', true, true, true] },
      { label: 'Bulk import and bulk actions', values: [false, true, true, true] },
    ],
  },
  {
    group: 'Platform',
    rows: [
      { label: 'Document vault', values: ['5GB', '20GB', '100GB', 'Custom'] },
      { label: 'Public API and webhooks', values: ['Add-on', 'Add-on', true, true] },
      { label: 'Custom report builder', values: [false, true, true, true] },
      { label: 'White label', values: [false, false, false, true] },
      { label: 'Support', values: ['Help centre', 'Email', 'Email + WhatsApp', 'Account manager'] },
    ],
  },
]

export interface AddOn {
  name: string
  price: string
  description: string
}

export const ADD_ONS: AddOn[] = [
  {
    name: 'eTIMS compliance module',
    price: 'KES 1,000 / month',
    description: 'KRA-compliant electronic receipts issued the moment rent clears.',
  },
  {
    name: 'Advanced analytics',
    price: 'KES 2,000 / month',
    description: 'Predictive arrears risk, portfolio benchmarking and cohort retention.',
  },
  {
    name: 'Vacancy marketing portal',
    price: 'KES 1,000 / month',
    description: 'Public listing pages built to be pasted straight into WhatsApp groups.',
  },
  {
    name: 'Open API access',
    price: 'KES 3,000 / month',
    description: 'API keys and webhooks on Starter and Professional. Included from Business.',
  },
  {
    name: 'Extra document storage',
    price: 'KES 500 / month',
    description: 'An additional 50GB in the encrypted property and tenant vault.',
  },
  {
    name: 'Extra SMS bundle',
    price: 'KES 500',
    description: '500 additional SMS on top of the allowance bundled with your plan.',
  },
]
