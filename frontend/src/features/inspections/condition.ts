import type { BadgeTone } from '@/components/ui'
import type { RoomChange, RoomCondition } from '@/api/types'

/** Shared so the capture screen, the comparison and the PDF never disagree. */
export const CONDITION_TONE: Record<RoomCondition, BadgeTone> = {
  excellent: 'success',
  good: 'info',
  fair: 'warn',
  poor: 'danger',
}

export const CONDITIONS: { value: RoomCondition; label: string }[] = [
  { value: 'excellent', label: 'Excellent' },
  { value: 'good', label: 'Good' },
  { value: 'fair', label: 'Fair' },
  { value: 'poor', label: 'Poor' },
]

export const CHANGE_TONE: Record<RoomChange, BadgeTone> = {
  unchanged: 'neutral',
  better: 'success',
  worse: 'danger',
  not_inspected: 'warn',
}

export const CHANGE_LABEL: Record<RoomChange, string> = {
  unchanged: 'No change',
  better: 'Improved',
  worse: 'Deteriorated',
  not_inspected: 'Not re-inspected',
}
