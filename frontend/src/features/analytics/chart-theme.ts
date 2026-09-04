/**
 * One palette for every chart in the app.
 *
 * Validated with the dataviz palette checker against the light surface: the three
 * categorical hues pass the lightness band, chroma floor, CVD separation
 * (worst adjacent ΔE 20.7 deutan), the normal-vision floor and 3:1 contrast.
 * Adding a fourth hue broke the amber↔red pair, so a fourth series folds into
 * "Other" or gets its own chart rather than a generated colour.
 *
 * Red is deliberately absent: it is reserved for status (overdue, failed) and
 * never doubles as a series colour.
 */
export const SERIES = {
  /** Money actually in the bank. */
  collected: '#1f8a5f',
  /** Anything projected or modelled rather than banked. */
  forecast: '#3b6fd4',
  /** A third categorical slot — utilities, fees, other income. */
  other: '#b0740e',
} as const

/** What was billed: a reference line the coloured series is read against, so it
 *  stays recessive rather than competing for attention. */
export const REFERENCE = '#94a3b8'

export const AXIS = {
  grid: '#e2e8f0',
  tick: '#64748b',
} as const

export const TOOLTIP_STYLE = {
  borderRadius: 8,
  border: '1px solid #e2e8f0',
  fontSize: 12,
  boxShadow: '0 4px 12px rgb(15 23 42 / 0.08)',
} as const
