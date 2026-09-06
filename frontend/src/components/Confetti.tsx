/** A brief, dependency-free celebration burst — see `rf-confetti-piece` in
 * index.css. Used for onboarding completion and milestone celebrations so
 * neither pulls in a confetti library for one moment in the product. */
const COLORS = [
  'var(--color-brand-500)',
  'var(--color-money-500)',
  'var(--color-warn-500)',
  'var(--color-danger-500)',
]

export function Confetti({ pieces = 24 }: { pieces?: number }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 h-0 overflow-visible" aria-hidden>
      {Array.from({ length: pieces }).map((_, index) => (
        <span
          key={index}
          className="rf-confetti-piece"
          style={{
            left: `${(index / pieces) * 100}%`,
            backgroundColor: COLORS[index % COLORS.length],
            animationDelay: `${(index % 6) * 60}ms`,
          }}
        />
      ))}
    </div>
  )
}
