import { beforeEach, describe, expect, it } from 'vitest'

import { useCommandPaletteStore } from '@/store/command-palette-store'

/**
 * Small, but the keyboard shortcut and the dismiss button drive it from
 * opposite directions, and a `toggle` that read a stale value would leave the
 * palette stuck open over the page it is meant to navigate away from.
 */

beforeEach(() => {
  useCommandPaletteStore.setState({ open: false })
})

describe('command palette visibility', () => {
  it('starts closed', () => {
    expect(useCommandPaletteStore.getState().open).toBe(false)
  })

  it('opens and closes through setOpen', () => {
    useCommandPaletteStore.getState().setOpen(true)
    expect(useCommandPaletteStore.getState().open).toBe(true)

    useCommandPaletteStore.getState().setOpen(false)
    expect(useCommandPaletteStore.getState().open).toBe(false)
  })

  it('toggles from whatever the current state is, not a captured one', () => {
    const { toggle } = useCommandPaletteStore.getState()

    toggle()
    expect(useCommandPaletteStore.getState().open).toBe(true)

    // Same destructured reference, so a toggle closing over a stale `open`
    // would re-open here instead of closing.
    toggle()
    expect(useCommandPaletteStore.getState().open).toBe(false)
  })
})
