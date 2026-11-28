/**
 * The caretaker PIN rules, mirrored from the server so a bad choice is caught
 * before the request. The server is the authority and checks again.
 */
export const PIN_LENGTH = 6

export const PIN_RULE_MESSAGE =
  'Choose a 6-digit PIN that is not an obvious one such as 123456 or 000000.'

export function isAcceptablePin(pin: string): boolean {
  if (!/^\d{6}$/.test(pin)) return false
  const digits = [...pin].map(Number)
  if (new Set(digits).size < 3) return false // 000000, 111111, 121212
  const steps = new Set(digits.slice(1).map((digit, index) => digit - digits[index]))
  if (steps.size === 1 && (steps.has(1) || steps.has(-1))) return false // 123456, 654321
  if (pin.slice(0, 3) === pin.slice(3)) return false // 123123
  return true
}
