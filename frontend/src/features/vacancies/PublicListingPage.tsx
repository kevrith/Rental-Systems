import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Bath,
  BedDouble,
  Check,
  MapPin,
  MessageCircle,
  Ruler,
  Share2,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { publicListingApi } from '@/api'
import { Alert, Button, Field, Input, PageLoader, Textarea } from '@/components/ui'
import { errorMessage, humanize, kes } from '@/lib/format'

/** The shareable advert (US-074). No login, and built to be opened on a phone
 *  from a WhatsApp group. */
export function PublicListingPage() {
  const { slug } = useParams<{ slug: string }>()
  const [sent, setSent] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [form, setForm] = useState({ full_name: '', phone_number: '', message: '' })
  const [error, setError] = useState<string | null>(null)

  const listing = useQuery({
    queryKey: ['public-listing-slug', slug],
    queryFn: () => publicListingApi.get(slug!),
    enabled: Boolean(slug),
    retry: false,
  })

  const inquire = useMutation({
    mutationFn: () =>
      publicListingApi.inquire(slug!, {
        full_name: form.full_name,
        phone_number: form.phone_number,
        message: form.message || null,
      }),
    onSuccess: (result) => setSent(result.message),
    onError: (inquireError) => setError(errorMessage(inquireError)),
  })

  if (listing.isPending) return <PageLoader />

  if (listing.isError) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <Alert tone="warn" title="This listing is no longer available">
          The unit may already be let. Ask whoever shared the link for a current one.
        </Alert>
      </div>
    )
  }

  const unit = listing.data

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      {unit.photo_urls.length > 0 && (
        <div className="flex snap-x gap-1 overflow-x-auto bg-slate-900">
          {unit.photo_urls.map((url) => (
            <img
              key={url}
              src={url}
              alt=""
              className="h-64 w-full shrink-0 snap-center object-cover sm:h-80 sm:w-auto sm:max-w-lg"
            />
          ))}
        </div>
      )}

      <div className="mx-auto max-w-3xl px-4 py-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold text-slate-900">
              {unit.headline ?? `${unit.property_name}, unit ${unit.unit_number}`}
            </h1>
            <p className="mt-1 flex items-start gap-1.5 text-sm text-slate-600">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
              {unit.property_address}
              {unit.county ? `, ${unit.county} County` : ''}
            </p>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            onClick={async () => {
              const url = window.location.href
              if (navigator.share) {
                await navigator.share({ title: unit.property_name, url }).catch(() => undefined)
                return
              }
              await navigator.clipboard.writeText(url)
              setCopied(true)
              window.setTimeout(() => setCopied(false), 2000)
            }}
          >
            {copied ? <Check className="h-4 w-4" /> : <Share2 className="h-4 w-4" />}
            {copied ? 'Link copied' : 'Share'}
          </button>
        </div>

        <div className="mt-5 rounded-card border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-3xl font-semibold text-slate-900">
              {kes(unit.monthly_rent)}
            </span>
            <span className="text-slate-500">per month</span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Deposit {kes(unit.deposit_amount)}
          </p>

          <div className="mt-4 flex flex-wrap gap-5 text-sm text-slate-600">
            {unit.bedrooms !== null && (
              <span className="inline-flex items-center gap-1.5">
                <BedDouble className="h-4 w-4 text-slate-400" />
                {unit.bedrooms} bedroom{unit.bedrooms === 1 ? '' : 's'}
              </span>
            )}
            {unit.bathrooms !== null && (
              <span className="inline-flex items-center gap-1.5">
                <Bath className="h-4 w-4 text-slate-400" />
                {unit.bathrooms} bathroom{unit.bathrooms === 1 ? '' : 's'}
              </span>
            )}
            {unit.size_sqm && (
              <span className="inline-flex items-center gap-1.5">
                <Ruler className="h-4 w-4 text-slate-400" />
                {unit.size_sqm} m&sup2;
              </span>
            )}
            {unit.unit_type && <span>{unit.unit_type}</span>}
          </div>

          {unit.description && (
            <p className="mt-4 whitespace-pre-wrap text-sm text-slate-700">{unit.description}</p>
          )}

          {(unit.features.length > 0 || unit.amenities.length > 0) && (
            <div className="mt-4 flex flex-wrap gap-2">
              {[...unit.features, ...unit.amenities].map((feature) => (
                <span
                  key={feature}
                  className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
                >
                  {humanize(feature)}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="mt-5 rounded-card border border-slate-200 bg-white p-5">
          {sent ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <Check className="h-10 w-10 text-money-600" />
              <p className="text-sm text-slate-600">{sent}</p>
              <Link
                to={`/apply/${unit.unit_id}`}
                className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                Apply for this unit
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-base font-semibold text-slate-900">Interested?</h2>
              <p className="mt-1 text-sm text-slate-500">
                Leave your number and the landlord will call you. Or apply straight away.
              </p>

              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Your name" required>
                    <Input
                      value={form.full_name}
                      onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                    />
                  </Field>
                  <Field label="Phone number" required>
                    <Input
                      placeholder="+2547XXXXXXXX"
                      value={form.phone_number}
                      onChange={(event) => setForm({ ...form, phone_number: event.target.value })}
                    />
                  </Field>
                </div>
                <Field label="Anything you want to ask?">
                  <Textarea
                    placeholder="Is it still available? Can I view it on Saturday?"
                    value={form.message}
                    onChange={(event) => setForm({ ...form, message: event.target.value })}
                  />
                </Field>

                {error && <Alert tone="danger">{error}</Alert>}

                <div className="flex flex-wrap gap-2">
                  <Button
                    size="lg"
                    icon={<MessageCircle className="h-4 w-4" />}
                    disabled={form.full_name.length < 2 || form.phone_number.length < 10}
                    loading={inquire.isPending}
                    onClick={() => {
                      setError(null)
                      inquire.mutate()
                    }}
                  >
                    Ask about this unit
                  </Button>
                  <Link
                    to={`/apply/${unit.unit_id}`}
                    className="inline-flex h-12 items-center rounded-lg border border-slate-300 bg-white px-6 text-base font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Apply now
                  </Link>
                </div>
              </div>
            </>
          )}

          {unit.contact_phone && (
            <p className="mt-4 border-t border-slate-100 pt-4 text-sm text-slate-500">
              Or call {unit.contact_name ? `${unit.contact_name} on ` : ''}
              <a href={`tel:${unit.contact_phone}`} className="text-brand-600">
                {unit.contact_phone}
              </a>
            </p>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">Listed on RentFlow Kenya</p>
      </div>
    </div>
  )
}
