import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authApi } from '@/api/auth'

import { PinLoginPage } from './PinLoginPage'

vi.mock('@/api/auth', () => ({
  authApi: {
    pinLogin: vi.fn(),
    pinEnroll: vi.fn(),
    me: vi.fn(),
  },
}))

const tokens = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }

function renderPage() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PinLoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(authApi.me).mockResolvedValue({ id: 'u1', role: 'caretaker' } as never)
})

describe('PinLoginPage', () => {
  it('keeps the sign-in button off until the number and all six digits are in', async () => {
    renderPage()
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toBeDisabled()

    await userEvent.type(screen.getByLabelText(/phone number/i), '0712345678')
    await userEvent.type(screen.getByLabelText(/^PIN/), '48291')
    expect(button).toBeDisabled()

    await userEvent.type(screen.getByLabelText(/^PIN/), '3')
    expect(button).toBeEnabled()
  })

  it('sends the number and PIN', async () => {
    vi.mocked(authApi.pinLogin).mockResolvedValue(tokens)
    renderPage()

    await userEvent.type(screen.getByLabelText(/phone number/i), '0712345678')
    await userEvent.type(screen.getByLabelText(/^PIN/), '482913')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() =>
      expect(authApi.pinLogin).toHaveBeenCalledWith({ phone_number: '0712345678', pin: '482913' }),
    )
  })

  it('only lets digits into the PIN box', async () => {
    renderPage()
    const pin = screen.getByLabelText(/^PIN/)

    await userEvent.type(pin, '48a2-9x13')

    expect(pin).toHaveValue('482913')
  })

  it('shows a locked phone as the message the server gave', async () => {
    vi.mocked(authApi.pinLogin).mockRejectedValue({
      response: { data: { detail: { message: 'Too many failed attempts. Try again in 5 minute(s).' } } },
    })
    renderPage()

    await userEvent.type(screen.getByLabelText(/phone number/i), '0712345678')
    await userEvent.type(screen.getByLabelText(/^PIN/), '482913')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText(/try again in 5 minute/i)).toBeInTheDocument()
  })

  it('refuses an obvious new PIN and a mismatch before sending anything', async () => {
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: /new phone or forgot your pin/i }))

    await userEvent.type(screen.getByLabelText(/phone number/i), '0712345678')
    await userEvent.type(screen.getByLabelText(/sign-in code/i), '654321')
    await userEvent.type(screen.getByLabelText(/choose a new pin/i), '123456')
    expect(screen.getByText(/not an obvious one/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /set my pin/i })).toBeDisabled()

    await userEvent.clear(screen.getByLabelText(/choose a new pin/i))
    await userEvent.type(screen.getByLabelText(/choose a new pin/i), '482913')
    await userEvent.type(screen.getByLabelText(/confirm the pin/i), '482914')
    expect(screen.getByText(/do not match/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /set my pin/i })).toBeDisabled()
    expect(authApi.pinEnroll).not.toHaveBeenCalled()
  })

  it('sets a new PIN with the handed-over code', async () => {
    vi.mocked(authApi.pinEnroll).mockResolvedValue(tokens)
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: /new phone or forgot your pin/i }))

    await userEvent.type(screen.getByLabelText(/phone number/i), '0712345678')
    await userEvent.type(screen.getByLabelText(/sign-in code/i), '654321')
    await userEvent.type(screen.getByLabelText(/choose a new pin/i), '482913')
    await userEvent.type(screen.getByLabelText(/confirm the pin/i), '482913')
    await userEvent.click(screen.getByRole('button', { name: /set my pin/i }))

    await waitFor(() =>
      expect(authApi.pinEnroll).toHaveBeenCalledWith({
        phone_number: '0712345678',
        code: '654321',
        pin: '482913',
      }),
    )
  })

  it('remembers the number for next time', async () => {
    vi.mocked(authApi.pinLogin).mockResolvedValue(tokens)
    renderPage()

    await userEvent.type(screen.getByLabelText(/phone number/i), '0712345678')
    await userEvent.type(screen.getByLabelText(/^PIN/), '482913')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(localStorage.getItem('rentflow-pin-phone')).toBe('0712345678'))
  })
})
