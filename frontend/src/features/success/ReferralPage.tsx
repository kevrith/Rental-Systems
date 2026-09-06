import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Gift, Send } from 'lucide-react'
import { useState } from 'react'

import { customerSuccessApi } from '@/api'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  Field,
  Input,
  PageLoader,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { errorMessage, shortDate } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const STATUS_TONE = {
  pending: 'neutral',
  signed_up: 'info',
  converted: 'success',
} as const

/** Referral tracking and credit (US-092). Credit is a ledger
 * (`Organization.credit_months`) rather than an applied invoice discount —
 * RentFlow has no billing engine yet for its own subscription fee. */
export function ReferralPage() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')

  const summary = useQuery({
    queryKey: queryKeys.referralSummary,
    queryFn: customerSuccessApi.referralSummary,
  })

  const record = useMutation({
    mutationFn: () => customerSuccessApi.createReferral({ referred_email: email }),
    onSuccess: () => {
      setEmail('')
      queryClient.invalidateQueries({ queryKey: queryKeys.referralSummary })
    },
  })

  if (summary.isPending) return <PageLoader />
  if (!summary.data) return <Alert tone="danger">Could not load your referral details.</Alert>

  const data = summary.data

  return (
    <div>
      <PageHeader
        title="Refer a friend"
        description="Share your link — when a referred account upgrades, you get a month of credit."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Total referrals" value={String(data.referrals.length)} />
        <StatCard
          label="Converted"
          value={String(data.referrals.filter((r) => r.status === 'converted').length)}
        />
        <StatCard label="Credit earned" value={`${data.credit_months} month(s)`} icon={<Gift className="h-4 w-4" />} />
      </div>

      <Card className="mb-6">
        <CardBody>
          <Field label="Your referral link">
            <div className="flex gap-2">
              <Input readOnly value={data.referral_link} />
              <Button
                type="button"
                variant="secondary"
                onClick={() => navigator.clipboard.writeText(data.referral_link)}
              >
                <Copy className="h-4 w-4" />
                Copy
              </Button>
            </div>
          </Field>

          <form
            className="mt-4 flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              record.mutate()
            }}
          >
            <Field label="Or record a referral by email" className="min-w-64 flex-1">
              <Input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="friend@example.com"
              />
            </Field>
            <Button type="submit" loading={record.isPending}>
              <Send className="h-4 w-4" />
              Record
            </Button>
          </form>
          {record.isError && <Alert tone="danger" className="mt-3">{errorMessage(record.error)}</Alert>}
        </CardBody>
      </Card>

      {data.referrals.length === 0 ? (
        <EmptyState title="No referrals yet" description="Share your link above to get started." />
      ) : (
        <Card>
          <CardBody className="overflow-x-auto p-0">
            <Table>
              <thead>
                <tr>
                  <Th>Email</Th>
                  <Th>Status</Th>
                  <Th>Recorded</Th>
                </tr>
              </thead>
              <tbody>
                {data.referrals.map((referral) => (
                  <tr key={referral.id}>
                    <Td>{referral.referred_email}</Td>
                    <Td>
                      <Badge tone={STATUS_TONE[referral.status]}>{referral.status.replace('_', ' ')}</Badge>
                    </Td>
                    <Td>{shortDate(referral.created_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
