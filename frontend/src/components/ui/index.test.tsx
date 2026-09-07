import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Alert, Badge, Button, Dialog, EmptyState, Field, Input } from '@/components/ui'

/**
 * These are the primitives every screen is built out of, so a regression here
 * is a regression everywhere. The cases below are the behaviours that would be
 * silently wrong rather than visibly broken: a disabled button that still
 * fires, a field whose error is not associated with anything, a dialog that
 * traps the page scroll after it closes.
 */

describe('Button', () => {
  it('calls its handler when clicked', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Record payment</Button>)

    await userEvent.click(screen.getByRole('button', { name: 'Record payment' }))

    expect(onClick).toHaveBeenCalledOnce()
  })

  it('does not fire while disabled', async () => {
    const onClick = vi.fn()
    render(
      <Button onClick={onClick} disabled>
        Record payment
      </Button>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Record payment' }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('defaults to type="button" so it cannot submit a form by accident', () => {
    render(<Button>Cancel</Button>)
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveAttribute('type', 'button')
  })
})

describe('Field', () => {
  it('shows the hint when there is no error', () => {
    render(
      <Field label="Monthly rent" hint="Before service charge">
        <Input />
      </Field>,
    )

    expect(screen.getByText('Before service charge')).toBeInTheDocument()
  })

  it('replaces the hint with the error, so only one message shows at a time', () => {
    render(
      <Field label="Monthly rent" hint="Before service charge" error="Must be greater than zero">
        <Input />
      </Field>,
    )

    expect(screen.getByText('Must be greater than zero')).toBeInTheDocument()
    expect(screen.queryByText('Before service charge')).not.toBeInTheDocument()
  })

  it('marks a required field with an asterisk', () => {
    render(
      <Field label="Monthly rent" required>
        <Input />
      </Field>,
    )

    expect(screen.getByText('*')).toBeInTheDocument()
  })
})

describe('Alert', () => {
  it('renders its title and body', () => {
    render(
      <Alert tone="danger" title="Payment rejected">
        The amount was above the approval limit.
      </Alert>,
    )

    expect(screen.getByText('Payment rejected')).toBeInTheDocument()
    expect(screen.getByText('The amount was above the approval limit.')).toBeInTheDocument()
  })
})

describe('Badge', () => {
  it('renders the label it is given', () => {
    render(<Badge tone="warn">Overdue</Badge>)
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })
})

describe('EmptyState', () => {
  it('explains what is missing rather than showing a blank panel', () => {
    render(<EmptyState title="No payments yet" description="Record one to get started." />)

    expect(screen.getByText('No payments yet')).toBeInTheDocument()
    expect(screen.getByText('Record one to get started.')).toBeInTheDocument()
  })
})

describe('Dialog', () => {
  it('renders nothing at all when closed', () => {
    render(
      <Dialog open={false} onClose={vi.fn()} title="Confirm">
        Body
      </Dialog>,
    )

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('is labelled by its own title for screen readers', () => {
    render(
      <Dialog open onClose={vi.fn()} title="Approve this payment?">
        Body
      </Dialog>,
    )

    expect(screen.getByRole('dialog', { name: 'Approve this payment?' })).toBeInTheDocument()
  })

  it('closes on Escape and on the close button', async () => {
    const onClose = vi.fn()
    render(
      <Dialog open onClose={onClose} title="Confirm">
        Body
      </Dialog>,
    )

    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('restores page scrolling when it unmounts', () => {
    const { unmount } = render(
      <Dialog open onClose={vi.fn()} title="Confirm">
        Body
      </Dialog>,
    )
    expect(document.body.style.overflow).toBe('hidden')

    unmount()

    // A dialog that leaves the body locked makes the whole page unscrollable
    // on a phone, which is the device most of this product is used on.
    expect(document.body.style.overflow).not.toBe('hidden')
  })
})
