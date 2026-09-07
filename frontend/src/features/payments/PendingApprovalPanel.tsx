import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ShieldAlert, X } from 'lucide-react'
import { useState } from 'react'

import { paymentsApi } from '@/api'
import type { PaymentDetail } from '@/api/types'
import { Alert, Badge, Button, Card, CardBody, Dialog, Field, Textarea } from '@/components/ui'
import { dateTime, errorMessage, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

/**
 * Cash held for a second signature (masterplan, Fraud Prevention).
 *
 * This panel is not optional decoration: a payment over the organisation's
 * threshold is recorded but *not banked* — nothing is allocated to an invoice,
 * no receipt is issued, and the tenant is not told their rent arrived. Without
 * somewhere to approve it, that money is stranded and the tenant's balance is
 * wrong. It sits at the top of the payments list for that reason.
 *
 * The server refuses an approval by the person who recorded the payment; the
 * panel simply never renders for someone without `payment:approve`.
 */
export function PendingApprovalPanel() {
  const queryClient = useQueryClient()
  const canApprove = useAuthStore((state) => state.user?.permissions?.includes('payment:approve'))
  const [rejecting, setRejecting] = useState<PaymentDetail | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const pending = useQuery({
    queryKey: queryKeys.paymentsPendingApproval,
    queryFn: paymentsApi.pendingApproval,
    enabled: Boolean(canApprove),
  })

  const settled = async () => {
    setError(null)
    setRejecting(null)
    setReason('')
    await queryClient.invalidateQueries({ queryKey: queryKeys.paymentsPendingApproval })
    await queryClient.invalidateQueries({ queryKey: ['payments'] })
    await queryClient.invalidateQueries({ queryKey: ['invoices'] })
  }

  const approve = useMutation({
    mutationFn: (id: string) => paymentsApi.approve(id),
    onSuccess: settled,
    onError: (mutationError) => setError(errorMessage(mutationError)),
  })

  const reject = useMutation({
    mutationFn: ({ id, why }: { id: string; why: string }) => paymentsApi.reject(id, why),
    onSuccess: settled,
    onError: (mutationError) => setError(errorMessage(mutationError)),
  })

  const rows = pending.data ?? []
  if (!canApprove || rows.length === 0) return null

  return (
    <>
      <Card className="mb-4 border-warn-200">
        <CardBody className="space-y-3">
          <div className="flex items-start gap-2">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-warn-600" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-slate-900">
                {rows.length} cash {rows.length === 1 ? 'payment needs' : 'payments need'} your
                approval
              </p>
              <p className="text-xs text-slate-500">
                These are recorded but not banked. Nothing is credited to the tenant, and no
                receipt has been sent, until you approve.
              </p>
            </div>
          </div>

          {error && <Alert tone="danger">{error}</Alert>}

          <div className="space-y-2">
            {rows.map((payment) => (
              <div
                key={payment.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">
                    {kes(payment.amount)}
                    <span className="ml-2 font-normal text-slate-500">
                      {payment.tenant_name ?? 'Unknown tenant'}
                      {payment.unit_number ? ` · ${payment.unit_number}` : ''}
                    </span>
                  </p>
                  <p className="text-xs text-slate-500">
                    {payment.reference_code} · recorded by{' '}
                    {payment.recorded_by_name ?? 'someone'} · {dateTime(payment.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="warn">Held</Badge>
                  <Button
                    size="sm"
                    variant="outline"
                    icon={<X className="h-4 w-4" />}
                    onClick={() => {
                      setError(null)
                      setRejecting(payment)
                    }}
                  >
                    Reject
                  </Button>
                  <Button
                    size="sm"
                    icon={<Check className="h-4 w-4" />}
                    loading={approve.isPending && approve.variables === payment.id}
                    onClick={() => approve.mutate(payment.id)}
                  >
                    Approve
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <Dialog
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title="Reject this cash payment?"
        description="Nothing will be credited to the tenant, and the person who recorded it will be told why."
        footer={
          <>
            <Button variant="ghost" onClick={() => setRejecting(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={reason.trim().length < 3}
              loading={reject.isPending}
              onClick={() =>
                rejecting && reject.mutate({ id: rejecting.id, why: reason.trim() })
              }
            >
              Reject payment
            </Button>
          </>
        }
      >
        <Field label="Reason" required hint="Recorded on the audit trail and sent to the recorder.">
          <Textarea
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Cash was never handed in at the office."
          />
        </Field>
      </Dialog>
    </>
  )
}
