/**
 * Tiny class-name joiner.
 *
 * Deliberately not `clsx` + `tailwind-merge`: the components here never take
 * conflicting utility overrides, so a dependency-free join is enough and keeps
 * the bundle small for 3G caretakers.
 */
export type ClassValue = string | number | null | undefined | false | ClassValue[]

export function cn(...values: ClassValue[]): string {
  const out: string[] = []
  for (const value of values) {
    if (!value) continue
    if (Array.isArray(value)) {
      const nested = cn(...value)
      if (nested) out.push(nested)
    } else {
      out.push(String(value))
    }
  }
  return out.join(' ')
}
