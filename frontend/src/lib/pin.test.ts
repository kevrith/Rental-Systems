import { describe, expect, it } from 'vitest'

import { isAcceptablePin } from './pin'

describe('isAcceptablePin', () => {
  it.each(['482913', '907351', '135791', '246810'])('accepts %s', (pin) => {
    expect(isAcceptablePin(pin)).toBe(true)
  })

  it.each([
    ['000000', 'one digit repeated'],
    ['121212', 'two digits alternating'],
    ['112211', 'only two different digits'],
    ['123456', 'counting up'],
    ['654321', 'counting down'],
    ['123123', 'the same three twice'],
    ['12345', 'too short'],
    ['1234567', 'too long'],
    ['12345a', 'not all digits'],
    ['', 'empty'],
  ])('refuses %s (%s)', (pin) => {
    expect(isAcceptablePin(pin)).toBe(false)
  })
})
