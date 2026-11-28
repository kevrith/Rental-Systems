import { KeyRound, Link2 } from 'lucide-react'

import { signaturesApi } from '@/api'
import type { HandoverAction } from '@/components/HandoverDialog'

/**
 * The two things a landlord or caretaker passes on to someone who has to sign:
 * the signing link, then the code that proves it is really them opening it.
 * Two separate messages on purpose — the code only lives 15 minutes, so it is
 * made after the link has reached them.
 */
export function signingActions(signatureId: string, who: string): HandoverAction[] {
  return [
    {
      key: `${signatureId}-link`,
      title: `1. Signing link for ${who}`,
      description:
        'Opens the document to read and sign. Making a new link cancels the earlier one, and it lasts 3 days.',
      buttonLabel: 'Make a signing link',
      icon: <Link2 className="h-4 w-4" />,
      run: () => signaturesApi.handoverLink(signatureId),
    },
    {
      key: `${signatureId}-code`,
      title: `2. Signing code for ${who}`,
      description:
        'They enter it on the signing page. Make it once they have the link and are ready; it works once.',
      buttonLabel: 'Make a signing code',
      icon: <KeyRound className="h-4 w-4" />,
      run: () => signaturesApi.handoverCode(signatureId),
    },
  ]
}
