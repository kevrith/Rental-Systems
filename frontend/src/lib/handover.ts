/**
 * Links that hand a message to the phone's own apps.
 *
 * RentFlow does not text one-time codes itself while SMS delivery is off. The
 * landlord or caretaker sends them from their own phone: `wa.me` opens
 * WhatsApp with the number and message filled in, `sms:` opens the messaging
 * app. On a computer WhatsApp Web still works; the SMS link has nowhere to go.
 */

/** Digits only, as `wa.me` wants the number: no plus, spaces or dashes. */
export const phoneDigits = (phone: string): string => phone.replace(/\D/g, '')

export const whatsappUrl = (phone: string, message: string): string =>
  `https://wa.me/${phoneDigits(phone)}?text=${encodeURIComponent(message)}`

/** WhatsApp with the message ready but no recipient, so the person picks the chat. */
export const whatsappShareUrl = (message: string): string =>
  `https://wa.me/?text=${encodeURIComponent(message)}`

export const smsUrl = (phone: string, message: string): string =>
  `sms:${phone}?body=${encodeURIComponent(message)}`

/** "15 minutes", "3 days" — how long a handed-over secret lives. */
export function lifetimeLabel(seconds: number): string {
  if (seconds >= 86400) {
    const days = Math.round(seconds / 86400)
    return `${days} day${days === 1 ? '' : 's'}`
  }
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600)
    return `${hours} hour${hours === 1 ? '' : 's'}`
  }
  const minutes = Math.max(1, Math.round(seconds / 60))
  return `${minutes} minute${minutes === 1 ? '' : 's'}`
}
