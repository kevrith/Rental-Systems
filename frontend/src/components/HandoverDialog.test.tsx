import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { HandoverCode, HandoverLink } from '@/api/types'
import { HandoverDialog } from '@/components/HandoverDialog'

const code: HandoverCode = {
  code: '482913',
  message: 'Hi Wanjiku, your RentFlow sign-in code is 482913. Do not share it.',
  phone_number: '+254712345678',
  recipient_name: 'Wanjiku Mwangi',
  expires_in_seconds: 900,
}

const link: HandoverLink = {
  link: 'https://app.test/sign/abc',
  message: 'Please sign: https://app.test/sign/abc',
  phone_number: '+254712345678',
  recipient_name: 'Wanjiku Mwangi',
  expires_in_seconds: 72 * 3600,
}

function open(run = vi.fn().mockResolvedValue(code), onClose = vi.fn()) {
  render(
    <HandoverDialog
      title="Sign-in code for Wanjiku"
      onClose={onClose}
      actions={[
        { key: 'code', title: 'One-time code', buttonLabel: 'Make a code', icon: null, run },
      ]}
    />,
  )
  return { run, onClose }
}

describe('HandoverDialog', () => {
  it('shows nothing secret until the person asks for it', () => {
    const { run } = open()

    expect(screen.queryByText('482913')).not.toBeInTheDocument()
    expect(run).not.toHaveBeenCalled()
  })

  it('shows the code once it is made, with WhatsApp and SMS links that carry the number and message', async () => {
    open()

    await userEvent.click(screen.getByRole('button', { name: 'Make a code' }))

    expect(await screen.findByText('482913')).toBeInTheDocument()
    const whatsapp = screen.getByRole('link', { name: /send on whatsapp/i })
    expect(whatsapp).toHaveAttribute(
      'href',
      `https://wa.me/254712345678?text=${encodeURIComponent(code.message)}`,
    )
    const sms = screen.getByRole('link', { name: /send by sms/i })
    expect(sms).toHaveAttribute('href', `sms:+254712345678?body=${encodeURIComponent(code.message)}`)
    expect(screen.getByText(/works for 15 minutes/i)).toBeInTheDocument()
  })

  it('shows a link as a link, not as a code, and says how long it lasts', async () => {
    open(vi.fn().mockResolvedValue(link))

    await userEvent.click(screen.getByRole('button', { name: 'Make a code' }))

    expect(await screen.findByText(link.message)).toBeInTheDocument()
    expect(screen.getByText(/works for 3 days/i)).toBeInTheDocument()
    expect(screen.queryByText(/cannot be shown again/i)).not.toBeInTheDocument()
  })

  it('shows the reason when the code cannot be made', async () => {
    open(vi.fn().mockRejectedValue(new Error('That account is disabled')))

    await userEvent.click(screen.getByRole('button', { name: 'Make a code' }))

    expect(await screen.findByText(/that account is disabled/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make a code' })).toBeEnabled()
  })

  it('closes from the Done button', async () => {
    const { onClose } = open()

    await userEvent.click(screen.getByRole('button', { name: 'Done' }))

    expect(onClose).toHaveBeenCalledOnce()
  })
})
