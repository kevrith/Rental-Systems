import type { BadgeTone } from '@/components/ui'
import type { DisbursementStatus } from '@/api/types'

/** Shared so the dashboard, list and detail views never disagree on colour. */
export const DISBURSEMENT_STATUS_TONE: Record<DisbursementStatus, BadgeTone> = {
  pending: 'warn',
  approved: 'brand',
  rejected: 'danger',
  processing: 'info',
  completed: 'success',
  failed: 'danger',
}

/** What the agency can still do to a payout in each state. */
export const CAN_REVIEW: DisbursementStatus[] = ['pending']
export const CAN_PAY: DisbursementStatus[] = ['approved', 'failed']
