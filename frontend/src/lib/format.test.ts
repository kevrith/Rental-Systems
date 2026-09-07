import { describe, expect, it } from 'vitest'

import {
  amount,
  dateTime,
  errorMessage,
  humanize,
  initials,
  kes,
  relative,
  shortDate,
  today,
} from '@/lib/format'

/**
 * Every money value in the UI passes through `kes`, and every API failure the
 * user ever reads passes through `errorMessage`. Both are pure, both have real
 * edge cases, and until now neither had a single test.
 */

describe('kes', () => {
  it('formats a number as Kenyan shillings with two decimals', () => {
    expect(kes(25000)).toBe('KES 25,000.00')
  })

  it('accepts the strings the API actually returns for Decimal columns', () => {
    expect(kes('25000.50')).toBe('KES 25,000.50')
  })

  it('treats null and undefined as zero rather than showing NaN', () => {
    expect(kes(null)).toBe('KES 0.00')
    expect(kes(undefined)).toBe('KES 0.00')
  })

  it('falls back to zero for a value that is not a number', () => {
    expect(kes('not a number')).toBe('KES 0.00')
    expect(kes(Number.POSITIVE_INFINITY)).toBe('KES 0.00')
  })

  it('keeps the sign on a negative balance', () => {
    expect(kes(-1500)).toBe('KES -1,500.00')
  })

  it('abbreviates only above the compact thresholds', () => {
    expect(kes(2_400_000, { compact: true })).toBe('KES 2.4M')
    expect(kes(45_000, { compact: true })).toBe('KES 45K')
    // Below 10,000 the exact figure still fits, so it is not abbreviated.
    expect(kes(9_999, { compact: true })).toBe('KES 9,999.00')
  })

  it('abbreviates large negative amounts by magnitude', () => {
    expect(kes(-2_400_000, { compact: true })).toBe('KES -2.4M')
  })
})

describe('amount', () => {
  it('drops the currency prefix and the decimals', () => {
    expect(amount(25000.67)).toBe('25,001')
  })

  it('is zero for anything unparseable', () => {
    expect(amount('abc')).toBe('0')
    expect(amount(null)).toBe('0')
  })
})

describe('date formatting', () => {
  it('renders an ISO date in the short form', () => {
    expect(shortDate('2026-09-03')).toBe('3 Sep 2026')
  })

  it('accepts a Date as well as a string', () => {
    expect(shortDate(new Date('2026-01-31T00:00:00Z'))).toBe('31 Jan 2026')
  })

  it('shows an em dash rather than "Invalid Date"', () => {
    expect(shortDate(null)).toBe('—')
    expect(shortDate('')).toBe('—')
    expect(shortDate('not-a-date')).toBe('—')
    expect(dateTime(undefined)).toBe('—')
    expect(relative('nonsense')).toBe('—')
  })

  it('includes the time in dateTime', () => {
    expect(dateTime('2026-09-03T12:04:00Z')).toMatch(/^3 Sep 2026, \d{2}:\d{2}$/)
  })

  it('describes a past date relatively', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000)
    expect(relative(twoDaysAgo)).toBe('2 days ago')
  })

  it('gives today in the format a date input expects', () => {
    expect(today()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('humanize', () => {
  it('turns a snake_case enum value into a sentence', () => {
    expect(humanize('under_maintenance')).toBe('Under maintenance')
  })

  it('leaves a single word capitalised', () => {
    expect(humanize('vacant')).toBe('Vacant')
  })

  it('shows an em dash for nothing', () => {
    expect(humanize(null)).toBe('—')
    expect(humanize('')).toBe('—')
  })
})

describe('initials', () => {
  it('takes the first letter of the first two names', () => {
    expect(initials('Jane Wanjiru Kamau')).toBe('JW')
  })

  it('handles a single name', () => {
    expect(initials('Jane')).toBe('J')
  })

  it('ignores the extra whitespace a pasted name arrives with', () => {
    expect(initials('  jane   wanjiru  ')).toBe('JW')
  })

  it('is a question mark when there is no name', () => {
    expect(initials(null)).toBe('?')
  })
})

describe('errorMessage', () => {
  it('uses the API detail string, which is written for the user', () => {
    const error = { response: { data: { detail: 'Unit A1 already has a live tenancy' } } }
    expect(errorMessage(error)).toBe('Unit A1 already has a live tenancy')
  })

  it('reads the first message out of a FastAPI validation error list', () => {
    const error = {
      response: { data: { detail: [{ loc: ['body', 'amount'], msg: 'Amount must be positive' }] } },
    }
    expect(errorMessage(error)).toBe('Amount must be positive')
  })

  it('reads a detail object that carries its own message', () => {
    const error = { response: { data: { detail: { message: 'Rate limited' } } } }
    expect(errorMessage(error)).toBe('Rate limited')
  })

  it('falls back to an Error message when there is no response', () => {
    expect(errorMessage(new Error('Network Error'))).toBe('Network Error')
  })

  it('uses the supplied fallback for something with no message at all', () => {
    expect(errorMessage({}, 'Could not save')).toBe('Could not save')
    expect(errorMessage(null)).toBe('Something went wrong. Please try again.')
  })

  it('does not return an empty validation list as a message', () => {
    const error = { response: { data: { detail: [] } } }
    expect(errorMessage(error)).toBe('Something went wrong. Please try again.')
  })
})
