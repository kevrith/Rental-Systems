# Email deliverability — SPF, DKIM, DMARC, and bounce/complaint handling

**Status: the code half of this is built (email suppression,
`app/services/email_service.py`, Sprint 26A). The DNS half is not — it can't
be, from here.** SPF, DKIM and DMARC are records on the real domain
`EMAIL_FROM` sends as (today `rentflow.co.ke`), configured in that domain's
own DNS zone through whoever hosts it and in the Resend dashboard. Nobody
editing code in this repository has access to that — this document is the
runbook for whoever does.

## Why this is two separate problems

- **"Is RentFlow allowed to send as this domain?"** — SPF, DKIM, DMARC. Pure
  DNS. A mailbox provider (Gmail, Outlook, everyone downstream of them) checks
  these before it even looks at the message content. Get them wrong and mail
  lands in spam or gets rejected outright, regardless of how well-behaved the
  sending code is.
- **"Does RentFlow behave once it can send?"** — bounce and complaint
  handling. This is the part that's actually code, and it's built: Resend's
  delivery-event webhook (`POST /api/v1/webhooks/resend`) marks the
  `Notification` row and adds the address to `email_suppressions`
  (`app/models/notification.py`) — platform-wide, since every organisation's
  email goes out through the one shared `EMAIL_FROM` domain, so one
  landlord's tenant bouncing has to protect every other landlord's sender
  reputation too. `notification_service.send`'s email branch checks
  `email_service.is_suppressed` before ever calling Resend, so a suppressed
  address is skipped rather than retried into oblivion.

A domain with perfect SPF/DKIM/DMARC that never processes a bounce will still
lose deliverability within weeks once its bounce rate creeps up. A domain
with excellent bounce handling but no DKIM will never get mail delivered in
the first place. Both halves are required; neither substitutes for the other.

## The DNS runbook

1. **Add and verify the sending domain in Resend.** Resend's dashboard
   (Domains → Add Domain) generates the exact records for step 2 — copy them
   from there rather than hand-deriving generic ones, since the DKIM
   selector and public key are specific to that Resend account.
2. **Add the DNS records Resend gives you**, in the DNS zone for
   `rentflow.co.ke` (or whatever `EMAIL_FROM`'s domain actually is at deploy
   time):
   - **SPF** (TXT, root domain): authorizes Resend's sending servers. If a
     record already exists (common — most domains have one for something
     else), Resend's servers must be *added* to it, not placed in a second,
     competing TXT record — two SPF records is a standards violation that
     several providers treat as an outright SPF failure.
   - **DKIM** (TXT/CNAME, a Resend-specific selector): the actual signing
     key. This is what "verify" in the Resend dashboard is checking for.
   - **Return-Path/MX** (Resend may ask for a subdomain, e.g.
     `bounce.rentflow.co.ke`, to handle bounces at the SMTP level): follow
     whatever Resend's own setup screen specifies for the account in use.
3. **Wait for DNS propagation and confirm "Verified" in Resend** before
   relying on the domain — sending through an unverified domain is why SPF
   would fail in the first place.
4. **Add a DMARC record** (TXT, `_dmarc.rentflow.co.ke`), starting at
   monitor-only:
   ```
   v=DMARC1; p=none; rua=mailto:dmarc-reports@rentflow.co.ke; pct=100
   ```
   `p=none` does not block or quarantine anything — it only asks mailbox
   providers to *report* what they saw (via `rua`), which is how a spoofing
   attempt or a misconfigured record gets noticed before enforcement makes it
   a customer-facing incident. This is the standard, deliberate rollout
   order — never start at `p=reject`.
5. **After 2–4 weeks of clean DMARC reports** (no legitimate mail failing
   alignment), tighten to `p=quarantine`, then eventually `p=reject`. Each
   step is a one-line DNS change; the waiting between them is the point, not
   something to skip to "finish faster."
6. **Set `RESEND_WEBHOOK_SECRET`** (the `.env` value, from Resend's dashboard
   under Webhooks → the endpoint pointed at `POST /api/v1/webhooks/resend`)
   in every environment that sends real email. Without it, the webhook
   endpoint refuses every event rather than trusting an unsigned payload —
   see `email_service.verify_webhook_signature`.

## What "done" looks like

- Resend shows the domain as **Verified**.
- `dig TXT rentflow.co.ke` shows exactly one SPF record including Resend's
  servers.
- `dig TXT _dmarc.rentflow.co.ke` returns the DMARC record, and DMARC
  aggregate reports (sent to the `rua` address, usually daily, from whichever
  provider fields the report) show mail from `EMAIL_FROM` passing SPF and
  DKIM alignment.
- A deliberately-bounced test send (e.g. to a syntactically valid but
  non-existent address at a real domain) shows up as `BOUNCED` on the
  corresponding `Notification` row within the webhook's normal delivery
  latency, and the address appears in `email_suppressions`.

None of this can be verified from the codebase alone — it requires a real,
DNS-controlled domain and a live Resend account, which is why this document
is a runbook for a person to execute rather than something this pass could
complete end-to-end.
