import { Building2, ShieldAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** Sprint 24, US-104: privacy policy, terms of service, and cookie policy —
 *  all three legal pages live here as one file, the same "related public
 *  pages together" pattern PasswordPages.tsx and PublicResponsePages.tsx use.
 *
 *  These are Kelvin's drafts, not a lawyer's — see the banner on every page.
 *  Bracketed placeholders ([...]) mark facts only Kelvin can supply
 *  (company registration number, physical address, DPO contact); nothing
 *  here invents a registration or certificate number that doesn't exist. */

const LAST_UPDATED = 'September 2026'

function DraftNotice() {
  return (
    <div className="mb-8 flex gap-3 rounded-card border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <ShieldAlert className="h-5 w-5 shrink-0" />
      <p>
        This is a working draft prepared for RentFlow's launch preparation. It is not a
        substitute for review by a qualified Kenyan lawyer, and should not be relied on as
        final until that review happens and the bracketed placeholders below are filled in.
      </p>
    </div>
  )
}

function LegalPageLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-4">
          <Link to="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
              <Building2 className="h-4 w-4" />
            </span>
            <span className="text-base font-semibold text-slate-900">RentFlow Kenya</span>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        <p className="mt-1 text-sm text-slate-500">Last updated: {LAST_UPDATED}</p>

        <div className="mt-8">
          <DraftNotice />
        </div>

        <div
          className="space-y-4 text-sm leading-relaxed text-slate-700
            [&_h2]:mb-2 [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-slate-900
            [&_li]:pl-1 [&_strong]:text-slate-900
            [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5"
        >
          {children}
        </div>

        <div className="mt-10 flex gap-4 border-t border-slate-200 pt-6 text-sm text-slate-500">
          <Link to="/legal/privacy" className="hover:text-slate-700">
            Privacy Policy
          </Link>
          <Link to="/legal/terms" className="hover:text-slate-700">
            Terms of Service
          </Link>
          <Link to="/legal/cookies" className="hover:text-slate-700">
            Cookie Policy
          </Link>
        </div>
      </main>
    </div>
  )
}

// ------------------------------------------------------------ privacy policy

export function PrivacyPolicyPage() {
  return (
    <LegalPageLayout title="Privacy Policy">
      <p>
        RentFlow Kenya ("RentFlow", "we", "us") is operated by Avinaya Solutions
        [company registration number] of [physical address]. This policy explains what
        personal data RentFlow collects through the platform, why, and what rights you have
        over it under Kenya's Data Protection Act, 2019 ("the DPA").
      </p>

      <h2>Who this applies to</h2>
      <p>
        Anyone whose data passes through RentFlow: property owners and agency staff who run
        an account, caretakers they invite, tenants who rent through a property managed on
        RentFlow, and guarantors or referees named in a tenant application.
      </p>

      <h2>What we collect</h2>
      <p>Depending on your role, RentFlow processes:</p>
      <ul>
        <li>
          <strong>Identity and contact details</strong> — full name, phone number, email,
          national ID number, and (for tenants and applicants) a photo of your national ID and
          a passport photo, collected for KYC and tenancy record-keeping.
        </li>
        <li>
          <strong>Financial data</strong> — rent amounts, payment history, M-Pesa transaction
          references (via Safaricom's Daraja API), bank account details for owners receiving
          disbursements, and KRA PIN where eTIMS tax receipts are generated.
        </li>
        <li>
          <strong>Employment and guarantor details</strong> — collected during tenant
          screening (employer, income, guarantor identity and contact details) to assess a
          rental application.
        </li>
        <li>
          <strong>Property and device data</strong> — meter readings and inspection photos
          (optionally geo-tagged when a caretaker's device permits it), device fingerprints
          and IP addresses used for login security and fraud detection.
        </li>
        <li>
          <strong>Communications metadata</strong> — delivery status of the WhatsApp, SMS, and
          email notifications RentFlow sends on your behalf (e.g. payment confirmations, rent
          reminders).
        </li>
      </ul>

      <h2>How we use it</h2>
      <p>
        To operate the tenancy you or your organization is party to: generating leases and
        invoices, processing and reconciling rent payments, sending statutory tax receipts,
        running fraud checks on payment activity, and sending the notifications a landlord,
        caretaker, or tenant has asked for or reasonably expects (rent due, payment received,
        maintenance updates).
      </p>
      <p>
        If an owner opts into AI-assisted lease template review, the relevant lease template
        text is sent to Anthropic (our AI provider) for analysis. No tenant KYC documents or
        payment data are sent to this or any AI provider — only the lease template text
        itself, and only when an owner explicitly requests the analysis.
      </p>

      <h2>Who we share it with</h2>
      <p>
        Only the processors needed to run the platform: Safaricom (M-Pesa payments), Africa's
        Talking (SMS), Meta/WhatsApp Business Platform (WhatsApp messages), Cloudflare (file
        storage), Resend (email delivery), Anthropic (opt-in AI lease analysis only), and KRA
        (statutory eTIMS tax receipts). We do not sell personal data, and we do not share a
        tenant's data with any owner or agency other than the one they have an actual tenancy
        with.
      </p>

      <h2>How long we keep it</h2>
      <p>
        For as long as your account or tenancy is active, plus the retention period Kenyan
        tax and tenancy law requires afterward (statutory financial records in particular
        outlive an active tenancy). Account deletion requests go through a 30-day grace
        period before permanent removal, as described in the Terms of Service.
      </p>

      <h2>Your rights under the DPA</h2>
      <p>
        You may request access to, correction of, or deletion of your personal data, and may
        object to or restrict certain processing, by contacting [data protection contact
        email]. We will respond within the timeframe the DPA requires. If you believe your
        data has been mishandled, you may also complain directly to the Office of the Data
        Protection Commissioner (ODPC), Kenya.
      </p>

      <h2>Security</h2>
      <p>
        Passwords are hashed, never stored in plain text. Financial and identity documents
        are stored behind time-limited signed URLs rather than public links. Two-factor
        authentication is available on every account. See our published security practices
        for more detail on request.
      </p>

      <h2>Contact</h2>
      <p>Questions about this policy: [data protection contact email].</p>
    </LegalPageLayout>
  )
}

// ------------------------------------------------------------------ terms of service

export function TermsOfServicePage() {
  return (
    <LegalPageLayout title="Terms of Service">
      <p>
        These Terms govern use of the RentFlow Kenya platform, operated by Avinaya Solutions
        [company registration number]. By creating an account or using RentFlow through an
        organization that has, you agree to them.
      </p>

      <h2>The service</h2>
      <p>
        RentFlow is software for managing rental properties: tenant and lease records,
        rent invoicing and payment collection (including M-Pesa), maintenance tracking,
        inspections, and related reporting. RentFlow is not a party to any tenancy agreement
        generated or managed through it — the landlord (or agency) and tenant are.
      </p>

      <h2>Accounts and trial</h2>
      <p>
        A new organization gets a 30-day free trial with no card required. After trial expiry,
        the account moves to read-only until a paid plan is selected; existing data is not
        deleted. You're responsible for keeping your login credentials confidential and for
        activity under your account, including anyone you invite as a caretaker or team member.
      </p>

      <h2>Payments processed through RentFlow</h2>
      <p>
        M-Pesa payments are processed via Safaricom's Daraja platform; RentFlow reconciles and
        records the resulting transaction but is not the payment processor of record — a
        payment dispute involving the underlying M-Pesa transaction is between the paying
        party and Safaricom. Cash payments recorded by a caretaker are exactly that: a record
        of a cash transaction the caretaker attests took place, subject to any
        caretaker-cash-limit the owner has configured.
      </p>

      <h2>Owner and agency responsibilities</h2>
      <p>
        If you use RentFlow to manage properties on behalf of others (agency mode), you are
        responsible for the accuracy of the management agreements, fee percentages, and
        disbursement details you configure — RentFlow calculates disbursements from what you
        enter, and is not a party to your management agreement with your client owners.
      </p>

      <h2>Acceptable use</h2>
      <p>
        Don't use RentFlow to store or transmit unlawful content, to discriminate against
        tenants or applicants on a basis unlawful under Kenyan law, or to attempt to access
        another organization's data. We may suspend an account for a clear violation of this
        section, with notice where reasonably possible.
      </p>

      <h2>Data deletion</h2>
      <p>
        An account deletion request starts a 30-day grace period, after which the account and
        its data are permanently removed, except for records Kenyan law requires RentFlow or
        the organization to retain longer (e.g. certain financial records).
      </p>

      <h2>Availability and liability</h2>
      <p>
        RentFlow is provided "as is." We work to keep the service available and to reconcile
        payments accurately, but we don't guarantee uninterrupted availability, and — to the
        extent Kenyan law allows — our liability for any claim arising from use of the
        platform is limited to the fees you paid RentFlow in the 12 months before the claim
        arose. Nothing here limits liability that cannot lawfully be limited.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these Terms; material changes will be announced in-app (see the
        in-app changelog) with reasonable notice before they take effect.
      </p>

      <h2>Governing law</h2>
      <p>These Terms are governed by the laws of Kenya.</p>

      <h2>Contact</h2>
      <p>[support contact email]</p>
    </LegalPageLayout>
  )
}

// ------------------------------------------------------------------ cookie policy

export function CookiePolicyPage() {
  return (
    <LegalPageLayout title="Cookie Policy">
      <p>
        RentFlow is a web application (installable as a PWA), and like most such
        applications it uses a small amount of browser storage to work at all — not primarily
        advertising cookies. This page explains what's stored and why.
      </p>

      <h2>What we actually use</h2>
      <ul>
        <li>
          <strong>Session storage (required)</strong> — your login session (access and refresh
          tokens) is kept in the browser so you stay signed in between page loads. Without
          this, RentFlow cannot function.
        </li>
        <li>
          <strong>Device identifier (required for 2FA)</strong> — a locally-generated,
          random device id (`X-Device-Id`) lets RentFlow recognize a device you've verified
          before, so you're not asked for a one-time code on every login from your own phone.
        </li>
        <li>
          <strong>Offline queue (caretaker and tenant PWA)</strong> — meter readings,
          maintenance requests, and payments recorded while offline are held in the browser's
          IndexedDB storage until connectivity returns, then synced and cleared.
        </li>
        <li>
          <strong>Service worker cache (PWA)</strong> — app assets are cached locally so
          RentFlow loads quickly and works offline, per the Workbox-based PWA setup.
        </li>
        <li>
          <strong>Preferences</strong> — small UI preferences (e.g. a collapsed panel, a
          chosen filter) may be remembered locally so you don't have to reset them each visit.
        </li>
      </ul>

      <h2>What we don't use</h2>
      <p>
        RentFlow does not use third-party advertising or cross-site tracking cookies. We
        don't sell data to ad networks, and there is no ad-tech pixel on this site.
      </p>

      <h2>Your control</h2>
      <p>
        Everything above is stored locally in your own browser, not on a central tracking
        server, and clearing your browser's site data for RentFlow removes it (you'll simply
        need to sign in again). Because the required items above are what make the app work,
        there isn't an "essential cookies off" option — turning off local storage in your
        browser will prevent RentFlow from functioning, the same as it would for any other
        web application that needs to keep you signed in.
      </p>

      <h2>Contact</h2>
      <p>[data protection contact email]</p>
    </LegalPageLayout>
  )
}
