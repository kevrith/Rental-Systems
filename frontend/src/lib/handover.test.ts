import { describe, expect, it } from 'vitest'

import { lifetimeLabel, phoneDigits, smsUrl, whatsappShareUrl, whatsappUrl } from './handover'

describe('handover links', () => {
  it('strips everything but digits for WhatsApp', () => {
    expect(phoneDigits('+254 712-345 678')).toBe('254712345678')
  })

  it('builds a wa.me link with the message encoded', () => {
    const url = whatsappUrl('+254712345678', 'Your code is 123456 & it expires')
    expect(url).toBe(
      'https://wa.me/254712345678?text=Your%20code%20is%20123456%20%26%20it%20expires',
    )
  })

  it('builds a share link with no recipient', () => {
    expect(whatsappShareUrl('Please send me a link')).toBe(
      'https://wa.me/?text=Please%20send%20me%20a%20link',
    )
  })

  it('builds an sms: link that keeps the plus sign on the number', () => {
    expect(smsUrl('+254712345678', 'Hi there')).toBe('sms:+254712345678?body=Hi%20there')
  })

  it('does not let a link in the message break out of the query string', () => {
    const url = whatsappUrl('+254712345678', 'sign: https://x.test/sign/abc?a=1&b=2')
    expect(url.split('?')).toHaveLength(2)
    expect(url).toContain('%26b%3D2')
  })

  it('describes lifetimes in plain words', () => {
    expect(lifetimeLabel(900)).toBe('15 minutes')
    expect(lifetimeLabel(60)).toBe('1 minute')
    expect(lifetimeLabel(7200)).toBe('2 hours')
    expect(lifetimeLabel(72 * 3600)).toBe('3 days')
  })
})
