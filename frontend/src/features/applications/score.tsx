import type { ScoreBreakdown } from '@/api/types'

/** Green / amber / red, the same three bands the backend assigns. */
const BAND_STYLES: Record<string, { ring: string; text: string; label: string }> = {
  green: { ring: 'border-money-500 bg-money-50', text: 'text-money-700', label: 'Strong' },
  amber: { ring: 'border-warn-400 bg-warn-50', text: 'text-warn-700', label: 'Marginal' },
  red: { ring: 'border-danger-400 bg-danger-50', text: 'text-danger-700', label: 'Weak' },
}

export function ScoreDot({ score, band }: { score: number; band: string }) {
  const style = BAND_STYLES[band] ?? BAND_STYLES.red
  return (
    <div
      className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-full border-2 ${style.ring}`}
    >
      <span className={`text-lg font-semibold leading-none ${style.text}`}>{score}</span>
      <span className="text-[10px] uppercase tracking-wide text-slate-400">/100</span>
    </div>
  )
}

/** The score with its working shown — an applicant who is turned down deserves
 *  a reason a person can read out loud. */
export function ScoreBreakdownCard({ breakdown }: { breakdown: ScoreBreakdown }) {
  const style = BAND_STYLES[breakdown.band] ?? BAND_STYLES.red

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <ScoreDot score={breakdown.score} band={breakdown.band} />
        <div>
          <p className={`text-sm font-medium ${style.text}`}>{style.label} applicant</p>
          {breakdown.income_ratio !== null && (
            <p className="text-sm text-slate-600">
              Rent is {breakdown.income_ratio}% of stated income
              {breakdown.income_ratio_exceeded && (
                <span className="ml-1 font-medium text-danger-700">
                  — over the 30% guideline
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      <ul className="space-y-3">
        {breakdown.components.map((component) => (
          <li key={component.label}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm text-slate-700">{component.label}</span>
              <span className="tabular-nums text-sm font-medium text-slate-900">
                {component.points}
                <span className="font-normal text-slate-400">/{component.max}</span>
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${(component.points / component.max) * 100}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-slate-500">{component.note}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
